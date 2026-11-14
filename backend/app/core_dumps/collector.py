"""Short-lived collector Job on the node, and file transfer out of it over exec.

The Job mounts the host core directory read-only and just sleeps; the backend
execs ``stat``/``sha256sum``/``cat`` in it. Files are streamed frame by frame
straight to local disk so a 150 MB core never sits in the backend's memory
(the backend runs with a 256 Mi limit).
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import uuid
from typing import BinaryIO, Callable, List, Optional, Tuple

from kubernetes import client
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream
from websocket import ABNF, WebSocketException

from .config import CoreDumpConfig
from .parsing import LISTING_SCRIPT, is_safe_relative_path, parse_listing
from .schemas import CoreDumpFile, HostCoreConfig

CONTAINER_NAME = "collector"

# Kubernetes exec channel ids (first byte of every websocket frame).
_STDOUT, _STDERR, _ERROR = 1, 2, 3
_STDERR_KEEP = 4096
_SMALL_OUTPUT_LIMIT = 8 * 1024 * 1024
_FATAL_WAITING = {
    "ErrImageNeverPull",
    "ImagePullBackOff",
    "ErrImagePull",
    "CrashLoopBackOff",
    "CreateContainerConfigError",
    "CreateContainerError",
}


class CoreDumpCollectionError(Exception):
    """The collector Job could not be run or a transfer failed."""


# --- Job manifest ------------------------------------------------------------


def build_collector_job(config: CoreDumpConfig) -> client.V1Job:
    """Pure: the collector Job. Read-only host mount, no API token, minimal caps."""
    labels = {"app": config.job_prefix}
    container = client.V1Container(
        name=CONTAINER_NAME,
        image=config.image,
        image_pull_policy=config.image_pull_policy,
        command=["sleep", str(config.job_deadline_seconds)],
        resources=client.V1ResourceRequirements(
            requests={"cpu": "50m", "memory": "32Mi"},
            limits={"cpu": "500m", "memory": "64Mi"},
        ),
        security_context=client.V1SecurityContext(
            run_as_user=0,
            run_as_group=0,
            allow_privilege_escalation=False,
            read_only_root_filesystem=True,
            # Cores are 0600 and owned by the crashing process's uid, so root
            # needs DAC_READ_SEARCH to read them. Nothing else.
            capabilities=client.V1Capabilities(
                drop=["ALL"], add=["DAC_READ_SEARCH"]
            ),
            seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
        ),
        volume_mounts=[
            client.V1VolumeMount(
                name="cores", mount_path=config.mount_path, read_only=True
            )
        ],
    )
    pod_spec = client.V1PodSpec(
        restart_policy="Never",
        node_name=config.node_name,
        automount_service_account_token=False,
        enable_service_links=False,
        termination_grace_period_seconds=0,
        containers=[container],
        volumes=[
            client.V1Volume(
                name="cores",
                host_path=client.V1HostPathVolumeSource(
                    path=config.host_dir, type="Directory"
                ),
            )
        ],
    )
    return client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name=f"{config.job_prefix}-{uuid.uuid4().hex[:8]}",
            namespace=config.namespace,
            labels=labels,
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            active_deadline_seconds=config.job_deadline_seconds,
            ttl_seconds_after_finished=config.job_ttl_seconds,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels), spec=pod_spec
            ),
        ),
    )


# --- exec streaming ----------------------------------------------------------


def _exec_status(raw: bytes) -> Tuple[bool, Optional[str]]:
    """Parse the exec error channel's Status object -> (success, message)."""
    if not raw:
        return True, None
    try:
        status = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return False, raw.decode("utf-8", "replace")[:500]
    if status.get("status") == "Success":
        return True, None
    return False, status.get("message") or "command failed"


def exec_to_sink(
    core: client.CoreV1Api,
    pod: str,
    namespace: str,
    command: List[str],
    sink: BinaryIO,
    timeout_seconds: float,
    on_bytes: Optional[Callable[[int], None]] = None,
    limit_bytes: Optional[int] = None,
) -> None:
    """Run `command` in the collector and write its stdout to `sink`.

    Reads one websocket frame at a time (instead of WSClient.update(), which
    drains every frame already waiting and can buffer a whole file in memory).
    Raises CoreDumpCollectionError on a non-zero exit, timeout or broken stream.
    """
    try:
        ws = stream(
            core.connect_get_namespaced_pod_exec,
            pod,
            namespace,
            command=command,
            container=CONTAINER_NAME,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            binary=True,
            _preload_content=False,
        )
    except ApiException as e:
        raise CoreDumpCollectionError(
            f"Could not exec into collector pod {pod}: {e.reason or e}"
        ) from e

    deadline = time.monotonic() + timeout_seconds
    stderr = bytearray()
    error_raw = b""
    written = 0
    try:
        sock = ws.sock
        sock.settimeout(min(60.0, timeout_seconds))
        while True:
            if time.monotonic() > deadline:
                raise CoreDumpCollectionError(
                    f"Transfer from {pod} timed out after {timeout_seconds:.0f}s"
                )
            opcode, frame = sock.recv_data_frame(True)
            if opcode == ABNF.OPCODE_CLOSE:
                break
            if opcode not in (ABNF.OPCODE_BINARY, ABNF.OPCODE_TEXT):
                continue
            data = frame.data
            if isinstance(data, str):
                data = data.encode("utf-8")
            if not data:
                continue
            channel, payload = data[0], data[1:]
            if channel == _STDOUT and payload:
                written += len(payload)
                if limit_bytes is not None and written > limit_bytes:
                    raise CoreDumpCollectionError(
                        f"Command output exceeded {limit_bytes} bytes"
                    )
                sink.write(payload)
                if on_bytes:
                    on_bytes(len(payload))
            elif channel == _STDERR and len(stderr) < _STDERR_KEEP:
                stderr += payload[: _STDERR_KEEP - len(stderr)]
            elif channel == _ERROR:
                error_raw += payload
    except (WebSocketException, OSError) as e:
        raise CoreDumpCollectionError(f"Exec stream from {pod} broke: {e}") from e
    finally:
        try:
            ws.close()
        except Exception:
            pass

    ok, message = _exec_status(error_raw)
    if not ok:
        detail = stderr.decode("utf-8", "replace").strip()
        raise CoreDumpCollectionError(
            f"{message}{f': {detail}' if detail else ''}"
        )


def _exec_small(
    core: client.CoreV1Api,
    pod: str,
    config: CoreDumpConfig,
    command: List[str],
    timeout_seconds: float = 60,
) -> str:
    buffer = io.BytesIO()
    exec_to_sink(
        core,
        pod,
        config.namespace,
        command,
        buffer,
        timeout_seconds,
        limit_bytes=_SMALL_OUTPUT_LIMIT,
    )
    return buffer.getvalue().decode("utf-8", "replace")


# --- session -----------------------------------------------------------------


class CollectorSession:
    """Context manager: create the Job, wait for its pod, always delete it."""

    def __init__(
        self,
        core: client.CoreV1Api,
        batch: client.BatchV1Api,
        config: CoreDumpConfig,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.core = core
        self.batch = batch
        self.config = config
        self._sleep = sleep
        self.job_name: Optional[str] = None
        self.pod_name: Optional[str] = None
        self.node_name: Optional[str] = None

    def __enter__(self) -> "CollectorSession":
        job = build_collector_job(self.config)
        try:
            created = self.batch.create_namespaced_job(
                namespace=self.config.namespace, body=job
            )
        except ApiException as e:
            raise CoreDumpCollectionError(
                f"Could not create core dump collector Job in "
                f"{self.config.namespace}: {e.reason or e}"
            ) from e
        self.job_name = (created.metadata.name if created.metadata else None) or (
            job.metadata.name
        )
        try:
            self._wait_for_running()
        except BaseException:
            self._delete()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self._delete()

    def _wait_for_running(self) -> None:
        selector = f"job-name={self.job_name}"
        deadline = time.monotonic() + self.config.startup_timeout_seconds
        last_pod: Optional[str] = None
        while time.monotonic() < deadline:
            pods = self.core.list_namespaced_pod(
                namespace=self.config.namespace, label_selector=selector
            ).items
            if pods:
                pod = pods[0]
                last_pod = pod.metadata.name if pod.metadata else last_pod
                status = pod.status
                phase = status.phase if status else None
                if phase == "Running" and last_pod:
                    self.pod_name = last_pod
                    self.node_name = pod.spec.node_name if pod.spec else None
                    return
                if phase in ("Failed", "Succeeded"):
                    raise CoreDumpCollectionError(
                        f"Collector pod {last_pod} exited ({phase}) before use."
                    )
                for cs in (status.container_statuses or []) if status else []:
                    waiting = cs.state.waiting if cs.state else None
                    if waiting and waiting.reason in _FATAL_WAITING:
                        detail = f" - {waiting.message}" if waiting.message else ""
                        raise CoreDumpCollectionError(
                            f"Collector pod {last_pod} cannot start: "
                            f"{waiting.reason}{detail}"
                        )
                for cond in (status.conditions or []) if status else []:
                    if (
                        cond.type == "PodScheduled"
                        and cond.status == "False"
                        and cond.reason == "Unschedulable"
                    ):
                        raise CoreDumpCollectionError(
                            f"Collector pod {last_pod} is unschedulable: {cond.message}"
                        )
            self._sleep(self.config.poll_interval_seconds)
        where = f"last pod {last_pod}" if last_pod else "no pod was created"
        raise CoreDumpCollectionError(
            f"Collector pod did not start within "
            f"{self.config.startup_timeout_seconds}s ({where})."
        )

    def _delete(self) -> None:
        if not self.job_name:
            return
        try:
            self.batch.delete_namespaced_job(
                name=self.job_name,
                namespace=self.config.namespace,
                propagation_policy="Background",
                grace_period_seconds=0,
            )
        except ApiException:
            # Already gone, or no permission: activeDeadlineSeconds + TTL
            # are the backstop.
            pass

    # --- operations ---

    def list_files(self) -> Tuple[List[CoreDumpFile], HostCoreConfig]:
        output = _exec_small(
            self.core,
            self.pod_name,
            self.config,
            ["sh", "-c", 'cd "$1" && ' + LISTING_SCRIPT, "sh", self.config.mount_path],
        )
        return parse_listing(output)

    def remote_sha256(self, path: str) -> str:
        _require_safe(path)
        output = _exec_small(
            self.core,
            self.pod_name,
            self.config,
            ["sh", "-c", 'cd "$1" && sha256sum "./$2"', "sh", self.config.mount_path, path],
            timeout_seconds=self.config.transfer_timeout_seconds,
        )
        digest = output.split(" ", 1)[0].strip()
        if len(digest) != 64:
            raise CoreDumpCollectionError(f"Unexpected sha256sum output for {path}")
        return digest

    def fetch(
        self,
        path: str,
        sink: BinaryIO,
        on_bytes: Optional[Callable[[int], None]] = None,
    ) -> Tuple[str, int]:
        """Stream one file into `sink`; returns (sha256, size) of what arrived."""
        _require_safe(path)
        hasher = hashlib.sha256()
        size = 0

        class _HashingSink:
            def write(self, data: bytes) -> int:
                nonlocal size
                hasher.update(data)
                size += len(data)
                return sink.write(data)

        exec_to_sink(
            self.core,
            self.pod_name,
            self.config.namespace,
            ["sh", "-c", 'cd "$1" && exec cat "./$2"', "sh", self.config.mount_path, path],
            _HashingSink(),
            self.config.transfer_timeout_seconds,
            on_bytes=on_bytes,
        )
        return hasher.hexdigest(), size


def _require_safe(path: str) -> None:
    if not is_safe_relative_path(path):
        raise CoreDumpCollectionError(f"Refusing unsafe core path: {path!r}")

"""Run a short-lived Job and exec commands in its pod.

Shared by the node collectors (core dumps, firewall). The Job's pod is expected
to just sleep; callers exec into it and the session always deletes the Job.

Output is read one websocket frame at a time and written to a sink, instead of
using WSClient.update() (which drains every frame already waiting and can
buffer a whole file in memory) or stream()'s capture-all buffer. The backend
runs with a 256 Mi memory limit.
"""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass
from typing import BinaryIO, Callable, List, Optional, Tuple

from kubernetes import client
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream
from websocket import ABNF, WebSocketException

# Kubernetes exec channel ids (first byte of every websocket frame).
_STDOUT, _STDERR, _ERROR = 1, 2, 3
_STDERR_KEEP = 4096
SMALL_OUTPUT_LIMIT = 16 * 1024 * 1024

FATAL_WAITING_REASONS = frozenset(
    {
        "ErrImageNeverPull",
        "ImagePullBackOff",
        "ErrImagePull",
        "CrashLoopBackOff",
        "CreateContainerConfigError",
        "CreateContainerError",
    }
)


class JobExecError(Exception):
    """The Job could not be run, or an exec into it failed."""


@dataclass
class ExecResult:
    ok: bool
    message: Optional[str]  # failure message from the exec status, if any
    stderr: str


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
    container: str,
    command: List[str],
    sink: BinaryIO,
    timeout_seconds: float,
    on_bytes: Optional[Callable[[int], None]] = None,
    limit_bytes: Optional[int] = None,
    check: bool = True,
) -> ExecResult:
    """Run `command` in the pod and write its stdout to `sink`.

    Raises JobExecError on a broken stream, timeout or output over
    `limit_bytes`; and, when `check` is true, on a non-zero exit.
    """
    try:
        ws = stream(
            core.connect_get_namespaced_pod_exec,
            pod,
            namespace,
            command=command,
            container=container,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            binary=True,
            _preload_content=False,
        )
    except ApiException as e:
        raise JobExecError(f"Could not exec into pod {pod}: {e.reason or e}") from e

    deadline = time.monotonic() + timeout_seconds
    stderr = bytearray()
    error_raw = b""
    written = 0
    try:
        sock = ws.sock
        sock.settimeout(min(60.0, timeout_seconds))
        while True:
            if time.monotonic() > deadline:
                raise JobExecError(
                    f"Command in {pod} timed out after {timeout_seconds:.0f}s"
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
                    raise JobExecError(f"Command output exceeded {limit_bytes} bytes")
                sink.write(payload)
                if on_bytes:
                    on_bytes(len(payload))
            elif channel == _STDERR and len(stderr) < _STDERR_KEEP:
                stderr += payload[: _STDERR_KEEP - len(stderr)]
            elif channel == _ERROR:
                error_raw += payload
    except (WebSocketException, OSError) as e:
        raise JobExecError(f"Exec stream from {pod} broke: {e}") from e
    finally:
        try:
            ws.close()
        except Exception:
            pass

    ok, message = _exec_status(error_raw)
    stderr_text = stderr.decode("utf-8", "replace").strip()
    if check and not ok:
        raise JobExecError(f"{message}{f': {stderr_text}' if stderr_text else ''}")
    return ExecResult(ok=ok, message=message, stderr=stderr_text)


class JobExecSession:
    """Context manager: create `job`, wait for its pod to run, always delete it.

    Subclasses build the Job and add their own operations on top of `exec`.
    """

    def __init__(
        self,
        core: client.CoreV1Api,
        batch: client.BatchV1Api,
        job: client.V1Job,
        container: str,
        startup_timeout_seconds: int = 90,
        poll_interval_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        error_cls: type = JobExecError,
    ) -> None:
        self.core = core
        self.batch = batch
        self.job = job
        self.namespace = job.metadata.namespace
        self.container = container
        self.startup_timeout_seconds = startup_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep
        self._error = error_cls
        self.job_name: Optional[str] = None
        self.pod_name: Optional[str] = None
        self.node_name: Optional[str] = None

    def __enter__(self):
        try:
            created = self.batch.create_namespaced_job(
                namespace=self.namespace, body=self.job
            )
        except ApiException as e:
            raise self._error(
                f"Could not create Job in {self.namespace}: {e.reason or e}"
            ) from e
        self.job_name = (created.metadata.name if created.metadata else None) or (
            self.job.metadata.name
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
        deadline = time.monotonic() + self.startup_timeout_seconds
        last_pod: Optional[str] = None
        while time.monotonic() < deadline:
            pods = self.core.list_namespaced_pod(
                namespace=self.namespace, label_selector=selector
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
                    raise self._error(
                        f"Collector pod {last_pod} exited ({phase}) before use."
                    )
                for cs in (status.container_statuses or []) if status else []:
                    waiting = cs.state.waiting if cs.state else None
                    if waiting and waiting.reason in FATAL_WAITING_REASONS:
                        detail = f" - {waiting.message}" if waiting.message else ""
                        raise self._error(
                            f"Collector pod {last_pod} cannot start: "
                            f"{waiting.reason}{detail}"
                        )
                for cond in (status.conditions or []) if status else []:
                    if (
                        cond.type == "PodScheduled"
                        and cond.status == "False"
                        and cond.reason == "Unschedulable"
                    ):
                        raise self._error(
                            f"Collector pod {last_pod} is unschedulable: {cond.message}"
                        )
            self._sleep(self.poll_interval_seconds)
        where = f"last pod {last_pod}" if last_pod else "no pod was created"
        raise self._error(
            f"Collector pod did not start within "
            f"{self.startup_timeout_seconds}s ({where})."
        )

    def _delete(self) -> None:
        if not self.job_name:
            return
        try:
            self.batch.delete_namespaced_job(
                name=self.job_name,
                namespace=self.namespace,
                propagation_policy="Background",
                grace_period_seconds=0,
            )
        except ApiException:
            # Already gone, or no permission: activeDeadlineSeconds + TTL
            # are the backstop.
            pass

    # --- exec helpers ---

    def exec(
        self,
        command: List[str],
        sink: BinaryIO,
        timeout_seconds: float,
        on_bytes: Optional[Callable[[int], None]] = None,
        limit_bytes: Optional[int] = None,
        check: bool = True,
    ) -> ExecResult:
        try:
            return exec_to_sink(
                self.core,
                self.pod_name,
                self.namespace,
                self.container,
                command,
                sink,
                timeout_seconds,
                on_bytes=on_bytes,
                limit_bytes=limit_bytes,
                check=check,
            )
        except JobExecError as e:
            if isinstance(e, self._error):
                raise
            raise self._error(str(e)) from e

    def exec_text(self, command: List[str], timeout_seconds: float = 60) -> str:
        buffer = io.BytesIO()
        self.exec(command, buffer, timeout_seconds, limit_bytes=SMALL_OUTPUT_LIMIT)
        return buffer.getvalue().decode("utf-8", "replace")

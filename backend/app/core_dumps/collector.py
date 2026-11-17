"""Short-lived collector Job on the node, and file transfer out of it over exec.

The Job mounts the host core directory read-only and just sleeps; the backend
execs ``stat``/``sha256sum``/``cat`` in it (see app.core.job_exec). Files are
streamed frame by frame straight to local disk, so a 150 MB core never sits in
the backend's memory.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import BinaryIO, Callable, List, Optional, Tuple

from kubernetes import client

from app.core.job_exec import JobExecError, JobExecSession

from .config import CoreDumpConfig
from .parsing import LISTING_SCRIPT, is_safe_relative_path, parse_listing
from .schemas import CoreDumpFile, HostCoreConfig

CONTAINER_NAME = "collector"


class CoreDumpCollectionError(JobExecError):
    """The collector Job could not be run or a transfer failed."""


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


class CollectorSession(JobExecSession):
    """Collector Job lifecycle plus the core-dump operations run inside it."""

    def __init__(
        self,
        core: client.CoreV1Api,
        batch: client.BatchV1Api,
        config: CoreDumpConfig,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(
            core,
            batch,
            build_collector_job(config),
            CONTAINER_NAME,
            startup_timeout_seconds=config.startup_timeout_seconds,
            poll_interval_seconds=config.poll_interval_seconds,
            sleep=sleep,
            error_cls=CoreDumpCollectionError,
        )
        self.config = config

    def _in_core_dir(self, script: str, *args: str) -> List[str]:
        return ["sh", "-c", f'cd "$1" && {script}', "sh", self.config.mount_path, *args]

    def list_files(self) -> Tuple[List[CoreDumpFile], HostCoreConfig]:
        return parse_listing(self.exec_text(self._in_core_dir(LISTING_SCRIPT)))

    def remote_sha256(self, path: str) -> str:
        _require_safe(path)
        output = self.exec_text(
            self._in_core_dir('sha256sum "./$2"', path),
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

        self.exec(
            self._in_core_dir('exec cat "./$2"', path),
            _HashingSink(),
            self.config.transfer_timeout_seconds,
            on_bytes=on_bytes,
        )
        return hasher.hexdigest(), size


def _require_safe(path: str) -> None:
    if not is_safe_relative_path(path):
        raise CoreDumpCollectionError(f"Refusing unsafe core path: {path!r}")

"""Deployment-tunable settings for the core dump collector Job."""

import os
from dataclasses import dataclass
from typing import Optional

# busybox is already on the node (mirrored for the platform) and has the
# sh/stat/sha256sum/cat the collector needs.
_DEFAULT_IMAGE = (
    "us-artifactory.apps.ge-healthcare.net/docker-axone-all/"
    "rancher/mirrored-library-busybox:1.36.1"
)


@dataclass(frozen=True)
class CoreDumpConfig:
    namespace: str = "iomt-integration"
    image: str = _DEFAULT_IMAGE
    image_pull_policy: str = "IfNotPresent"
    # Where coredump_handler.sh writes on the host (and where the
    # local-path provisioner puts the coredump-class PVs).
    host_dir: str = "/var/log/files"
    # Where host_dir is mounted (read-only) inside the collector pod.
    mount_path: str = "/host-cores"
    # Optional: pin the Job to a node. The backend's service account cannot
    # list Nodes, so on a multi-node cluster this must be set explicitly.
    # TODO(multi-node): one Job per node.
    node_name: Optional[str] = None
    job_prefix: str = "core-dump-collector"
    # Hard ceiling on the collector pod's lifetime; the pod just sleeps and
    # is exec'd into, so this is what guarantees it never lingers. There is
    # no size cap on collection, so this has to cover pulling every core.
    job_deadline_seconds: int = 4 * 3600
    job_ttl_seconds: int = 120
    startup_timeout_seconds: int = 90
    poll_interval_seconds: float = 1.0
    # Per-file transfer ceiling (a 150 MB core takes well under a minute).
    transfer_timeout_seconds: int = 1800


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def get_core_dump_config() -> CoreDumpConfig:
    defaults = CoreDumpConfig()
    return CoreDumpConfig(
        namespace=os.environ.get("CORE_DUMP_NAMESPACE", "iomt-integration"),
        image=os.environ.get("CORE_DUMP_IMAGE", _DEFAULT_IMAGE),
        host_dir=os.environ.get("CORE_DUMP_HOST_DIR", "/var/log/files"),
        node_name=os.environ.get("CORE_DUMP_NODE_NAME") or None,
        job_deadline_seconds=_env_int(
            "CORE_DUMP_JOB_DEADLINE_SECONDS", defaults.job_deadline_seconds
        ),
        transfer_timeout_seconds=_env_int(
            "CORE_DUMP_TRANSFER_TIMEOUT_SECONDS", defaults.transfer_timeout_seconds
        ),
    )

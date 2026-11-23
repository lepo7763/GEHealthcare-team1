"""Deployment-tunable settings for the Prometheus TSDB collector Job."""

import os
from dataclasses import dataclass
from typing import Optional

from app.core_dumps.config import _DEFAULT_IMAGE, _env_int


@dataclass(frozen=True)
class PrometheusConfig:
    """Same shape as CoreDumpConfig, so the core-dump collector Job is reused."""

    namespace: str = "iomt-integration"
    image: str = _DEFAULT_IMAGE
    image_pull_policy: str = "IfNotPresent"
    # Host directory searched (a few levels deep) for Prometheus data
    # directories. The platform's axone-local-path provisioner puts PVs here,
    # so the Prometheus PVC is
    #   pvc-<uid>_compute_prometheus-...-db-.../prometheus-db/
    host_dir: str = "/opt/local-path-provisioner"
    # Where host_dir is mounted (read-only) inside the collector pod.
    mount_path: str = "/host-prometheus"
    # How deep under host_dir to look for TSDB blocks (<data-dir>/<ULID>/meta.json).
    search_depth: int = 4
    node_name: Optional[str] = None
    job_prefix: str = "prometheus-collector"
    # The database can be many GB, so the pod may need to live a while.
    job_deadline_seconds: int = 4 * 3600
    job_ttl_seconds: int = 120
    startup_timeout_seconds: int = 90
    poll_interval_seconds: float = 1.0
    # Per-file ceiling; block chunk files are at most 512 MB each.
    transfer_timeout_seconds: int = 1800


def get_prometheus_config() -> PrometheusConfig:
    defaults = PrometheusConfig()
    return PrometheusConfig(
        namespace=os.environ.get("PROMETHEUS_COLLECTOR_NAMESPACE", defaults.namespace),
        image=os.environ.get("PROMETHEUS_COLLECTOR_IMAGE", defaults.image),
        host_dir=os.environ.get("PROMETHEUS_HOST_DIR", defaults.host_dir),
        search_depth=_env_int("PROMETHEUS_SEARCH_DEPTH", defaults.search_depth),
        node_name=os.environ.get("PROMETHEUS_NODE_NAME")
        or os.environ.get("CORE_DUMP_NODE_NAME")
        or None,
        job_deadline_seconds=_env_int(
            "PROMETHEUS_JOB_DEADLINE_SECONDS", defaults.job_deadline_seconds
        ),
        transfer_timeout_seconds=_env_int(
            "PROMETHEUS_TRANSFER_TIMEOUT_SECONDS", defaults.transfer_timeout_seconds
        ),
    )

"""Configuration for UMF RTI discovery captures.

Everything that identifies platform resources is environment-driven so the
same backend image can run against a lab cluster or a customer installation.
The defaults match the lab platform described in kubernetes/README.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

DEFAULT_UMF_RTI_IMAGE = (
    "192.168.0.3:30003/spectro-images/"
    "us-artifactory.apps.ge-healthcare.net/docker-axone-all/"
    "axone-umfcompatibilitycheck:uw-badger-latest"
)


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class UmfRtiConfig:
    """Platform resources and Job settings for one UMF RTI capture."""

    image: str = DEFAULT_UMF_RTI_IMAGE
    namespace: str = "iomt-integration"
    image_pull_secrets: List[str] = field(
        default_factory=lambda: ["192-168-0-3-30003-pull-secret"]
    )

    qos_configmap: str = "umf-rti-qos"
    qos_key: str = "CommissioningQoS.xml"
    sdds_secret: str = "umf-rti-sdds"
    collector_secret: str = "umf-rti-collector"
    collector_key: str = "umf-rti-collector.jar"
    license_secret: str = "umf-rti-license"
    license_key: str = "rti_license.dat"

    router_namespace: str = "pm"
    router_service: str = "axone-router-1"
    discovery_peers_override: Optional[str] = None
    dds_interfaces: str = "eth0"

    cpu_request: str = "100m"
    memory_request: str = "256Mi"
    cpu_limit: str = "1"
    memory_limit: str = "1Gi"

    job_ttl_seconds: int = 600
    wait_timeout_seconds: int = 360
    poll_interval_seconds: float = 1.0
    job_active_deadline_grace_seconds: int = 300
    pod_creation_timeout_seconds: int = 60

    collector_container_name: str = "umf-rti-collector"
    collector_version: str = "1.0.0"
    collector_max_records: int = 5000

    @property
    def service_label_selector(self) -> str:
        return f"iomt-analysis-tool/service=umf-rti"

    @property
    def qos_mount_path(self) -> str:
        return "/opt/axone-tools/qos"

    @property
    def sdds_mount_path(self) -> str:
        return "/opt/axone-tools/sdds"

    @property
    def license_mount_path(self) -> str:
        return "/opt/axone-tools/license"

    @property
    def collector_mount_path(self) -> str:
        return "/opt/umf-rti"


def get_umf_rti_config() -> UmfRtiConfig:
    """Build the config from environment variables (fresh for each request)."""
    overrides = _env_list("IOMT_UMF_RTI_IMAGE_PULL_SECRETS", ["192-168-0-3-30003-pull-secret"])
    poll_interval = float(_env("IOMT_UMF_RTI_POLL_INTERVAL_SECONDS", "1"))
    if poll_interval <= 0:
        raise ValueError("IOMT_UMF_RTI_POLL_INTERVAL_SECONDS must be positive")
    return UmfRtiConfig(
        image=_env("IOMT_UMF_RTI_IMAGE", DEFAULT_UMF_RTI_IMAGE),
        namespace=_env("IOMT_UMF_RTI_NAMESPACE", "iomt-integration"),
        image_pull_secrets=overrides,
        qos_configmap=_env("IOMT_UMF_RTI_QOS_CONFIGMAP", "umf-rti-qos"),
        qos_key=_env("IOMT_UMF_RTI_QOS_KEY", "CommissioningQoS.xml"),
        sdds_secret=_env("IOMT_UMF_RTI_SDDS_SECRET", "umf-rti-sdds"),
        collector_secret=_env("IOMT_UMF_RTI_COLLECTOR_SECRET", "umf-rti-collector"),
        collector_key=_env("IOMT_UMF_RTI_COLLECTOR_KEY", "umf-rti-collector.jar"),
        license_secret=_env("IOMT_UMF_RTI_LICENSE_SECRET", "umf-rti-license"),
        license_key=_env("IOMT_UMF_RTI_LICENSE_KEY", "rti_license.dat"),
        router_namespace=_env("IOMT_UMF_RTI_ROUTER_NAMESPACE", "pm"),
        router_service=_env("IOMT_UMF_RTI_ROUTER_SERVICE", "axone-router-1"),
        discovery_peers_override=(
            _env("IOMT_UMF_RTI_DISCOVERY_PEERS", "")
            or None
        ),
        dds_interfaces=_env("IOMT_UMF_RTI_DDS_INTERFACES", "eth0"),
        cpu_request=_env("IOMT_UMF_RTI_CPU_REQUEST", "100m"),
        memory_request=_env("IOMT_UMF_RTI_MEMORY_REQUEST", "256Mi"),
        cpu_limit=_env("IOMT_UMF_RTI_CPU_LIMIT", "1"),
        memory_limit=_env("IOMT_UMF_RTI_MEMORY_LIMIT", "1Gi"),
        job_ttl_seconds=_env_int("IOMT_UMF_RTI_JOB_TTL_SECONDS", 600, 0),
        wait_timeout_seconds=_env_int("IOMT_UMF_RTI_WAIT_TIMEOUT_SECONDS", 360, 30),
        poll_interval_seconds=poll_interval,
        job_active_deadline_grace_seconds=_env_int(
            "IOMT_UMF_RTI_ACTIVE_DEADLINE_GRACE_SECONDS", 300, 30
        ),
        pod_creation_timeout_seconds=_env_int(
            "IOMT_UMF_RTI_POD_CREATION_TIMEOUT_SECONDS", 60, 10
        ),
        collector_version=_env("IOMT_UMF_RTI_COLLECTOR_VERSION", "1.0.0"),
        collector_max_records=_env_int("IOMT_UMF_RTI_MAX_RECORDS", 5000, 1),
    )

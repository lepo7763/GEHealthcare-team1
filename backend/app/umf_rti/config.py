import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UmfRtiConfig:
    """
    Environment-driven configuration for the UMF RTI Kubernetes Job collector.
    Defaults match the live MiniEdge cluster and the 'iomt-integration' sandbox.
    """

    # Cached platform image in local Harbor containing Ubuntu 22.04, JRE 17, and RTI 6.1.2 native libs
    image: str = os.environ.get(
        "IOMT_UMF_RTI_IMAGE",
        "192.168.0.3:30003/spectro-images/us-artifactory.apps.ge-healthcare.net/docker-axone-all/axone-umfcompatibilitycheck:uw-badger-latest",
    )
    namespace: str = os.environ.get("IOMT_UMF_RTI_NAMESPACE", "iomt-integration")

    # Mounted ConfigMap & Secrets in iomt-integration (created by kubernetes/umf-rti-setup.sh)
    qos_configmap: str = os.environ.get("IOMT_UMF_RTI_QOS_CONFIGMAP", "umf-rti-qos")
    qos_key: str = os.environ.get("IOMT_UMF_RTI_QOS_KEY", "CommissioningQoS.xml")
    qos_profile: str = os.environ.get(
        "IOMT_UMF_RTI_QOS_PROFILE", "AxoneNetQoSLibrary::umfgeneral_qos"
    )
    sdds_secret: str = os.environ.get("IOMT_UMF_RTI_SDDS_SECRET", "umf-rti-sdds")
    collector_secret: str = os.environ.get(
        "IOMT_UMF_RTI_COLLECTOR_SECRET", "umf-rti-collector"
    )
    license_secret: str = os.environ.get(
        "IOMT_UMF_RTI_LICENSE_SECRET", "umf-rti-license"
    )

    # Platform DDS router discovery settings
    router_namespace: str = os.environ.get("IOMT_UMF_RTI_ROUTER_NAMESPACE", "pm")
    router_service: str = os.environ.get(
        "IOMT_UMF_RTI_ROUTER_SERVICE", "axone-router-1"
    )
    # Optional manual override for NDDS_DISCOVERY_PEERS; if unset, resolved dynamically from router_service
    discovery_peers_override: str = os.environ.get("IOMT_UMF_RTI_DISCOVERY_PEERS", "")
    dds_interfaces: str = os.environ.get("IOMT_UMF_RTI_DDS_INTERFACES", "eth0")

    # Job container resource requests/limits (must fit inside iomt-integration-quota)
    cpu_request: str = os.environ.get("IOMT_UMF_RTI_CPU_REQUEST", "100m")
    cpu_limit: str = os.environ.get("IOMT_UMF_RTI_CPU_LIMIT", "1")
    memory_request: str = os.environ.get("IOMT_UMF_RTI_MEMORY_REQUEST", "256Mi")
    memory_limit: str = os.environ.get("IOMT_UMF_RTI_MEMORY_LIMIT", "1Gi")

    # Lifecycle & polling bounds
    job_ttl_seconds: int = int(os.environ.get("IOMT_UMF_RTI_JOB_TTL_SECONDS", "600"))
    poll_interval_seconds: float = float(
        os.environ.get("IOMT_UMF_RTI_POLL_INTERVAL_SECONDS", "2.0")
    )
    startup_fast_fail_seconds: int = int(
        os.environ.get("IOMT_UMF_RTI_STARTUP_FAST_FAIL_SECONDS", "60")
    )


def get_umf_rti_config() -> UmfRtiConfig:
    return UmfRtiConfig()
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UmfRtiConfig:
    namespace: str = "iomt-integration"
    image: str = "docker.io/library/axone-umf-rtitools:temp"
    router_namespace: str = "pm"
    sdds_secret_name: str = "umf-router-sdds"  # secret with the certs and private keys
    job_prefix: str = (
        "umf-rti-capture"  # just for kubernetes job naming; prefix to uuid
    )
    default_peer: str = "100.64.64.200"  # router
    poll_interval_seconds: float = 1.0
    startup_timeout_seconds: int = 30


# using getter to avoid allowing overriding any other fields
def get_umf_rti_config() -> UmfRtiConfig:
    return UmfRtiConfig(
        namespace=os.environ.get("UMF_RTI_NAMESPACE", "iomt-integration"),
        image=os.environ.get(
            "UMF_RTI_IMAGE", "docker.io/library/axone-umf-rtitools:temp"
        ),
        router_namespace=os.environ.get("UMF_RTI_ROUTER_NAMESPACE", "pm"),
        sdds_secret_name=os.environ.get("UMF_RTI_SDDS_SECRET", "umf-rti-sdds"),
        default_peer=os.environ.get("UMF_RTI_PEER", "100.64.64.200"),
    )

from dataclasses import dataclass

@dataclass(frozen=True)
class UmfRtiConfig:
    namespace: str = "iomt-integration"
    image: str = "docker.io/library/axone-umf-rtitools:temp"
    router_namespace: str = "pm"
    sdds_secret_name: str = "umf-router-sdds"
    job_prefix: str = "umf-rti-capture"
    default_peer: str = "100.64.64.200" # router
    poll_interval_seconds: float = 1.0
    startup_timeout_seconds: int = 30

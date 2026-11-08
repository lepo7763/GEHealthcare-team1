"""Configuration for the UMF-RTI capture feature.

Deployment-level constants for running an `rtirecordingservice` capture Job
against the Axone router. Defaults are the validated test-cluster values
(see backend/app/umf_rti/PLAN.md); every scalar is env-overridable so a real
cluster only needs different env, not code changes.

End users never see any of this — they pick a domain number + duration
(see schemas.py). Everything here is hidden infrastructure config.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

# WAN server ports the router exposes per DDS domain (its DDS_RTWAN_SERVER_PORT_*).
# We list all of them as peers so any WAN-facing domain matches without the user
# needing to know which transport/port a given domain uses.
_DEFAULT_WAN_PORTS: Dict[int, int] = {7: 32007, 12: 32013, 13: 32015}

_DEFAULT_IMAGE = "us-artifactory.apps.ge-healthcare.net/docker-axone-all/axone-umf-rtitools:router-certs"

# Friendly labels for the domain dropdown. Display gloss only (the stored/sent
# value is always the plain number); 13 is first so it's the default option.
# Only 7/12/13 — the domains the image's built-in Test certs authorize. Must
# stay in sync with the allowed set in schemas.py (UmfRtiParams.umf_domain_id).
_DEFAULT_DOMAIN_LABELS: Dict[int, str] = {
    13: "Viewer — live vitals (viewpod)",
    12: "Source — from Hub (sourcepod)",
    7: "Logger",
}


def _parse_domain_labels(raw: Optional[str]) -> Dict[int, str]:
    """Parse UMF_RTI_DOMAIN_LABELS (JSON object) or fall back to the defaults."""
    if not raw:
        return dict(_DEFAULT_DOMAIN_LABELS)
    try:
        return {int(k): str(v) for k, v in json.loads(raw).items()}
    except (ValueError, TypeError, AttributeError):
        return dict(_DEFAULT_DOMAIN_LABELS)


@dataclass(frozen=True)
class UmfRtiConfig:
    # --- Kubernetes placement ---
    namespace: str = "iomt-integration"  # where the capture Job runs
    router_namespace: str = "pm"  # where axone-router lives
    image: str = (
        _DEFAULT_IMAGE  # rtitools image, present on the node (pull policy Never)
    )
    job_prefix: str = "umf-rti-capture"  # k8s Job name prefix (+ uuid)

    # --- DDS identity / transport ---
    # The image ships Test certs authorized for domains 7/12/13. no other secret needed.
    sdds_home: str = "/opt/axone-tools/sdds"
    router_pod_peer: str = (
        "udpv4://100.64.64.200"  # internal plain-UDP locator (router pod IP)
    )
    wan_public: str = "192.168.0.3"  # router's DDS_RTWAN_SERVER_PUBLIC_ADDRESS
    wan_ports: Dict[int, int] = field(default_factory=lambda: dict(_DEFAULT_WAN_PORTS))
    max_message_size: int = 1400  # router's WAN message_size_max

    # --- recorder tuning (both MANDATORY for umfnum/umfwav) ---
    # S35c_sapphire TypeObjects exceed the 300000 default -> recorder records nothing
    # for the clinical topics without this. (-1/UNLIMITED is rejected; use a number.)
    type_object_max_serialized_length: int = 33554432
    # Viewpod umfnum/umfwav writers are in a NAMED partition; a wildcard subscriber
    # partition is required or the reader silently never matches (no error logged).
    partition: str = "*"
    reader_history_depth: int = 64

    # --- capture lifecycle ---
    output_dir: str = "/out"  # recording dir inside the Job pod
    collect_grace_seconds: int = (
        300  # pod holds after recording so the backend can pull files
    )
    poll_interval_seconds: float = 1.0
    startup_timeout_seconds: int = 30

    # --- UI ---
    domain_labels: Dict[int, str] = field(
        default_factory=lambda: dict(_DEFAULT_DOMAIN_LABELS)
    )

    def initial_peers(self) -> list[str]:
        """Discovery peers: the internal router locator + every WAN port.

        Both transports are enabled on the capture participant and all peers
        are listed, so DDS auto-selects whichever matches the requested domain.
        """
        return [self.router_pod_peer] + [
            f"udpv4_wan://{self.wan_public}:{port}" for port in self.wan_ports.values()
        ]


def get_umf_rti_config() -> UmfRtiConfig:
    """Build config from environment, defaulting to validated test-cluster values."""
    return UmfRtiConfig(
        namespace=os.environ.get("UMF_RTI_NAMESPACE", "iomt-integration"),
        router_namespace=os.environ.get("UMF_RTI_ROUTER_NAMESPACE", "pm"),
        image=os.environ.get("UMF_RTI_IMAGE", _DEFAULT_IMAGE),
        job_prefix=os.environ.get("UMF_RTI_JOB_PREFIX", "umf-rti-capture"),
        sdds_home=os.environ.get("UMF_RTI_SDDS_HOME", "/opt/axone-tools/sdds"),
        router_pod_peer=os.environ.get("UMF_RTI_ROUTER_PEER", "udpv4://100.64.64.200"),
        wan_public=os.environ.get("UMF_RTI_WAN_PUBLIC", "192.168.0.3"),
        max_message_size=int(os.environ.get("UMF_RTI_MAX_MESSAGE_SIZE", "1400")),
        type_object_max_serialized_length=int(
            os.environ.get("UMF_RTI_TYPE_OBJECT_MAX", "33554432")
        ),
        partition=os.environ.get("UMF_RTI_PARTITION", "*"),
        reader_history_depth=int(os.environ.get("UMF_RTI_READER_DEPTH", "64")),
        output_dir=os.environ.get("UMF_RTI_OUTPUT_DIR", "/out"),
        collect_grace_seconds=int(os.environ.get("UMF_RTI_COLLECT_GRACE", "300")),
        poll_interval_seconds=float(os.environ.get("UMF_RTI_POLL_INTERVAL", "1.0")),
        startup_timeout_seconds=int(os.environ.get("UMF_RTI_STARTUP_TIMEOUT", "30")),
        domain_labels=_parse_domain_labels(os.environ.get("UMF_RTI_DOMAIN_LABELS")),
    )

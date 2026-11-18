"""Deployment-tunable settings for the firewall collector Job."""

import os
from dataclasses import dataclass
from typing import Optional

# Same on-node busybox as the core dump collector: it has nsenter and tar,
# and every firewall tool itself runs from the host's own mount namespace.
_DEFAULT_IMAGE = (
    "us-artifactory.apps.ge-healthcare.net/docker-axone-all/"
    "rancher/mirrored-library-busybox:1.36.1"
)


@dataclass(frozen=True)
class FirewallConfig:
    namespace: str = "iomt-integration"
    image: str = _DEFAULT_IMAGE
    image_pull_policy: str = "IfNotPresent"
    # TODO(multi-node): one Job per node. The backend's service account can't
    # list Nodes, so pin explicitly on a multi-node cluster.
    node_name: Optional[str] = None
    job_prefix: str = "firewall-collector"
    job_deadline_seconds: int = 300
    job_ttl_seconds: int = 120
    startup_timeout_seconds: int = 90
    poll_interval_seconds: float = 1.0
    # All commands run in one exec; ~20 firewall-cmd/iptables calls.
    commands_timeout_seconds: int = 180


def get_firewall_config() -> FirewallConfig:
    return FirewallConfig(
        namespace=os.environ.get("FIREWALL_NAMESPACE", "iomt-integration"),
        image=os.environ.get("FIREWALL_IMAGE", _DEFAULT_IMAGE),
        node_name=os.environ.get("FIREWALL_NODE_NAME") or None,
    )
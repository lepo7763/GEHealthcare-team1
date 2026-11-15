from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FirewallZone(BaseModel):
    """A firewalld zone or policy, as printed by --list-all-zones/--list-all-policies."""

    name: str
    active: bool = False
    is_default: bool = False
    target: Optional[str] = None
    interfaces: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    services: List[str] = Field(default_factory=list)
    ports: List[str] = Field(default_factory=list)
    protocols: List[str] = Field(default_factory=list)
    forward_ports: List[str] = Field(default_factory=list)
    source_ports: List[str] = Field(default_factory=list)
    icmp_blocks: List[str] = Field(default_factory=list)
    icmp_block_inversion: Optional[bool] = None
    masquerade: Optional[bool] = None
    forward: Optional[bool] = None
    rich_rules: List[str] = Field(default_factory=list)
    # Anything else (policies: priority, ingress-zones, egress-zones, ...).
    other: Dict[str, str] = Field(default_factory=dict)


class ZoneDrift(BaseModel):
    """A runtime setting that differs from the permanent (on-disk) config."""

    zone: str
    field: str
    runtime: str
    permanent: str


class IptablesTable(BaseModel):
    name: str
    chains: int = 0
    rules: int = 0
    # Built-in chain -> default policy (e.g. INPUT -> ACCEPT).
    policies: Dict[str, str] = Field(default_factory=dict)


class FirewalldStatus(BaseModel):
    installed: bool = False
    state: Optional[str] = None  # "running" | "not running"
    version: Optional[str] = None
    service_active: Optional[str] = None
    service_enabled: Optional[str] = None
    default_zone: Optional[str] = None
    log_denied: Optional[str] = None
    lockdown: Optional[bool] = None
    panic_mode: Optional[bool] = None


class CommandResult(BaseModel):
    id: str
    description: str
    command: str
    exit_code: Optional[int] = None
    status: str  # ok | error | missing
    file: str
    output_bytes: int = 0


class FirewallSnapshot(BaseModel):
    collected_at_utc: str
    node: Optional[str] = None
    collector_pod: Optional[str] = None
    firewalld: FirewalldStatus = Field(default_factory=FirewalldStatus)
    zones: List[FirewallZone] = Field(default_factory=list)
    policies: List[FirewallZone] = Field(default_factory=list)
    direct_rules: List[str] = Field(default_factory=list)
    drift: List[ZoneDrift] = Field(default_factory=list)
    unassigned_interfaces: List[str] = Field(
        default_factory=list,
        description="Host interfaces in no zone (so the default zone applies); "
        "lo and veth pod interfaces excluded.",
    )
    iptables_backend: Optional[str] = None  # e.g. "legacy" / "nf_tables"
    iptables_v4: List[IptablesTable] = Field(default_factory=list)
    iptables_v6: List[IptablesTable] = Field(default_factory=list)
    ipv6_enabled: Optional[bool] = None
    nft_ruleset_lines: int = 0
    ipset_count: int = 0
    commands: List[CommandResult] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class FirewallResponse(BaseModel):
    """GET /api/firewall: the parsed snapshot, a printable report, raw outputs."""

    snapshot: FirewallSnapshot
    report: str
    outputs: Dict[str, str] = Field(default_factory=dict)
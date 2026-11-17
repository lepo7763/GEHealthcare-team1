"""Pure: the fixed command list, the framed-output parser, firewall parsers
and the printable report. No Kubernetes here.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .schemas import (
    CommandResult,
    FirewalldStatus,
    FirewallSnapshot,
    FirewallZone,
    IptablesTable,
    ZoneDrift,
)


@dataclass(frozen=True)
class FirewallCommand:
    id: str
    argv: Tuple[str, ...]
    description: str
    # Exit codes that are answers, not failures (e.g. --query-* exits 1 for "no").
    ok_exit_codes: Tuple[int, ...] = (0,)

    @property
    def file(self) -> str:
        return f"firewall/{self.id}.txt"


# Read-only commands only. Nothing here is built from user input.
COMMANDS: Tuple[FirewallCommand, ...] = (
    FirewallCommand("firewalld_service_active", ("systemctl", "is-active", "firewalld"),
                    "Is the firewalld service running", (0, 3)),
    FirewallCommand("firewalld_service_enabled", ("systemctl", "is-enabled", "firewalld"),
                    "Is firewalld enabled at boot", (0, 1)),
    FirewallCommand("firewalld_version", ("firewall-cmd", "--version"), "firewalld version"),
    FirewallCommand("firewalld_state", ("firewall-cmd", "--state"),
                    "firewalld daemon state", (0, 252)),
    FirewallCommand("default_zone", ("firewall-cmd", "--get-default-zone"), "Default zone"),
    FirewallCommand("active_zones", ("firewall-cmd", "--get-active-zones"),
                    "Zones with interfaces or sources bound", (0, 2)),
    FirewallCommand("zones_runtime", ("firewall-cmd", "--list-all-zones"),
                    "Every zone, runtime config"),
    FirewallCommand("zones_permanent", ("firewall-cmd", "--permanent", "--list-all-zones"),
                    "Every zone, permanent (on-disk) config"),
    FirewallCommand("policies_runtime", ("firewall-cmd", "--list-all-policies"),
                    "Inter-zone policies (firewalld >= 0.9)"),
    FirewallCommand("direct_rules", ("firewall-cmd", "--direct", "--get-all-rules"),
                    "Direct (raw iptables) rules added through firewalld"),
    FirewallCommand("log_denied", ("firewall-cmd", "--get-log-denied"),
                    "Logging of denied packets"),
    FirewallCommand("lockdown", ("firewall-cmd", "--query-lockdown"),
                    "Lockdown mode", (0, 1)),
    FirewallCommand("panic_mode", ("firewall-cmd", "--query-panic"),
                    "Panic mode (drops all traffic)", (0, 1)),
    FirewallCommand("iptables_version", ("iptables", "--version"),
                    "iptables version and backend"),
    FirewallCommand("iptables_save", ("iptables-save",), "Full IPv4 ruleset (all tables)"),
    FirewallCommand("ip6tables_save", ("ip6tables-save",), "Full IPv6 ruleset (all tables)"),
    FirewallCommand("nft_ruleset", ("nft", "list", "ruleset"), "nftables ruleset"),
    FirewallCommand("ipsets", ("ipset", "list"), "IP sets"),
    FirewallCommand("interfaces", ("ip", "-o", "link", "show"), "Host network interfaces"),
    # -e: the IPv6 key doesn't exist when IPv6 is disabled at boot.
    FirewallCommand("ip_forwarding", ("sysctl", "-e", "net.ipv4.ip_forward",
                                      "net.ipv6.conf.all.forwarding"),
                    "Kernel IP forwarding"),
    FirewallCommand("ipv6_enabled", ("test", "-d", "/proc/sys/net/ipv6"),
                    "IPv6 enabled in the kernel (exit 1 = disabled)", (0, 1)),
)

MISSING_EXIT_CODE = 127


def build_script(commands: Iterable[FirewallCommand] = COMMANDS) -> str:
    """Host-side sh script. $1 is a per-run marker token.

    Each command's stdout+stderr is framed as
        <T> BEGIN <id>\\n<output>\\n<T> END <id> <rc>\\n
    (the newline before END is added by us and stripped by the parser).
    """
    lines = [
        'T="$1"',
        "run() {",
        '  id="$1"; shift',
        '  printf "%s BEGIN %s\\n" "$T" "$id"',
        '  if command -v "$1" >/dev/null 2>&1; then "$@" 2>&1; rc=$?; else rc=127; fi',
        '  printf "\\n%s END %s %s\\n" "$T" "$id" "$rc"',
        "}",
    ]
    for c in commands:
        lines.append("run " + " ".join(shlex.quote(a) for a in (c.id, *c.argv)))
    lines.append("exit 0")
    return "\n".join(lines) + "\n"


def parse_framed(output: str, token: str) -> Dict[str, Tuple[str, int]]:
    """Split framed output into {id: (text, exit_code)}. Unclosed frames are dropped."""
    results: Dict[str, Tuple[str, int]] = {}
    begin = re.compile(rf"^{re.escape(token)} BEGIN (\S+)$")
    end = re.compile(rf"^{re.escape(token)} END (\S+) (\d+)$")
    current: Optional[str] = None
    buf: List[str] = []
    for line in output.split("\n"):
        if current is None:
            m = begin.match(line)
            if m:
                current, buf = m.group(1), []
            continue
        m = end.match(line)
        if m and m.group(1) == current:
            # The separator newline build_script adds before END is the line
            # break consumed by split(), so joining restores the exact output.
            results[current] = ("\n".join(buf), int(m.group(2)))
            current = None
            continue
        buf.append(line)
    return results


# --- firewall-cmd ---------------------------------------------------------------

_HEADER = re.compile(r"^(\S+)(?:\s+\(([^)]*)\))?\s*$")
_LIST_FIELDS = {
    "interfaces": "interfaces",
    "sources": "sources",
    "services": "services",
    "ports": "ports",
    "protocols": "protocols",
    "forward-ports": "forward_ports",
    "source-ports": "source_ports",
    "icmp-blocks": "icmp_blocks",
}
_BOOL_FIELDS = {
    "masquerade": "masquerade",
    "forward": "forward",
    "icmp-block-inversion": "icmp_block_inversion",
}


def _yes(value: str) -> Optional[bool]:
    v = value.strip().lower()
    return True if v == "yes" else False if v == "no" else None


def parse_zones(text: str) -> List[FirewallZone]:
    """Parse `firewall-cmd --list-all-zones` (or --list-all-policies) output."""
    zones: List[FirewallZone] = []
    zone: Optional[FirewallZone] = None
    in_rich = False
    for raw in text.splitlines():
        if not raw.strip():
            in_rich = False
            continue
        if raw.startswith("\t") or (in_rich and raw.startswith("    ")):
            if zone is not None and in_rich:
                zone.rich_rules.append(raw.strip())
            continue
        if not raw.startswith(" "):
            m = _HEADER.match(raw)
            if not m:
                zone = None
                continue
            flags = {f.strip() for f in (m.group(2) or "").split(",") if f.strip()}
            zone = FirewallZone(
                name=m.group(1), active="active" in flags, is_default="default" in flags
            )
            zones.append(zone)
            in_rich = False
            continue
        if zone is None:
            continue
        key, sep, value = raw.strip().partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        in_rich = key == "rich rules"
        if in_rich:
            if value:
                zone.rich_rules.append(value)
        elif key == "target":
            zone.target = value or None
        elif key in _LIST_FIELDS:
            setattr(zone, _LIST_FIELDS[key], value.split())
        elif key in _BOOL_FIELDS:
            setattr(zone, _BOOL_FIELDS[key], _yes(value))
        else:
            zone.other[key] = value
    return zones


def zone_drift(runtime: List[FirewallZone], permanent: List[FirewallZone]) -> List[ZoneDrift]:
    """Settings where runtime differs from permanent (lost on reload/reboot)."""
    perm = {z.name: z for z in permanent}
    run = {z.name: z for z in runtime}
    fields = ["target", *(_LIST_FIELDS.values()), *(_BOOL_FIELDS.values()), "rich_rules"]
    drift: List[ZoneDrift] = []
    for name in sorted(set(run) | set(perm)):
        r, p = run.get(name), perm.get(name)
        if r is None or p is None:
            drift.append(ZoneDrift(
                zone=name, field="(zone)",
                runtime="present" if r else "absent",
                permanent="present" if p else "absent",
            ))
            continue
        for f in fields:
            rv, pv = getattr(r, f), getattr(p, f)
            if isinstance(rv, list):
                if sorted(rv) == sorted(pv):
                    continue
                rv, pv = " ".join(rv) or "-", " ".join(pv) or "-"
            elif rv == pv:
                continue
            drift.append(ZoneDrift(zone=name, field=f, runtime=str(rv), permanent=str(pv)))
    return drift


def parse_direct_rules(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


# --- iptables / nft / ipset / interfaces -------------------------------------------

_BUILTIN_CHAINS = {"INPUT", "OUTPUT", "FORWARD", "PREROUTING", "POSTROUTING"}


def parse_iptables_save(text: str) -> List[IptablesTable]:
    tables: List[IptablesTable] = []
    table: Optional[IptablesTable] = None
    for line in text.splitlines():
        if line.startswith("*"):
            table = IptablesTable(name=line[1:].strip())
            tables.append(table)
        elif table is None:
            continue
        elif line.startswith(":"):
            parts = line[1:].split()
            table.chains += 1
            if len(parts) >= 2 and parts[0] in _BUILTIN_CHAINS and parts[1] != "-":
                table.policies[parts[0]] = parts[1]
        elif line.startswith("-A "):
            table.rules += 1
        elif line.strip() == "COMMIT":
            table = None
    return tables


def iptables_backend(version_text: str) -> Optional[str]:
    m = re.search(r"\((legacy|nf_tables)\)", version_text)
    return m.group(1) if m else None


def count_ipsets(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith("Name:"))


def parse_interfaces(text: str) -> List[str]:
    """Interface names from `ip -o link show` ("2: eth0@if5: <...> ...")."""
    names = []
    for line in text.splitlines():
        parts = line.split(":", 2)
        if len(parts) >= 2 and parts[0].strip().isdigit():
            names.append(parts[1].strip().split("@", 1)[0])
    return names


def unassigned_interfaces(interfaces: List[str], zones: List[FirewallZone]) -> List[str]:
    bound = {i for z in zones for i in z.interfaces}
    return [i for i in interfaces if i != "lo" and not i.startswith("veth") and i not in bound]


# --- snapshot -----------------------------------------------------------------------


def _first_line(text: str) -> Optional[str]:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None


def command_results(
    outputs: Dict[str, Tuple[str, int]], commands: Iterable[FirewallCommand] = COMMANDS
) -> List[CommandResult]:
    results = []
    for c in commands:
        text, rc = outputs.get(c.id, ("", None))
        if rc is None:
            status = "error"
        elif rc == MISSING_EXIT_CODE:
            status = "missing"
        else:
            status = "ok" if rc in c.ok_exit_codes else "error"
        results.append(CommandResult(
            id=c.id, description=c.description, command=shlex.join(c.argv),
            exit_code=rc, status=status, file=c.file, output_bytes=len(text.encode()),
        ))
    return results


def build_snapshot(
    outputs: Dict[str, Tuple[str, int]],
    collected_at_utc: str,
    node: Optional[str] = None,
    collector_pod: Optional[str] = None,
) -> FirewallSnapshot:
    """Turn {command id: (output, exit code)} into the parsed snapshot."""
    commands = command_results(outputs)
    ok = {c.id for c in commands if c.status == "ok"}

    def text(cid: str) -> str:
        return outputs[cid][0] if cid in ok else ""

    status = FirewalldStatus(
        installed=any(c.id == "firewalld_version" and c.status != "missing" for c in commands),
        state=_first_line(text("firewalld_state")),
        version=_first_line(text("firewalld_version")),
        service_active=_first_line(text("firewalld_service_active")),
        service_enabled=_first_line(text("firewalld_service_enabled")),
        default_zone=_first_line(text("default_zone")),
        log_denied=_first_line(text("log_denied")),
    )
    for cid, attr in (("lockdown", "lockdown"), ("panic_mode", "panic_mode")):
        if cid in ok:
            setattr(status, attr, _first_line(outputs[cid][0]) == "yes")
    ipv6_enabled = outputs["ipv6_enabled"][1] == 0 if "ipv6_enabled" in ok else None

    zones = parse_zones(text("zones_runtime"))
    for z in zones:
        if status.default_zone and z.name == status.default_zone:
            z.is_default = True
    permanent = parse_zones(text("zones_permanent"))

    snap = FirewallSnapshot(
        collected_at_utc=collected_at_utc,
        node=node,
        collector_pod=collector_pod,
        firewalld=status,
        zones=zones,
        policies=parse_zones(text("policies_runtime")),
        direct_rules=parse_direct_rules(text("direct_rules")),
        drift=zone_drift(zones, permanent) if zones and permanent else [],
        unassigned_interfaces=unassigned_interfaces(
            parse_interfaces(text("interfaces")), zones
        ) if zones else [],
        iptables_backend=iptables_backend(text("iptables_version")),
        iptables_v4=parse_iptables_save(text("iptables_save")),
        iptables_v6=parse_iptables_save(text("ip6tables_save")),
        ipv6_enabled=ipv6_enabled,
        nft_ruleset_lines=sum(1 for line in text("nft_ruleset").splitlines() if line.strip()),
        ipset_count=count_ipsets(text("ipsets")),
        commands=commands,
    )
    for c in commands:
        if c.status == "error":
            detail = _first_line(outputs.get(c.id, ("", 0))[0]) or "no output"
            snap.errors.append(f"{c.command} failed (exit {c.exit_code}): {detail}")
    return snap


# --- printable report ---------------------------------------------------------------


def _list(values: List[str]) -> str:
    return ", ".join(values) if values else "-"


def _yn(value: Optional[bool]) -> str:
    return "-" if value is None else "yes" if value else "no"


def _zone_block(z: FirewallZone, kind: str) -> List[str]:
    flags = [f for f, on in (("default", z.is_default), ("active", z.active)) if on]
    out = [f"{kind} {z.name}" + (f" ({', '.join(flags)})" if flags else "")]
    head = f"  Target: {z.target or '-'}    Masquerade: {_yn(z.masquerade)}"
    if z.forward is not None:
        head += f"    Forward: {_yn(z.forward)}"
    out.append(head)
    for key, value in z.other.items():
        out.append(f"  {key + ':':<17}{value or '-'}")
    # Bindings and openings always print (an explicit "-" is informative);
    # the rest only when set, to keep the printout short.
    for label, values, always in (
        ("Interfaces", z.interfaces, kind == "ZONE"), ("Sources", z.sources, kind == "ZONE"),
        ("Services", z.services, True), ("Ports", z.ports, True),
        ("Protocols", z.protocols, False), ("Forward ports", z.forward_ports, False),
        ("Source ports", z.source_ports, False), ("ICMP blocks", z.icmp_blocks, False),
    ):
        if always or values:
            out.append(f"  {label + ':':<17}{_list(values)}")
    if z.icmp_block_inversion:
        out.append(f"  {'ICMP inversion:':<17}yes (ICMP blocks list what is allowed)")
    if z.rich_rules:
        out.append("  Rich rules:")
        out.extend(f"    {r}" for r in z.rich_rules)
    return out


def _tables_line(tables: List[IptablesTable]) -> List[str]:
    if not tables:
        return ["  (no tables / not collected)"]
    out = []
    for t in tables:
        pol = " ".join(f"{k}={v}" for k, v in t.policies.items())
        out.append(f"  {t.name:<8} {t.chains:>4} chains {t.rules:>5} rules   {pol}")
    return out


def render_report(snap: FirewallSnapshot) -> str:
    """Human-readable, printable summary (also written to firewall/report.txt)."""
    fw = snap.firewalld
    lines = [
        "FIREWALL SETTINGS",
        f"Node: {snap.node or '-'}",
        f"Collected (UTC): {snap.collected_at_utc}",
        "",
    ]
    if not fw.installed:
        lines.append("firewalld: not installed on this node")
    else:
        lines += [
            f"firewalld {fw.version or '?'}: {fw.state or 'unknown'}"
            f" (service {fw.service_active or '?'}, {fw.service_enabled or '?'} at boot)",
            f"Default zone: {fw.default_zone or '-'}    Log denied: {fw.log_denied or '-'}"
            f"    Lockdown: {_yn(fw.lockdown)}    Panic mode: {_yn(fw.panic_mode)}",
        ]
    lines.append(f"iptables backend: {snap.iptables_backend or 'unknown'}"
                 f"    nft ruleset lines: {snap.nft_ruleset_lines}"
                 f"    ipsets: {snap.ipset_count}")
    if snap.unassigned_interfaces and fw.default_zone:
        lines.append(f"Interfaces in no zone (default zone '{fw.default_zone}' applies): "
                     f"{_list(snap.unassigned_interfaces)}")
    lines.append("")

    detailed = [z for z in snap.zones if z.active or z.is_default or z.interfaces or z.sources]
    for z in detailed:
        lines += _zone_block(z, "ZONE") + [""]
    idle = [z.name for z in snap.zones if z not in detailed]
    if idle:
        lines += [f"Other zones (no interfaces or sources): {_list(idle)}", ""]

    if snap.policies:
        for p in snap.policies:
            lines += _zone_block(p, "POLICY") + [""]

    lines.append("DIRECT RULES: " + ("none" if not snap.direct_rules else ""))
    lines += [f"  {r}" for r in snap.direct_rules]
    lines.append("")

    if snap.drift:
        lines.append("RUNTIME vs PERMANENT (runtime changes lost on reload/reboot):")
        lines += [f"  {d.zone}.{d.field}: runtime={d.runtime}  permanent={d.permanent}"
                  for d in snap.drift]
    else:
        lines.append("RUNTIME vs PERMANENT: in sync")
    lines.append("")

    lines.append("IPTABLES (IPv4)")
    lines += _tables_line(snap.iptables_v4)
    lines.append("IPTABLES (IPv6)")
    if snap.ipv6_enabled is False:
        lines.append("  IPv6 is disabled in the kernel (no IPv6 rules apply)")
    else:
        lines += _tables_line(snap.iptables_v6)
    lines.append("")

    if snap.errors:
        lines.append("COLLECTION PROBLEMS")
        lines += [f"  {e}" for e in snap.errors]
        lines.append("")
    lines.append("Full command outputs are in firewall/*.txt; /etc/firewalld is under "
                 "firewall/etc/firewalld/.")
    return "\n".join(lines) + "\n"
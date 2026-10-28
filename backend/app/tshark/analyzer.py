
"""Analyze TShark packet metadata."""

import csv
import io
from collections import Counter


def analyze_capture(output: str) -> dict:
    reader = csv.DictReader(io.StringIO(output))

    packets = 0
    total_bytes = 0
    tcp_packets = 0
    resets = 0
    retransmissions = 0
    dns_failures = 0

    protocols = Counter()
    endpoints = Counter()

    for row in reader:
        packets += 1

        try:
            total_bytes += int(row.get("frame.len") or 0)
        except ValueError:
            pass

        protocol_stack = row.get("frame.protocols") or ""
        layers = protocol_stack.lower().split(":")

        if "dns" in layers:
            protocol = "DNS"
        elif "icmp" in layers:
            protocol = "ICMP"
        elif "icmpv6" in layers:
            protocol = "ICMPv6"
        elif "tcp" in layers:
            protocol = "TCP"
        elif "udp" in layers:
            protocol = "UDP"
        elif "arp" in layers:
            protocol = "ARP"
        elif "ip" in layers:
            protocol = "IPv4"
        elif "ipv6" in layers:
            protocol = "IPv6"
        else:
            protocol = "Unknown"

        protocols[protocol] += 1

        source = row.get("ip.src") or row.get("ipv6.src")
        destination = row.get("ip.dst") or row.get("ipv6.dst")

        if source:
            endpoints[source] += 1
        if destination:
            endpoints[destination] += 1

        if row.get("tcp.srcport") or row.get("tcp.dstport"):
            tcp_packets += 1

        if row.get("tcp.flags.reset") == "1":
            resets += 1

        if row.get("tcp.analysis.retransmission") == "1":
            retransmissions += 1

        if row.get("dns.flags.rcode") == "3":
            dns_failures += 1

    retransmission_rate = (
        round(retransmissions / tcp_packets * 100, 2)
        if tcp_packets else 0.0
    )

    return {
        "packetsAnalyzed": packets,
        "totalBytes": total_bytes,
        "tcpPackets": tcp_packets,
        "retransmissionRatePercent": retransmission_rate,
        "protocols": dict(protocols),
        "topEndpoints": [
            {"ip": ip, "packetOccurrences": count}
            for ip, count in endpoints.most_common(10)
        ],
        "diagnostics": [
            {
                "type": "TCP_RESET",
                "count": resets,
                "message": "TCP reset packets detected",
            },
            {
                "type": "TCP_RETRANSMISSION",
                "count": retransmissions,
                "message": "Possible TCP retransmissions detected",
            },
            {
                "type": "DNS_NXDOMAIN",
                "count": dns_failures,
                "message": "DNS name-not-found responses detected",
            },
        ],
    }

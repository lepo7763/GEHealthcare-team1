
import csv
import io


def analyze_capture(output: str) -> dict:
    reader = csv.DictReader(io.StringIO(output))

    packets = 0
    resets = 0
    retransmissions = 0
    dns_failures = 0

    for row in reader:
        packets += 1

        if row.get("tcp.flags.reset") == "1":
            resets += 1

        if row.get("tcp.analysis.retransmission") == "1":
            retransmissions += 1

        if row.get("dns.flags.rcode") == "3":
            dns_failures += 1

    return {
        "packetsAnalyzed": packets,
        "diagnostics": [
            {
                "type": "TCP_RESET",
                "count": resets,
                "message": "TCP reset packets detected",
            },
            {
                "type": "TCP_RETRANSMISSION",
                "count": retransmissions,
                "message": "Possible network retransmissions detected",
            },
            {
                "type": "DNS_NXDOMAIN",
                "count": dns_failures,
                "message": "DNS name-not-found responses detected",
            },
        ],
    }

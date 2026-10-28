
"""Run TShark in a Kubernetes pod and analyze the results."""

from datetime import datetime, timezone

from kubernetes import client
from kubernetes.stream import stream

from app.tshark.analyzer import analyze_capture
from app.tshark.config import (
    TSHARK_NAMESPACE,
    TSHARK_POD,
    TSHARK_CONTAINER,
    TSHARK_INTERFACE,
    TSHARK_DURATION,
    TSHARK_MAX_DURATION,
    TSHARK_MAX_PACKETS,
    TSHARK_REQUEST_TIMEOUT,
)


def capture_network(
    core: client.CoreV1Api,
    duration: int | None = None,
) -> dict:
    capture_duration = (
        TSHARK_DURATION if duration is None else duration
    )

    if not 1 <= capture_duration <= TSHARK_MAX_DURATION:
        raise ValueError(
            f"Capture duration must be between "
            f"1 and {TSHARK_MAX_DURATION} seconds."
        )

    command = [
        "tshark",
        "-i", TSHARK_INTERFACE,
        "-p",
        "-n",
        "-a", f"duration:{capture_duration}",
        "-c", str(TSHARK_MAX_PACKETS),
        "-T", "fields",
        "-E", "separator=,",
        "-E", "header=y",
        "-E", "quote=d",
        "-e", "frame.len",
        "-e", "frame.protocols",
        "-e", "ip.src",
        "-e", "ip.dst",
        "-e", "ipv6.src",
        "-e", "ipv6.dst",
        "-e", "tcp.srcport",
        "-e", "tcp.dstport",
        "-e", "tcp.flags.reset",
        "-e", "tcp.analysis.retransmission",
        "-e", "dns.flags.rcode",
    ]

    started_at = datetime.now(timezone.utc)

    output = stream(
        core.connect_get_namespaced_pod_exec,
        TSHARK_POD,
        TSHARK_NAMESPACE,
        command=command,
        container=TSHARK_CONTAINER,
        stderr=False,
        stdin=False,
        stdout=True,
        tty=False,
        _request_timeout=TSHARK_REQUEST_TIMEOUT,
    )

    finished_at = datetime.now(timezone.utc)

    result = analyze_capture(output)

    return {
        "status": "completed",
        "namespace": TSHARK_NAMESPACE,
        "pod": TSHARK_POD,
        "interface": TSHARK_INTERFACE,
        "durationSeconds": capture_duration,
        "startedAt": started_at.isoformat(),
        "finishedAt": finished_at.isoformat(),
        "captureLimits": {
            "maxPackets": TSHARK_MAX_PACKETS,
            "maxDurationSeconds": TSHARK_MAX_DURATION,
        },
        **result,
    }

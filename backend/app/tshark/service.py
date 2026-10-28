# own the capture lifecycle: create workload, wait, retrieve output, package it, and clean up
from kubernetes import client
from kubernetes.stream import stream

from app.tshark.analyzer import analyze_capture

NAMESPACE = "iomt-dev-2"
POD_NAME = "tshark-test"
DURATION = 10


def capture_network(core: client.CoreV1Api) -> dict:
    command = [
        "tshark",
        "-i", "eth0",
        "-p",
        "-n",
        "-a", f"duration:{DURATION}",
        "-T", "fields",
        "-E", "separator=,",
        "-E", "header=y",
        "-e", "ip.src",
        "-e", "ip.dst",
        "-e", "tcp.flags.reset",
        "-e", "tcp.analysis.retransmission",
        "-e", "dns.flags.rcode",
    ]

    output = stream(
        core.connect_get_namespaced_pod_exec,
        POD_NAME,
        NAMESPACE,
        command=command,
        container="tshark-test",
        stderr=False,
        stdin=False,
        stdout=True,
        tty=False,
        _request_timeout=DURATION + 20,
    )

    result = analyze_capture(output)

    return {
        "status": "completed",
        "namespace": NAMESPACE,
        "pod": POD_NAME,
        "durationSeconds": DURATION,
        **result,
    }

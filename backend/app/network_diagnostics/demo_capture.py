
import base64
import io
import ipaddress
import logging
import uuid
import zipfile

from fastapi import HTTPException
from kubernetes import client
from kubernetes.stream import stream

from .service import ensure_netshoot_ready, read_running_pod


NAMESPACE = "iomt-dev-1"
DEMO_PODS = ("http-test-1", "http-test-2")
NETSHOOT_CONTAINER = "netshoot-capture"

logger = logging.getLogger(__name__)

PCAP_SIGNATURES = {
    bytes.fromhex("d4c3b2a1"),
    bytes.fromhex("a1b2c3d4"),
    bytes.fromhex("4d3cb2a1"),
    bytes.fromhex("a1b23c4d"),
}


def execute_netshoot(pod_name: str, command: list[str],
                     stderr: bool = False) -> str:
    try:
        # Use a fresh client for each WebSocket exec call.
        exec_api = client.CoreV1Api()

        return stream(
            exec_api.connect_post_namespaced_pod_exec,
            pod_name,
            NAMESPACE,
            container=NETSHOOT_CONTAINER,
            command=command,
            stderr=stderr,
            stdin=False,
            stdout=True,
            tty=False,
            _request_timeout=20,
        )
    except Exception as exc:
        logger.exception("Netshoot exec failed for %s", pod_name)
        raise HTTPException(
            status_code=502,
            detail=f"Unable to execute diagnostics in {pod_name}",
        ) from exc


def capture_pcap(pod_name: str, peer_ip: str) -> bytes:
    # Accept only a valid IP address returned by Kubernetes.
    try:
        address = ipaddress.ip_address(peer_ip)
    except ValueError as exc:
        raise HTTPException(503, "Invalid peer pod IP") from exc

    host = f"[{address}]" if address.version == 6 else str(address)

    # Use a unique filename so repeated requests cannot reuse old data.
    filename = f"/tmp/iomt-{uuid.uuid4().hex}.pcap"
    logfile = f"{filename}.log"

    script = f"""
set -e

timeout 6 tcpdump -i eth0 -nn -s 0 -U -c 100 \
    -w {filename} "tcp port 8080" \
    > {logfile} 2>&1 &

capture_pid=$!
sleep 1

curl -fsS --max-time 3 http://{host}:8080/ > /dev/null

wait "$capture_pid" || [ "$?" -eq 124 ]

test -s {filename}
echo CAPTURE_OK
"""

    result = execute_netshoot(
        pod_name, ["sh", "-c", script], stderr=True
    )

    if "CAPTURE_OK" not in result:
        raise HTTPException(
            status_code=502,
            detail=f"Packet capture failed for {pod_name}",
        )

    encoded = execute_netshoot(
        pod_name, ["base64", filename]
    )

    try:
        pcap = base64.b64decode(
            "".join(encoded.split()), validate=True
        )
    except (ValueError, base64.binascii.Error) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Invalid PCAP transfer from {pod_name}",
        ) from exc

    if len(pcap) <= 24 or pcap[:4] not in PCAP_SIGNATURES:
        raise HTTPException(
            status_code=502,
            detail=f"Invalid PCAP data from {pod_name}",
        )

    return pcap


def capture_demo_zip(v1: client.CoreV1Api) -> bytes:
    # Check both pods and retrieve their current IP addresses.
    pod_ips = {}

    for pod_name in DEMO_PODS:
        pod = read_running_pod(v1, pod_name, NAMESPACE)

        if not pod.status.pod_ip:
            raise HTTPException(
                status_code=503,
                detail=f"No IP assigned to {pod_name}",
            )

        pod_ips[pod_name] = pod.status.pod_ip

    archive_buffer = io.BytesIO()

    with zipfile.ZipFile(
        archive_buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for pod_name in DEMO_PODS:
            # Attach Netshoot if missing, otherwise reuse it.
            ensure_netshoot_ready(v1, pod_name, NAMESPACE)

            peer_name = next(
                name for name in DEMO_PODS if name != pod_name
            )

            pcap = capture_pcap(
                pod_name, pod_ips[peer_name]
            )

            archive.writestr(f"{pod_name}.pcap", pcap)

    return archive_buffer.getvalue()

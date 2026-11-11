
import json
import subprocess


CRI_ENDPOINT = "unix:///run/k3s/containerd/containerd.sock"


def find_ready_sandbox_id(
    pod_uid: str,
    sandboxes: list[dict],
) -> str:
    """Find the active sandbox for a Kubernetes Pod UID."""

    matches = []

    for sandbox in sandboxes:
        metadata = sandbox.get("metadata") or {}

        if metadata.get("uid") != pod_uid:
            continue

        if sandbox.get("state") != "SANDBOX_READY":
            continue

        matches.append(sandbox)

    if len(matches) != 1:
        raise ValueError(
            f"Expected one ready sandbox for pod {pod_uid}, "
            f"found {len(matches)}"
        )

    sandbox_id = matches[0].get("id")

    if not sandbox_id:
        raise ValueError("Ready sandbox has no ID")

    return sandbox_id


def extract_sandbox_pid(inspection: dict) -> int:
    """Extract a valid host PID from a sandbox inspection."""

    info = inspection.get("info") or {}
    pid = info.get("pid")

    if type(pid) is not int or pid <= 0:
        raise ValueError(
            "Sandbox inspection did not contain a valid host PID"
        )

    return pid


def resolve_pod_pid(pod_uid: str, namespace: str) -> int:
    """Resolve a Pod UID to its current sandbox host PID."""

    if not pod_uid or not namespace:
        raise ValueError("Pod UID and namespace are required")

    base_command = [
        "crictl",
        "--runtime-endpoint",
        CRI_ENDPOINT,
    ]

    result = subprocess.run(
        base_command + [
            "pods", "--namespace", namespace, "-o", "json"
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )

    sandboxes = json.loads(result.stdout).get("items", [])
    sandbox_id = find_ready_sandbox_id(pod_uid, sandboxes)

    result = subprocess.run(
        base_command + ["inspectp", sandbox_id],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )

    inspection = json.loads(result.stdout)

    return extract_sandbox_pid(inspection)

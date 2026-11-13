
"""Discover Portrait Mobile pods through Kubernetes."""

from kubernetes import client


def discover_pm_pods(core: client.CoreV1Api) -> list[dict]:
    response = core.list_namespaced_pod(namespace="pm")

    return [
        {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "ip": pod.status.pod_ip,
            "status": pod.status.phase,
            "node": pod.spec.node_name,
        }
        for pod in response.items
    ]

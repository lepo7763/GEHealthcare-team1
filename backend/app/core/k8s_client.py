from kubernetes import client, config
from fastapi import HTTPException


def _load_k8s_config() -> None:
    """
    Loads K8s configuration into the default client.
    Tries local ~/.kube/config first (for workstation dev), then falls back to
    in-cluster service account config.
    """
    try:
        config.load_kube_config()
    except config.ConfigException:
        try:
            config.load_incluster_config()
        except config.ConfigException as e:
            raise HTTPException(
                status_code=503,
                detail=f"Could not connect to Kubernetes cluster: {str(e)}",
            )


def get_core_v1_api() -> client.CoreV1Api:
    """Returns a CoreV1Api client for Pods, Logs, Services, ConfigMaps, and Secrets."""
    _load_k8s_config()
    return client.CoreV1Api()


def get_batch_v1_api() -> client.BatchV1Api:
    """Returns a BatchV1Api client for creating, polling, and deleting Kubernetes Jobs."""
    _load_k8s_config()
    return client.BatchV1Api()
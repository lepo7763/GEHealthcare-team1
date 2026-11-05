from kubernetes import client, config
from fastapi import HTTPException


def _load_config() -> None:
    """Loads the Kubernetes configuration from the local kubeconfig."""
    try:
        config.load_kube_config()
    except config.ConfigException as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to Kubernetes cluster: {str(e)}",
        ) from e


def get_core_v1_api() -> client.CoreV1Api:
    """Core (pods, logs, services, config maps, secrets) client."""
    _load_config()
    return client.CoreV1Api()


def get_batch_v1_api() -> client.BatchV1Api:
    """Batch (Jobs) client used by the UMF RTI capture service."""
    _load_config()
    return client.BatchV1Api()

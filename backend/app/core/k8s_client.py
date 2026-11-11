from kubernetes import client, config
from fastapi import HTTPException
import os



def _load_config() -> None:
    """Load Kubernetes configuration for local or in-cluster execution."""
    try:
        if os.environ.get("KUBERNETES_SERVICE_HOST"):
            config.load_incluster_config()
        else:
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

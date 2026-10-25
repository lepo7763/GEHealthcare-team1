from kubernetes import client, config
from fastapi import HTTPException


def _load_config() -> None:
    """
    Loads K8s configuration, preferring local kubeconfig (for laptop dev) and
    falling back to in-cluster credentials.
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
    """Core (pods, logs, services, config maps, secrets) client."""
    _load_config()
    return client.CoreV1Api()


def get_batch_v1_api() -> client.BatchV1Api:
    """Batch (Jobs) client used by the UMF RTI capture service."""
    _load_config()
    return client.BatchV1Api()

from kubernetes import client, config
from fastapi import HTTPException


def get_core_v1_api() -> client.CoreV1Api:
    """
    Loads K8s configuration and returns a CoreV1Api client.
    Tries local kubeconfig first (for laptop dev), then falls back to in-cluster.
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
    return client.CoreV1Api()


get_core_v1_api()

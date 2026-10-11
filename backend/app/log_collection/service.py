import time
import zipfile
import tempfile
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from .schemas import LogCollectionParams, LogCollectionManifest, LogErrorEntry


def _get_pod_targets(pod: client.V1Pod) -> List[Tuple[str, bool]]:
    """
    Extracts all container names from a pod and checks if they have restarted.
    Returns a list of (container_name, has_restarted) tuples.
    """
    containers = (
        (pod.spec.containers or [])
        + (pod.spec.init_containers or [])
        + (pod.spec.ephemeral_containers or [])
    )

    restarted_containers = set()
    for status_list in [
        pod.status.container_statuses,
        pod.status.init_container_statuses,
        pod.status.ephemeral_container_statuses,
    ]:
        for status in status_list or []:
            if (status.restart_count or 0) > 0:
                restarted_containers.add(status.name)

    return [(c.name, c.name in restarted_containers) for c in containers]

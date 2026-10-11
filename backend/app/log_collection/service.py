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
                # If restart_count > 0, it means the container crashed or exited at least once,
                # so Kubernetes is holding onto a previous log that could explain the crash.
                restarted_containers.add(status.name)

    return [(c.name, c.name in restarted_containers) for c in containers]


def _fetch_single_log(
    v1: client.CoreV1Api,
    namespace: str,
    pod_name: str,
    container_name: str,
    params: LogCollectionParams,
    previous: bool = False,
) -> Tuple[Optional[str], Optional[LogErrorEntry]]:
    """
    Fetches a single container log from K8s.
    Returns (log_text, None) on success, or (None, LogErrorEntry) on failure.
    """
    try:
        log_text = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container_name,
            previous=previous,
            limit_bytes=params.max_bytes_per_container,
            tail_lines=params.tail_lines,
            timestamps=True,
            _request_timeout=15,
        )
        # `or ""` in case container hasn't printed anything yet. API returns None
        #  We want string for zipfile.writestr, not None
        return (log_text or "", None)
    except ApiException as e:
        return (
            None,
            LogErrorEntry(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                reason=e.reason or "ApiException",
                status=e.status,
            ),
        )
    except Exception as e:
        return (
            None,
            LogErrorEntry(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                reason=str(e),
            ),
        )


def _process_pod(
    v1: client.CoreV1Api,
    pod: client.V1Pod,
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    params: LogCollectionParams,
) -> None:
    """Collects and zips all container logs for a single pod."""
    ns = pod.metadata.namespace
    pod_name = pod.metadata.name

    for c_name, has_restarted in _get_pod_targets(pod):
        # Fetch current logs for this container
        log_text, err = _fetch_single_log(
            v1, ns, pod_name, c_name, params, previous=False
        )

        if err:
            # Record why we couldn't get this container's log in manifest.json
            manifest.errors.append(err)
        else:
            path = f"logs/{ns}/{pod_name}/{c_name}.log"
            zf.writestr(path, log_text)
            manifest.collected_files.append(path)

        # If the container restarted earlier, also grab the log from right before it crashed
        if params.include_previous and has_restarted:
            # '_' for the error because k8s might've garbage collected old log.
            # No problem, probably shouldn't pollute manifest with this
            prev_text, _ = _fetch_single_log(
                v1, ns, pod_name, c_name, params, previous=True
            )
            if prev_text is not None:
                prev_path = f"logs/{ns}/{pod_name}/{c_name}_previous.log"
                zf.writestr(prev_path, prev_text)
                manifest.collected_files.append(prev_path)

        # stall a little to avoid spiking CPU/disk I/O. Server is already in bad shape
        if params.throttle_delay_ms > 0:
            time.sleep(params.throttle_delay_ms / 1000.0)

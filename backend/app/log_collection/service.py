import time
import zipfile
import tempfile
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from .schemas import LogCollectionParams, LogCollectionManifest, LogErrorEntry


class ClusterUnreachableError(Exception):
    """Raised when the initial connection or pod listing to the K8s cluster fails."""

    pass


def _get_pod_targets(pod: client.V1Pod) -> List[Tuple[str, bool]]:
    """
    Extracts all container names from a pod and checks if they have restarted.
    Returns a list of (container_name, has_restarted) tuples.
    """
    spec = pod.spec
    if not spec:
        return []

    containers = (
        (spec.containers or [])
        + (spec.init_containers or [])
        + (spec.ephemeral_containers or [])
    )

    restarted_containers: set[str] = set()
    status = pod.status
    if status:
        for status_list in [
            status.container_statuses,
            status.init_container_statuses,
            status.ephemeral_container_statuses,
        ]:
            for st in status_list or []:
                if (st.restart_count or 0) > 0:
                    # If restart_count > 0, it means the container crashed or exited at least once,
                    # so Kubernetes is holding onto a previous log that could explain the crash.
                    restarted_containers.add(st.name)

    return [(c.name, c.name in restarted_containers) for c in containers if c.name]


def _fetch_single_log(
    v1: client.CoreV1Api,
    namespace: str,
    pod_name: str,
    container_name: str,
    params: LogCollectionParams,
    previous: bool = False,
) -> Tuple[str, Optional[LogErrorEntry]]:
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
            "",
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
            "",
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
    if not pod.metadata or not pod.metadata.namespace or not pod.metadata.name:
        return

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
            if params.include_previous and has_restarted:
                prev_text, prev_err = _fetch_single_log(
                    v1, ns, pod_name, c_name, params, previous=True
                )
                if (
                    not prev_err
                ):  # Only write the file if the K8s call actually succeeded
                    prev_path = f"logs/{ns}/{pod_name}/{c_name}_previous.log"
                    zf.writestr(prev_path, prev_text)
                    manifest.collected_files.append(prev_path)

        # stall a little to avoid spiking CPU/disk I/O. Server is already in bad shape
        if params.throttle_delay_ms > 0:
            time.sleep(params.throttle_delay_ms / 1000.0)


# TODO: works, but is synchronous so will crash if UI locks. Also idk how to track progress
def collect_all_cluster_logs(
    v1: client.CoreV1Api, params: LogCollectionParams
) -> tempfile.SpooledTemporaryFile:
    """High-level entry point: queries pods, zips all logs, and writes manifest.

    WHY `SpooledTemporaryFile` INSTEAD OF `io.BytesIO` OR A REGULAR FILE:
    - `io.BytesIO` keeps everything in RAM. If a cluster has too many logs, backend crashes (OOM).
    - A normal disk file is slower for small zips and leaves leftover files if you forget to delete it.
    - `SpooledTemporaryFile` stays in fast RAM up to set limit, and automatically spills
      over to an invisible temporary file on disk if the zip grows larger than limit
    """
    try:
        pods = v1.list_pod_for_all_namespaces(watch=False, _request_timeout=10).items
    except Exception as e:
        raise ClusterUnreachableError(f"Failed to query Kubernetes cluster: {e}") from e

    temp_zip = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024, mode="w+b")

    # Initialize our tracking manifest with an ISO-8601 UTC timestamp
    manifest = LogCollectionManifest(
        timestamp_utc=datetime.now(timezone.utc).isoformat(), total_logs_collected=0
    )

    # Without `compression=zipfile.ZIP_DEFLATED`, Python's zipfile module just stores raw uncompressed files.
    # Plain text log files are super repetitive and compress a lot using standard DEFLATE.
    with zipfile.ZipFile(temp_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pod in pods:
            _process_pod(v1, pod, zf, manifest, params)

        manifest.total_logs_collected = len(manifest.collected_files)
        zf.writestr("manifest.json", manifest.model_dump_json(indent=2))

    # If we pass to FastAPI's StreamingResponse without seeking to start,
    # FastAPI will read from the end and send a 0-byte empty file.
    temp_zip.seek(0)
    return temp_zip

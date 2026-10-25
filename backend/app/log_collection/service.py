import time
import zipfile
import tempfile
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from .schemas import (
    CollectedService,
    LogCollectionManifest,
    LogCollectionParams,
    LogErrorEntry,
)
from .progress import (
    CONTAINER_LOGS_LABEL,
    CONTAINER_LOGS_SERVICE_ID,
    ServiceProgress,
    tracker,
)


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
                service=CONTAINER_LOGS_SERVICE_ID,
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
                service=CONTAINER_LOGS_SERVICE_ID,
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
        current = f"{ns}/{pod_name}/{c_name}"
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

        tracker.increment_service(
            CONTAINER_LOGS_SERVICE_ID, current=current, had_error=bool(err)
        )

        # If the container restarted earlier, also grab the log from right before it crashed
        if params.include_previous and has_restarted:
            prev_text, prev_err = _fetch_single_log(
                v1, ns, pod_name, c_name, params, previous=True
            )
            # Only write the file if the K8s call actually succeeded.
            # We don't append prev_err to manifest.errors because k8s might've garbage collected the old log.
            if not prev_err:
                prev_path = f"logs/{ns}/{pod_name}/{c_name}_previous.log"
                zf.writestr(prev_path, prev_text)
                manifest.collected_files.append(prev_path)

        # stall a little to avoid spiking CPU/disk I/O. Server is already in bad shape
        if params.throttle_delay_ms > 0:
            time.sleep(params.throttle_delay_ms / 1000.0)


def collect_container_logs_into(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    v1: client.CoreV1Api,
    params: LogCollectionParams,
) -> List[str]:
    """Collect container logs into an existing zip/manifest.

    The caller (the diagnostics orchestrator) owns the zip, manifest and
    progress lifecycle.  Returns the paths this service wrote.
    """
    files_before = len(manifest.collected_files)

    try:
        pods = v1.list_pod_for_all_namespaces(watch=False, _request_timeout=10).items
    except Exception as e:
        raise ClusterUnreachableError(f"Failed to query Kubernetes cluster: {e}") from e

    containers_total = sum(len(_get_pod_targets(pod)) for pod in pods)
    tracker.set_service_total(
        CONTAINER_LOGS_SERVICE_ID, containers_total, unit="containers"
    )

    for pod in pods:
        _process_pod(v1, pod, zf, manifest, params)

    return manifest.collected_files[files_before:]


def collect_all_cluster_logs(
    v1: client.CoreV1Api, params: LogCollectionParams
) -> tempfile.SpooledTemporaryFile:
    """Backward-compatible single-service entry point.

    The diagnostics endpoint uses the orchestrator in app.diagnostics.service,
    but keeping this wrapper makes the log-collection service usable on its own
    and preserves the original tests/API contract.
    """
    tracker.begin(
        [ServiceProgress(id=CONTAINER_LOGS_SERVICE_ID, label=CONTAINER_LOGS_LABEL)]
    )
    try:
        temp_zip = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024, mode="w+b")
        manifest = LogCollectionManifest(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            total_logs_collected=0,
        )
        with zipfile.ZipFile(temp_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            files = collect_container_logs_into(zf, manifest, v1, params)
            manifest.services.append(
                CollectedService(
                    id=CONTAINER_LOGS_SERVICE_ID,
                    label=CONTAINER_LOGS_LABEL,
                    status="done",
                    files=files,
                )
            )
            manifest.total_logs_collected = len(manifest.collected_files)
            zf.writestr("manifest.json", manifest.model_dump_json(indent=2))
        temp_zip.seek(0)
        tracker.finish()
        return temp_zip
    except Exception as e:
        tracker.fail(str(e))
        raise

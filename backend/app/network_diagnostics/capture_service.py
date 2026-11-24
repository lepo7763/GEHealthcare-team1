from time import monotonic, sleep
from kubernetes import client
from .job_service import DIAGNOSTICS_NAMESPACE
from kubernetes.stream import stream
from kubernetes.client.exceptions import ApiException
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from .job_service import schedule_capture_jobs

import base64
import hashlib
import tempfile
import zipfile
import logging

from pathlib import Path

logger = logging.getLogger(__name__)

ARCHIVE_PATH = "/captures/job-artifacts.zip"
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024

class NetshootCaptureError(RuntimeError):
    """Raised when a Natshoot capture can't be collected"""


def wait_for_worker_pod(
    core_api: client.CoreV1Api,
    job_name: str,
    timeout_seconds: int = 60,
    poll_interval: float = 1.0,
) -> str:
    """Find the worker Pod belonging to a Netshoot Job."""

    deadline = monotonic() + timeout_seconds

    selector = f"batch.kubernetes.io/job-name={job_name}"

    while monotonic() < deadline:
        response = core_api.list_namespaced_pod(
            namespace=DIAGNOSTICS_NAMESPACE,
            label_selector=selector,
            _request_timeout=10,
        )

        for pod in response.items:
            if pod.status.phase == "Running":
                return pod.metadata.name

            if pod.status.phase in ("Failed", "Succeeded"):
                raise NetshootCaptureError(
                    f"Worker Pod {pod.metadata.name} "
                    f"terminated before retrieval: {pod.status.phase}"
                )

        sleep(poll_interval)

    raise NetshootCaptureError(
        f"Worker Pod for Job {job_name} did not start in time"
    )

def wait_for_archive(
    core_api: client.CoreV1Api,
    pod_name: str,
    timeout_seconds: int = 180,
    poll_interval: float = 1.0,
) -> None:
    """Wait until the worker signals that its ZIP is ready."""

    deadline = monotonic() + timeout_seconds

    while monotonic() < deadline:
        pod = core_api.read_namespaced_pod(
            name=pod_name,
            namespace=DIAGNOSTICS_NAMESPACE,
            _request_timeout=10,
        )

        if pod.status.phase in ("Failed", "Succeeded"):
            raise NetshootCaptureError(
                f"Worker Pod {pod_name} terminated before retrieval"
            )

        if pod.status.phase == "Running":
            try:
                output = stream(
                    core_api.connect_get_namespaced_pod_exec,
                    pod_name,
                    DIAGNOSTICS_NAMESPACE,
                    container="netshoot",
                    command=[
                        "sh",
                        "-c",
                        "if [ -f /captures/.done ] && "
                        "[ -f /captures/job-artifacts.zip ]; then "
                        "echo NETSHOOT_ARCHIVE_READY; fi",
                    ],
                    stderr=False,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=True,
                    _request_timeout=10,
                )

                if output.strip() == "NETSHOOT_ARCHIVE_READY":
                    return

            except ApiException as exc:
                if exc.status not in (400, 409, 429, 500, 502, 503, 504):
                    raise NetshootCaptureError(
                        f"Unable to inspect worker Pod {pod_name}"
                    ) from exc

        sleep(poll_interval)

    raise NetshootCaptureError(
        f"Timed out waiting for archive from Pod {pod_name}"
    )

def exec_worker_command(
    core_api: client.CoreV1Api,
    pod_name: str,
    command: list[str],
) -> str:
    """Execute a command inside the Netshoot worker."""

    try:
        return stream(
            core_api.connect_get_namespaced_pod_exec,
            pod_name,
            DIAGNOSTICS_NAMESPACE,
            container="netshoot",
            command=command,
            stderr=False,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=True,
            _request_timeout=10,
        )

    except ApiException as exc:
        raise NetshootCaptureError(
            f"Unable to execute command in worker {pod_name}"
        ) from exc

def retrieve_capture_archive(
    core_api: client.CoreV1Api,
    pod_name: str,
    destination: Path,
    max_bytes: int = MAX_ARCHIVE_BYTES,
    chunk_bytes: int = CHUNK_BYTES,
    timeout_seconds: int = 300,
) -> Path:
    """Retrieve and validate a completed capture archive."""

    deadline = monotonic() + timeout_seconds

    metadata = exec_worker_command(
        core_api,
        pod_name,
        [
            "sh", "-ec",
            f"stat -c %s {ARCHIVE_PATH}; "
            f"sha256sum {ARCHIVE_PATH}",
        ],
    )

    try:
        fields = metadata.split()
        archive_size = int(fields[0])
        expected_hash = fields[1]

    except (ValueError, IndexError) as exc:
        raise NetshootCaptureError(
            "Invalid archive metadata"
        ) from exc

    if not 0 < archive_size <= max_bytes:
        raise NetshootCaptureError(
            f"Archive size exceeds allowed limits: {archive_size}"
        )

    if chunk_bytes <= 0:
        raise ValueError("Chunk size must be positive")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None
    checksum = hashlib.sha256()

    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            suffix=".partial",
            delete=False,
        ) as temporary:

            temporary_path = Path(temporary.name)

            for offset in range(0, archive_size, chunk_bytes):

                if monotonic() >= deadline:
                    raise NetshootCaptureError(
                        "Archive retrieval timed out"
                    )

                length = min(
                    chunk_bytes,
                    archive_size - offset,
                )

                encoded = exec_worker_command(
                    core_api,
                    pod_name,
                    [
                        "python3", "-c",
                        "import sys, base64\n"
                        "with open(sys.argv[1], 'rb') as f:\n"
                        "    f.seek(int(sys.argv[2]))\n"
                        "    data = f.read(int(sys.argv[3]))\n"
                        "    print(base64.b64encode(data).decode())",
                        ARCHIVE_PATH,
                        str(offset),
                        str(length),
                    ],
                )

                decoded = base64.b64decode(
                    encoded.strip(),
                    validate=True,
                )

                if len(decoded) != length:
                    raise NetshootCaptureError(
                        "Incomplete archive chunk"
                    )

                temporary.write(decoded)
                checksum.update(decoded)

        if checksum.hexdigest() != expected_hash:
            raise NetshootCaptureError(
                "Archive checksum mismatch"
            )

        with zipfile.ZipFile(temporary_path, "r") as archive:
            if "manifest.json" not in archive.namelist():
                raise NetshootCaptureError(
                    "Capture manifest missing"
                )

            if archive.testzip() is not None:
                raise NetshootCaptureError(
                    "Archive contains corrupted files"
                )

        temporary_path.replace(destination)

        return destination

    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise NetshootCaptureError(
            f"Unable to retrieve archive from {pod_name}"
        ) from exc

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

def collect_worker_archive(
    core_api: client.CoreV1Api,
    job_name: str,
    destination: Path,
    duration_seconds: int,
) -> Path:
    """Collect the completed ZIP from a single Netshoot Job."""

    pod_name = wait_for_worker_pod(
        core_api,
        job_name,
    )

    wait_for_archive(
        core_api,
        pod_name,
        timeout_seconds=duration_seconds + 120,
    )

    return retrieve_capture_archive(
        core_api,
        pod_name,
        destination,
    )

def collect_worker_archive_independent(
    configuration: client.Configuration,
    job_name: str,
    destination: Path,
    duration_seconds: int,
) -> Path:
    """Collect a worker archive using an independent API client."""

    with client.ApiClient(
        configuration=deepcopy(configuration)
    ) as api_client:

        core_api = client.CoreV1Api(api_client)

        return collect_worker_archive(
            core_api,
            job_name,
            destination,
            duration_seconds,
        )

def collect_worker_archives(
    core_api: client.CoreV1Api,
    jobs_by_node: dict,
    destination_dir: Path,
    duration_seconds: int,
) -> tuple[dict[str, Path], dict[str, str]]:
    """Retrieve archives from scheduled workers concurrently."""

    archives = {}
    errors = {}

    if not jobs_by_node:
        return archives, errors

    configuration = core_api.api_client.configuration

    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(
        max_workers=len(jobs_by_node)
    ) as executor:

        futures = {}

        for node_name, job in jobs_by_node.items():
            job_name = job["job_name"]

            future = executor.submit(
                collect_worker_archive_independent,
                configuration,
                job_name,
                destination_dir / f"{job_name}.zip",
                duration_seconds,
            )

            futures[future] = node_name

        for future in as_completed(futures):
            node_name = futures[future]

            try:
                archives[node_name] = future.result()

            except NetshootCaptureError as exc:
                errors[node_name] = str(exc)

            except ApiException as exc:
                errors[node_name] = (
                    f"Kubernetes API error: {exc.status}"
                )

    return archives, errors

def cleanup_capture_jobs(
    batch_api: client.BatchV1Api,
    jobs_by_node: dict,
) -> dict[str, str]:
    """Request deletion of all Jobs from a capture session."""

    errors = {}

    for job in jobs_by_node.values():
        job_name = job["job_name"]

        try:
            batch_api.delete_namespaced_job(
                name=job_name,
                namespace=DIAGNOSTICS_NAMESPACE,
                propagation_policy="Foreground",
                _request_timeout=10,
            )

        except ApiException as exc:
            if exc.status != 404:
                errors[job_name] = (
                    f"Kubernetes API error: {exc.status}"
                )
                logger.exception(
                    "Could not delete Netshoot Job %s",
                    job_name,
                )

        except Exception:
            errors[job_name] = "Unexpected cleanup failure"
            logger.exception(
                "Could not delete Netshoot Job %s",
                job_name,
            )

    return errors

def collect_netshoot_captures(
    core_api: client.CoreV1Api,
    batch_api: client.BatchV1Api,
    namespaces: list[str] | None,
    destination_dir: Path,
    duration_seconds: int = 30,
    scope: str = "both",
) -> tuple[
    dict[str, Path],
    dict[str, str],
    dict[str, str],
]:
    """Schedule, collect, and clean up a Netshoot session."""

    jobs_by_node = schedule_capture_jobs(
        core_api=core_api,
        batch_api=batch_api,
        namespaces=namespaces,
        duration_seconds=duration_seconds,
        scope = scope,
    )

    if not jobs_by_node:
        raise NetshootCaptureError(
            "No eligible running Pods found"
        )

    try:
        archives, errors = collect_worker_archives(
            core_api,
            jobs_by_node,
            destination_dir,
            duration_seconds,
        )

    finally:
        cleanup_errors = cleanup_capture_jobs(
            batch_api,
            jobs_by_node,
        )

    return archives, errors, cleanup_errors
"""Orchestrates the selected diagnostic services into one zip package."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import List, Optional

from app.log_collection.progress import (
    CONTAINER_LOGS_LABEL,
    CONTAINER_LOGS_SERVICE_ID,
    TSHARK_LABEL,
    TSHARK_SERVICE_ID,
    UMF_RTI_LABEL,
    UMF_RTI_SERVICE_ID,
    ServiceProgress,
    tracker,
)
from app.log_collection.schemas import (
    CollectedService,
    LogCollectionManifest,
    LogCollectionParams,
    LogErrorEntry,
)
from app.log_collection.service import (
    ClusterUnreachableError,
    collect_container_logs_into,
)
from app.tshark.config import TSHARK_DURATION as TSHARK_DEFAULT_DURATION
from app.tshark.config import TSHARK_DIAGNOSTICS_NAMESPACE
from app.tshark.service import TSharkCaptureError, capture_network, cleanup_capture_job
from app.umf_rti.config import UmfRtiConfig, get_umf_rti_config
from app.umf_rti.schemas import UmfRtiParams
from app.umf_rti.service import (
    UmfRtiCaptureError,
    UmfRtiPrerequisiteError,
    capture_umf_rti,
    check_prerequisites,
    write_artifacts,
    write_failure_artifacts,
)

from kubernetes import client

SUPPORTED_SERVICES = (CONTAINER_LOGS_SERVICE_ID, UMF_RTI_SERVICE_ID, TSHARK_SERVICE_ID)


class CollectionInProgressError(Exception):
    """Another diagnostic collection already owns the tracker."""


def _cleanup_tshark_jobs(batch: client.BatchV1Api, pending: List[str]) -> Optional[str]:
    errors = []
    while pending:
        job_name = pending.pop()
        try:
            cleanup_capture_job(batch, job_name)
        except TSharkCaptureError as exc:
            errors.append(str(exc))
    return "; ".join(errors) or None


def _dedupe_services(services: List[str]) -> List[str]:
    selected: List[str] = []
    for service in services:
        if service not in SUPPORTED_SERVICES:
            raise ValueError(f"Unsupported diagnostic service: {service}")
        if service not in selected:
            selected.append(service)
    if not selected:
        raise ValueError("Select at least one diagnostic service.")
    return selected


def _begin_progress(selected: List[str]) -> bool:
    progress_services = []
    for service_id in selected:
        if service_id == CONTAINER_LOGS_SERVICE_ID:
            progress_services.append(
                ServiceProgress(
                    id=CONTAINER_LOGS_SERVICE_ID,
                    label=CONTAINER_LOGS_LABEL,
                    unit="containers",
                )
            )
        elif service_id == UMF_RTI_SERVICE_ID:
            progress_services.append(
                ServiceProgress(
                    id=UMF_RTI_SERVICE_ID,
                    label=UMF_RTI_LABEL,
                    unit="seconds",
                )
            )
        elif service_id == TSHARK_SERVICE_ID:
            progress_services.append(
                ServiceProgress(
                    id=TSHARK_SERVICE_ID,
                    label=TSHARK_LABEL,
                    unit="seconds",
                )
            )
    return tracker.try_begin(progress_services)


def _collect_tshark(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    pending_cleanup: List[str],
    duration: Optional[int] = None,
) -> None:
    import json
    # Duration is None if the user did not request TShark capture, in which case we use the default duration.
    capture_duration = TSHARK_DEFAULT_DURATION if duration is None else duration
    tracker.set_service_total(TSHARK_SERVICE_ID, capture_duration, unit="seconds")
    tracker.set_service_completed(
        TSHARK_SERVICE_ID, 0, current="Preparing TShark capture workload..."
    )
    state_messages = {
        "pending": "Waiting to create capture workload...",
        "deploying": "Creating TShark capture workload...",
        "capturing": "Capturing traffic on the workload interface...",
        "processing": "Analyzing packets and collecting PCAPNG...",
        "completed": "Capture and analysis completed.",
        "failed": "TShark capture failed.",
        "cancelled": "TShark capture cancelled.",
    }
    # Update the tracker with the current state and progress of the TShark capture.
    def update_capture_state(state: str) -> None:
        tracker.set_service_state(TSHARK_SERVICE_ID, state)
        tracker.set_service_current(
            TSHARK_SERVICE_ID, state_messages.get(state, state)
        )
    # Update the tracker with the progress of the TShark capture.
    def update_capture_progress(completed: int, total: int) -> None:
        tracker.set_service_total(
            TSHARK_SERVICE_ID, total, unit="seconds"
        )
        tracker.set_service_completed(
            TSHARK_SERVICE_ID,
            completed,
            current=(
                "Capturing traffic on the workload interface... "
                f"({completed}/{total} seconds)"
            ),
        )

    try:
        result = capture_network(
            core,
            batch,
            duration=capture_duration,
            include_pcap=True,
            defer_cleanup=True,
            on_state=update_capture_state,
            on_progress=update_capture_progress,
        )
        pending_cleanup.append(result.pop("cleanupJobName"))
        pcap_bytes = result.pop("pcapBytes")
        analysis_filename = "network/tshark-analysis.json"
        capture_filename = "network/tshark-capture.pcapng"
        zf.writestr(analysis_filename, json.dumps(result, indent=2))
        zf.writestr(capture_filename, pcap_bytes)
        manifest.collected_files.extend([analysis_filename, capture_filename])

        if result["captureState"] == "failed":
            message = result["error"]
            tracker.fail_service(TSHARK_SERVICE_ID, message)
            manifest.errors.append(
                LogErrorEntry(
                    namespace=TSHARK_DIAGNOSTICS_NAMESPACE,
                    pod=result["pod"],
                    container="tshark",
                    reason=message,
                    service=TSHARK_SERVICE_ID,
                )
            )
            manifest.services.append(
                CollectedService(
                    id=TSHARK_SERVICE_ID,
                    label=TSHARK_LABEL,
                    status="error",
                    files=[analysis_filename, capture_filename],
                    error=message,
                )
            )
            return

        tracker.set_service_completed(TSHARK_SERVICE_ID, capture_duration)
        manifest.services.append(
            CollectedService(
                id=TSHARK_SERVICE_ID,
                label=TSHARK_LABEL,
                status="done",
                files=[analysis_filename, capture_filename],
            )
        )
    except Exception as e:
        message = f"TShark capture failed: {e}"
        tracker.set_service_state(TSHARK_SERVICE_ID, "failed")
        tracker.fail_service(TSHARK_SERVICE_ID, message)
        manifest.errors.append(
            LogErrorEntry(
                namespace=TSHARK_DIAGNOSTICS_NAMESPACE,
                pod="tshark-capture",
                container="tshark",
                reason=message,
                service=TSHARK_SERVICE_ID,
            )
        )
        manifest.services.append(
            CollectedService(
                id=TSHARK_SERVICE_ID,
                label=TSHARK_LABEL,
                status="error",
                error=message,
            )
        )


def collect_diagnostics(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    services: List[str],
    log_params: LogCollectionParams,
    umf_params: UmfRtiParams,
    config: Optional[UmfRtiConfig] = None,
    tshark_duration: Optional[int] = None,
) -> tempfile.SpooledTemporaryFile:
    """Collect every selected service into one streaming zip.

    Per-service failures are recorded in ``manifest.json`` and do not discard
    the other service's artifacts.  A cluster that cannot even list pods is
    still a 503 at the HTTP layer (nothing useful can be collected).
    """
    selected = _dedupe_services(services)
    config = config or get_umf_rti_config()
    if not _begin_progress(selected):
        raise CollectionInProgressError(
            "A diagnostic collection is already in progress."
        )

    temp_zip = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024, mode="w+b")
    manifest = LogCollectionManifest(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        total_logs_collected=0,
    )
    pending_tshark_cleanup: List[str] = []

    try:
        with zipfile.ZipFile(
            temp_zip, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for service_id in selected:
                if service_id == CONTAINER_LOGS_SERVICE_ID:
                    _collect_container_logs(zf, manifest, core, log_params)
                elif service_id == UMF_RTI_SERVICE_ID:
                    _collect_umf_rti(
                        zf, manifest, core, batch, umf_params, config, selected
                    )
                elif service_id == TSHARK_SERVICE_ID:
                    _collect_tshark(
                        zf,
                        manifest,
                        core,
                        batch,
                        pending_tshark_cleanup,
                        duration=tshark_duration,
                    )

            tracker.set_status("packaging")
            manifest.total_logs_collected = len(manifest.collected_files)
            zf.writestr("manifest.json", manifest.model_dump_json(indent=2))

        cleanup_error = _cleanup_tshark_jobs(batch, pending_tshark_cleanup)
        if cleanup_error:
            raise TSharkCaptureError(cleanup_error)

        temp_zip.seek(0)
        tracker.finish()
        return temp_zip
    except ClusterUnreachableError as e:
        cleanup_error = _cleanup_tshark_jobs(batch, pending_tshark_cleanup)
        message = f"{e}; {cleanup_error}" if cleanup_error else str(e)
        tracker.fail(message)
        temp_zip.close()
        if cleanup_error:
            raise RuntimeError(message) from e
        raise
    except UmfRtiPrerequisiteError as e:
        cleanup_error = _cleanup_tshark_jobs(batch, pending_tshark_cleanup)
        message = f"{e}; {cleanup_error}" if cleanup_error else str(e)
        tracker.fail(message)
        temp_zip.close()
        if cleanup_error:
            raise RuntimeError(message) from e
        raise
    except Exception as e:
        cleanup_error = _cleanup_tshark_jobs(batch, pending_tshark_cleanup)
        message = f"{e}; {cleanup_error}" if cleanup_error else str(e)
        tracker.fail(message)
        temp_zip.close()
        if cleanup_error:
            raise RuntimeError(message) from e
        raise


def _collect_container_logs(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    core: client.CoreV1Api,
    params: LogCollectionParams,
) -> None:
    try:
        files = collect_container_logs_into(zf, manifest, core, params)
    except ClusterUnreachableError:
        # Let the endpoint return 503: if we cannot list pods, the cluster
        # connection itself is broken and a partial package is misleading.
        raise
    except Exception as e:
        message = f"Container log collection failed: {e}"
        tracker.fail_service(CONTAINER_LOGS_SERVICE_ID, message)
        manifest.errors.append(
            LogErrorEntry(
                namespace="(cluster)",
                pod="(all)",
                container="(all)",
                reason=message,
                service=CONTAINER_LOGS_SERVICE_ID,
            )
        )
        manifest.services.append(
            CollectedService(
                id=CONTAINER_LOGS_SERVICE_ID,
                label=CONTAINER_LOGS_LABEL,
                status="error",
                error=message,
            )
        )
        return

    manifest.services.append(
        CollectedService(
            id=CONTAINER_LOGS_SERVICE_ID,
            label=CONTAINER_LOGS_LABEL,
            status="done",
            files=files,
        )
    )


def _collect_umf_rti(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    params: UmfRtiParams,
    config: UmfRtiConfig,
    selected: List[str],
) -> None:
    result = None
    try:
        check_prerequisites(core, config)
        result = capture_umf_rti(core, batch, params, config)
        write_artifacts(zf, manifest, result)
    except UmfRtiPrerequisiteError as e:
        message = str(e)
        tracker.fail_service(UMF_RTI_SERVICE_ID, message)
        if selected == [UMF_RTI_SERVICE_ID]:
            # Nothing else was requested, so surface the actionable 503.
            raise
        write_failure_artifacts(zf, manifest, message, params, config)
    except UmfRtiCaptureError as e:
        message = str(e)
        tracker.fail_service(UMF_RTI_SERVICE_ID, message)
        write_failure_artifacts(zf, manifest, message, params, config)
    except Exception as e:
        message = f"UMF RTI collection failed: {e}"
        tracker.fail_service(UMF_RTI_SERVICE_ID, message)
        write_failure_artifacts(zf, manifest, message, params, config)
    finally:
        # The recording was pulled to a local temp dir; drop it now it's zipped.
        if result is not None and result.recording_dir:
            shutil.rmtree(result.recording_dir, ignore_errors=True)
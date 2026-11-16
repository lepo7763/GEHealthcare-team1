"""Orchestrates the selected diagnostic services into one zip package."""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import List, Optional

from app.log_collection.progress import (
    CONTAINER_LOGS_LABEL,
    CONTAINER_LOGS_SERVICE_ID,
    UMF_RTI_LABEL,
    UMF_RTI_SERVICE_ID,
    ServiceProgress,
    tracker,
    NETSHOOT_LABEL,
    NETSHOOT_SERVICE_ID,
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

from app.network_diagnostics.capture_service import (
    NetshootCaptureError,
    collect_netshoot_captures
)
from app.network_diagnostics.schemas import (
    NetshootCollectionParams
)

from kubernetes import client

SUPPORTED_SERVICES = (CONTAINER_LOGS_SERVICE_ID, UMF_RTI_SERVICE_ID, NETSHOOT_SERVICE_ID)


class CollectionInProgressError(Exception):
    """Another diagnostic collection already owns the tracker."""


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
        else:
            progress_services.append(
                ServiceProgress(
                    id = NETSHOOT_SERVICE_ID,
                    label = NETSHOOT_LABEL,
                    unit = "sessions"
                )
            )
    return tracker.try_begin(progress_services)


def collect_diagnostics(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    services: List[str],
    log_params: LogCollectionParams,
    umf_params: UmfRtiParams,
    config: Optional[UmfRtiConfig] = None,
    netshoot_params: Optional[NetshootCollectionParams] = None,
) -> tempfile.SpooledTemporaryFile:
    """Collect every selected service into one streaming zip.

    Per-service failures are recorded in ``manifest.json`` and do not discard
    the other service's artifacts.  A cluster that cannot even list pods is
    still a 503 at the HTTP layer (nothing useful can be collected).
    """
    selected = _dedupe_services(services)
    config = config or get_umf_rti_config()

    netshoot_params = netshoot_params or NetshootCollectionParams()

    if not _begin_progress(selected):
        raise CollectionInProgressError(
            "A diagnostic collection is already in progress."
        )

    temp_zip = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024, mode="w+b")
    manifest = LogCollectionManifest(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        total_logs_collected=0,
    )

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
                elif service_id == NETSHOOT_SERVICE_ID:
                    _collect_netshoot(
                        zf, manifest, core, batch, netshoot_params
                    )

            tracker.set_status("packaging")
            manifest.total_logs_collected = len(manifest.collected_files)
            zf.writestr("manifest.json", manifest.model_dump_json(indent=2))

        temp_zip.seek(0)
        tracker.finish()
        return temp_zip
    except ClusterUnreachableError as e:
        tracker.fail(str(e))
        temp_zip.close()
        raise
    except UmfRtiPrerequisiteError as e:
        tracker.fail(str(e))
        temp_zip.close()
        raise
    except Exception as e:
        tracker.fail(str(e))
        temp_zip.close()
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

def _collect_netshoot(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    params: NetshootCollectionParams,
) -> None:

    files = []
    failures = []

    tracker.set_service_total(
        NETSHOOT_SERVICE_ID, 1, unit="sessions"
    )

    tracker.set_service_current(
        NETSHOOT_SERVICE_ID,
        "Collecting network traffic",
    )

    try:

        with tempfile.TemporaryDirectory(
            prefix="netshoot-"
        ) as directory:

            archives, errors, cleanup_errors = (
                collect_netshoot_captures(
                    core_api=core,
                    batch_api=batch,
                    namespaces=None,
                    destination_dir=directory,
                    duration_seconds=(
                        params.netshoot_duration_seconds
                    ),
                )
            )

            for node, archive in archives.items():
                archive_name = (
                    f"netshoot/{node}/{archive.name}"
                )

                zf.write(
                    archive,
                    arcname=archive_name,
                    compress_type=zipfile.ZIP_STORED,
                )

                files.append(archive_name)
                manifest.collected_files.append(
                    archive_name
                )

            for node, error in errors.items():
                failures.append(
                    f"Node {node}: {error}"
                )

            for job, error in cleanup_errors.items():
                failures.append(
                    f"Cleanup failed for Job {job}: {error}"
                )

    except Exception as exc:
        failures.append(
            f"Netshoot collection failed: {exc}"
        )

    for failure in failures:
        manifest.errors.append(
            LogErrorEntry(
                namespace="(cluster)",
                pod="(multiple)",
                container="netshoot",
                reason=failure,
                service=NETSHOOT_SERVICE_ID,
            )
        )

    message = "; ".join(failures) if failures else None

    if failures:
        tracker.fail_service(
            NETSHOOT_SERVICE_ID, message
        )
    else:
        tracker.set_service_completed(
            NETSHOOT_SERVICE_ID, 1
        )

    manifest.services.append(
        CollectedService(
            id=NETSHOOT_SERVICE_ID,
            label=NETSHOOT_LABEL,
            status="error" if failures else "done",
            files=files,
            error=message,
        )
    )
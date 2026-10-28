"""Orchestrates the selected diagnostic services into one zip package."""

from __future__ import annotations

import tempfile
import zipfile
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes import client

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
from app.tshark.service import capture_network
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

SUPPORTED_SERVICES = (CONTAINER_LOGS_SERVICE_ID, UMF_RTI_SERVICE_ID, TSHARK_SERVICE_ID)


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
) -> None:
    import json
    tracker.set_service_total(TSHARK_SERVICE_ID, TSHARK_DEFAULT_DURATION, unit="seconds")
    tracker.set_service_completed(TSHARK_SERVICE_ID, 0, current="Running Wireshark / tshark capture...")
    try:
        result = capture_network(core)
        filename = "network/wireshark-tshark-analysis.json"
        zf.writestr(filename, json.dumps(result, indent=2))
        manifest.collected_files.append(filename)
        tracker.set_service_completed(TSHARK_SERVICE_ID, TSHARK_DEFAULT_DURATION)
        manifest.services.append(
            CollectedService(
                id=TSHARK_SERVICE_ID,
                label=TSHARK_LABEL,
                status="done",
                files=[filename],
            )
        )
    except Exception as e:
        message = f"Wireshark / tshark capture failed: {e}"
        tracker.fail_service(TSHARK_SERVICE_ID, message)
        manifest.errors.append(
            LogErrorEntry(
                namespace="iomt-dev-2",
                pod="tshark-test",
                container="tshark-test",
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
) -> tempfile.SpooledTemporaryFile:
    """Collect every selected service into one streaming zip.

    Per-service failures are recorded in ``manifest.json`` and do not discard
    the other service's artifacts.  A cluster that cannot even list pods is
    still a 503 at the HTTP layer (nothing useful can be collected).
    """
    selected = _dedupe_services(services)
    config = config or get_umf_rti_config()
    if not _begin_progress(selected):
        raise CollectionInProgressError("A diagnostic collection is already in progress.")

    temp_zip = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024, mode="w+b")
    manifest = LogCollectionManifest(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        total_logs_collected=0,
    )

    try:
        with zipfile.ZipFile(temp_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for service_id in selected:
                if service_id == CONTAINER_LOGS_SERVICE_ID:
                    _collect_container_logs(zf, manifest, core, log_params)
                elif service_id == UMF_RTI_SERVICE_ID:
                    _collect_umf_rti(
                        zf, manifest, core, batch, umf_params, config, selected
                    )
                elif service_id == TSHARK_SERVICE_ID:
                    _collect_tshark(zf, manifest, core)

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
    try:
        check_prerequisites(core, config)
        result = capture_umf_rti(core, batch, params, config)
        write_artifacts(zf, manifest, result, params, config)
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

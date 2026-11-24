"""Orchestrates the selected diagnostic services into one zip package."""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import BinaryIO, List, Optional

from app.core.workdir import work_dir

from app.cms.collector import collect_cms_into
from app.core_dumps.config import CoreDumpConfig
from app.core_dumps.schemas import CoreDumpParams
from app.core_dumps.service import collect_core_dumps_into
from app.firewall.config import FirewallConfig
from app.firewall.service import collect_firewall_into
from app.prometheus.config import PrometheusConfig
from app.prometheus.schemas import PrometheusParams
from app.prometheus.service import collect_prometheus_into
from app.log_collection.progress import (
    AXONE_LOGS_LABEL,
    AXONE_LOGS_SERVICE_ID,
    CONTAINER_LOGS_LABEL,
    CONTAINER_LOGS_SERVICE_ID,
    CORE_DUMPS_LABEL,
    CORE_DUMPS_SERVICE_ID,
    CollectionCancelled,
    FIREWALL_LABEL,
    FIREWALL_SERVICE_ID,
    PROMETHEUS_LABEL,
    PROMETHEUS_SERVICE_ID,
    UMF_RTI_LABEL,
    UMF_RTI_SERVICE_ID,
    ServiceProgress,
    tracker,
    NETSHOOT_LABEL,
    NETSHOOT_SERVICE_ID,
    CMS_LABEL,
    CMS_SERVICE_ID,
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
from app.log_export.schemas import AxoneLogParams
from app.log_export.service import ExportError, fetch_axone_csv
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

SUPPORTED_SERVICES = (
    CONTAINER_LOGS_SERVICE_ID,
    UMF_RTI_SERVICE_ID,
    AXONE_LOGS_SERVICE_ID,
    CORE_DUMPS_SERVICE_ID,
    FIREWALL_SERVICE_ID,
    NETSHOOT_SERVICE_ID,
    CMS_SERVICE_ID,
    PROMETHEUS_SERVICE_ID,
)


class CollectionCancelledError(Exception):
    """The user cancelled the collection (the Back button on the collect step)."""


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
        elif service_id == AXONE_LOGS_SERVICE_ID:
            progress_services.append(
                ServiceProgress(
                    id=AXONE_LOGS_SERVICE_ID,
                    label=AXONE_LOGS_LABEL,
                    unit="files",
                )
            )
        elif service_id == FIREWALL_SERVICE_ID:
            progress_services.append(
                ServiceProgress(
                    id=FIREWALL_SERVICE_ID,
                    label=FIREWALL_LABEL,
                    unit="steps",
                )
            )
        elif service_id == CORE_DUMPS_SERVICE_ID:
            progress_services.append(
                ServiceProgress(
                    id=CORE_DUMPS_SERVICE_ID,
                    label=CORE_DUMPS_LABEL,
                    unit="MB",
                )
            )
        elif service_id == PROMETHEUS_SERVICE_ID:
            progress_services.append(
                ServiceProgress(
                    id=PROMETHEUS_SERVICE_ID,
                    label=PROMETHEUS_LABEL,
                    unit="MB",
                )
            )
        elif service_id == NETSHOOT_SERVICE_ID:
            progress_services.append(
                ServiceProgress(
                    id = NETSHOOT_SERVICE_ID,
                    label = NETSHOOT_LABEL,
                    unit = "sessions"
                )
            )
        elif service_id == CMS_SERVICE_ID:
            progress_services.append(
                ServiceProgress(
                    id = CMS_SERVICE_ID,
                    label = CMS_LABEL,
                    unit = "snapshots",
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
    axone_params: Optional[AxoneLogParams] = None,
    core_dump_params: Optional[CoreDumpParams] = None,
    core_dump_config: Optional[CoreDumpConfig] = None,
    firewall_config: Optional[FirewallConfig] = None,
    prometheus_params: Optional[PrometheusParams] = None,
    prometheus_config: Optional[PrometheusConfig] = None,
    cms_start_datetime: Optional[str] = None,
    cms_end_datetime: Optional[str] = None,
    out: Optional[BinaryIO] = None,
) -> BinaryIO:
    """Collect every selected service into one streaming zip.

    Written to `out` if given, else to an anonymous file on disk (see
    app.core.workdir); returned rewound. On failure the file is closed.

    Per-service failures are recorded in ``manifest.json`` and do not discard
    the other service's artifacts.  A cluster that cannot even list pods is
    still a 503 at the HTTP layer (nothing useful can be collected).
    """
    selected = _dedupe_services(services)
    if CMS_SERVICE_ID in selected:
        if not cms_start_datetime or not cms_end_datetime:
            raise ValueError(
                "CMS collection require start and end timestamps"
            )
    config = config or get_umf_rti_config()

    netshoot_params = netshoot_params or NetshootCollectionParams()

    axone_params = axone_params or AxoneLogParams()
    if not _begin_progress(selected):
        raise CollectionInProgressError(
            "A diagnostic collection is already in progress."
        )

    temp_zip = out if out is not None else tempfile.TemporaryFile(dir=work_dir())
    manifest = LogCollectionManifest(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        total_logs_collected=0,
    )

    try:
        with zipfile.ZipFile(
            temp_zip, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for service_id in selected:
                tracker.check_cancelled()
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
                elif service_id == AXONE_LOGS_SERVICE_ID:
                    _collect_axone_logs(zf, manifest, axone_params, selected)
                elif service_id == CORE_DUMPS_SERVICE_ID:
                    collect_core_dumps_into(
                        zf,
                        manifest,
                        core,
                        batch,
                        core_dump_params or CoreDumpParams(),
                        core_dump_config,
                    )
                elif service_id == FIREWALL_SERVICE_ID:
                    collect_firewall_into(zf, manifest, core, batch, firewall_config)
                
                elif service_id == CMS_SERVICE_ID:
                    collect_cms_into(
                        zf,
                        manifest,
                        cms_start_datetime,
                        cms_end_datetime,
                    )
                elif service_id == PROMETHEUS_SERVICE_ID:
                    collect_prometheus_into(
                        zf,
                        manifest,
                        core,
                        batch,
                        prometheus_params or PrometheusParams(),
                        prometheus_config,
                    )

            tracker.set_status("packaging")
            manifest.total_logs_collected = len(manifest.collected_files)
            zf.writestr("manifest.json", manifest.model_dump_json(indent=2))

        temp_zip.seek(0)
        tracker.finish()
        return temp_zip
    except CollectionCancelled:
        # The collectors' finally blocks have already deleted their Jobs.
        tracker.mark_cancelled()
        temp_zip.close()
        raise CollectionCancelledError("Collection cancelled.") from None
    except ClusterUnreachableError as e:
        tracker.fail(str(e))
        temp_zip.close()
        raise
    except UmfRtiPrerequisiteError as e:
        tracker.fail(str(e))
        temp_zip.close()
        raise
    except ExportError as e:
        tracker.fail(e.detail)
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

    test_namespace = os.getenv("IOMT_NETSHOOT_TEST_NAMESPACE")
    namespaces = [test_namespace] if test_namespace else None

    try:

        if test_namespace and params.netshoot_scope != "pod":
            raise NetshootCaptureError(
                "Host-network capture is unavailable in namespace-restricted "
                "test mode. Select Pod traffic only."
        )

        with tempfile.TemporaryDirectory(
            prefix="netshoot-"
        ) as directory:

            archives, errors, cleanup_errors = (
                collect_netshoot_captures(
                    core_api=core,
                    batch_api=batch,
                    namespaces=namespaces,
                    destination_dir=directory,
                    duration_seconds=(
                        params.netshoot_duration_seconds
                    ),
                    scope = params.netshoot_scope,
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


def _collect_axone_logs(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    params: AxoneLogParams,
    selected: List[str],
) -> None:
    tracker.set_service_total(AXONE_LOGS_SERVICE_ID, 1, unit="files")
    tracker.set_service_current(AXONE_LOGS_SERVICE_ID, "Requesting CSV export")
    try:
        content = fetch_axone_csv(params)
    except ExportError as e:
        message = f"Axone log export failed: {e.detail}"
        tracker.fail_service(AXONE_LOGS_SERVICE_ID, message)
        if selected == [AXONE_LOGS_SERVICE_ID]:
            # Nothing else was requested, so surface the actionable error.
            raise
        _record_axone_failure(manifest, message)
        return
    except Exception as e:
        message = f"Axone log export failed: {e}"
        tracker.fail_service(AXONE_LOGS_SERVICE_ID, message)
        _record_axone_failure(manifest, message)
        return

    path = f"axone/axone_{params.axone_scope}_logs.csv"
    zf.writestr(path, content)
    manifest.collected_files.append(path)
    tracker.increment_service(AXONE_LOGS_SERVICE_ID, current=path)
    manifest.services.append(
        CollectedService(
            id=AXONE_LOGS_SERVICE_ID,
            label=AXONE_LOGS_LABEL,
            status="done",
            files=[path],
        )
    )


def _record_axone_failure(manifest: LogCollectionManifest, message: str) -> None:
    manifest.errors.append(
        LogErrorEntry(
            namespace="(axone)",
            pod="(log-export)",
            container="(all)",
            reason=message,
            service=AXONE_LOGS_SERVICE_ID,
        )
    )
    manifest.services.append(
        CollectedService(
            id=AXONE_LOGS_SERVICE_ID,
            label=AXONE_LOGS_LABEL,
            status="error",
            error=message,
        )
    )

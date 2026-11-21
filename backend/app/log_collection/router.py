import io
import time
import zipfile
from datetime import datetime, timezone
from typing import List, Literal, Optional

from app.core.k8s_client import get_batch_v1_api, get_core_v1_api
from app.core_dumps.schemas import CoreDumpParams
from app.diagnostics import packages
from app.diagnostics.service import (
    CollectionCancelledError,
    CollectionInProgressError,
    collect_diagnostics,
)
from app.prometheus.schemas import PrometheusParams
from app.log_collection.progress import tracker
from app.log_collection.schemas import (
    CollectionProgressResponse,
    LogCollectionParams,
    PackageResponse,
)
from app.log_collection.service import ClusterUnreachableError
from app.log_export.schemas import AxoneLogParams
from app.log_export.service import ExportError, validate_axone_params
from app.umf_rti.schemas import UmfRtiParams
from app.umf_rti.service import UmfRtiPrerequisiteError
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse

from kubernetes import client

router = APIRouter(prefix="/api/logs", tags=["Diagnostics"])


def _stream_and_close(temp_file, chunk_size: int = 64 * 1024):
    try:
        while chunk := temp_file.read(chunk_size):
            yield chunk
    finally:
        temp_file.close()


@router.get("/progress", response_model=CollectionProgressResponse)
def get_collection_progress() -> dict:
    """Snapshot of the current/last collection, polled by the UI."""
    return tracker.snapshot()


@router.post("/cancel")
def cancel_collection() -> dict:
    """Stop the running collection and wait until its collector Jobs are cleaned up.

    Returns once nothing is running, so the caller can start a new collection
    straight away. ``cancelled`` is False when nothing was running.
    """
    cancelled = tracker.request_cancel()
    if cancelled:
        deadline = time.monotonic() + 30
        while tracker.running and time.monotonic() < deadline:
            time.sleep(0.1)
    return {"cancelled": cancelled, "running": tracker.running}


def collection_request(
    services: List[
        Literal[
            "container-logs", "umf-rti", "axone-logs", "core-dumps", "firewall", "prometheus"
        ]
    ] = Query(
        default=["container-logs"],
        description=(
            "Repeat for each service: services=container-logs&services=umf-rti"
            "&services=axone-logs&services=core-dumps&services=firewall"
            "&services=prometheus."
            " At least one service is required."
        ),
    ),
    log_params: LogCollectionParams = Depends(),
    umf_params: UmfRtiParams = Depends(),
    axone_params: AxoneLogParams = Depends(),
    core_since: Optional[datetime] = Query(
        default=None, description="Core dumps: only cores dumped at/after this time."
    ),
    core_until: Optional[datetime] = Query(
        default=None, description="Core dumps: only cores dumped at/before this time."
    ),
    core_process: List[str] = Query(
        default=[], description="Core dumps: process name(s) to include (repeatable)."
    ),
    prom_since: Optional[datetime] = Query(
        default=None, description="Prometheus: only TSDB blocks with data at/after this time."
    ),
    prom_until: Optional[datetime] = Query(
        default=None, description="Prometheus: only TSDB blocks with data at/before this time."
    ),
) -> dict:
    """The query parameters shared by /zip and /packages, as collect_diagnostics kwargs."""
    return dict(
        services=list(services),
        log_params=log_params,
        umf_params=umf_params,
        axone_params=axone_params,
        core_dump_params=CoreDumpParams(
            since=core_since, until=core_until, processes=core_process
        ),
        prometheus_params=PrometheusParams(since=prom_since, until=prom_until),
    )


def _collect(request: dict, core, batch, out=None):
    """Run collect_diagnostics, mapping its errors to HTTP status codes."""
    if tracker.running:
        raise HTTPException(
            status_code=409,
            detail="A diagnostic collection is already in progress.",
        )
    if not request["services"]:
        raise HTTPException(
            status_code=422,
            detail="Select at least one diagnostic service.",
        )
    if "axone-logs" in request["services"]:
        # Fail fast on bad Axone filters, before any other service runs.
        try:
            validate_axone_params(request["axone_params"])
        except ExportError as e:
            raise HTTPException(status_code=422, detail=e.detail)
    try:
        return collect_diagnostics(core=core, batch=batch, out=out, **request)
    except CollectionCancelledError as e:
        raise HTTPException(status_code=499, detail=str(e))
    except CollectionInProgressError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ClusterUnreachableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except UmfRtiPrerequisiteError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ExportError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _package_filename() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"iomt_diagnostics_{ts}.zip"


@router.get("/zip")
def download_diagnostics(
    request: dict = Depends(collection_request),
    core: client.CoreV1Api = Depends(get_core_v1_api),
    batch: client.BatchV1Api = Depends(get_batch_v1_api),
):
    """Collect container logs, a UMF RTI capture, an Axone log CSV export, node
    core dumps, firewall settings
    and/or a time slice of the Prometheus database into one zip, returned in the
    response. The UI uses POST /packages instead, so large packages go straight
    to disk on the browser side too."""
    temp_zip = _collect(request, core, batch)
    filename = _package_filename()

    # The zip is built in full first (on disk), then streamed to the client.
    return StreamingResponse(
        _stream_and_close(temp_zip),
        media_type="application/zip",
        # 'attachment' so don't try open in browser
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/packages", response_model=PackageResponse)
def create_package(
    request: dict = Depends(collection_request),
    core: client.CoreV1Api = Depends(get_core_v1_api),
    batch: client.BatchV1Api = Depends(get_batch_v1_api),
) -> PackageResponse:
    """Same collection as GET /zip, but the package stays on the backend's disk
    and is downloaded from ``url`` (a plain file download the browser saves to
    disk, so package size doesn't matter)."""
    out = packages.new_package_file()
    try:
        _collect(request, core, batch, out=out)
    except BaseException:
        out.close()
        packages.discard(out.name)
        raise
    out.close()
    package = packages.register(out.name, _package_filename())
    return PackageResponse(
        id=package.id,
        filename=package.filename,
        size_bytes=package.size_bytes,
        url=f"{router.prefix}/packages/{package.id}",
    )


@router.get("/packages/{package_id}")
def download_package(package_id: str):
    """The package file itself (supports resumable Range requests)."""
    package = packages.get(package_id)
    if package is None:
        raise HTTPException(
            status_code=404,
            detail="That package is no longer available. Run the collection again.",
        )
    return FileResponse(
        package.path, media_type="application/zip", filename=package.filename
    )


@router.get("/demo.zip")
def download_demo_logs():
    collected_at = datetime.now(timezone.utc).isoformat()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"demo_diagnostic_logs_{timestamp}.zip"
    files = {
        "session-summary.txt": (
            "SIMULATED DIAGNOSTIC SESSION\n"
            "This archive contains demonstration data only, not results from a live system.\n"
            f"Collection time (UTC): {collected_at}\n"
        ),
        "logs/system.log": (
            f"{collected_at} INFO [DEMO] System services initialized.\n"
            f"{collected_at} INFO [DEMO] Resource checks completed successfully.\n"
        ),
        "logs/application.log": (
            f"{collected_at} INFO [DEMO] Application service is responding.\n"
            f"{collected_at} WARN [DEMO] Example warning for interface demonstration.\n"
        ),
        "network-diagnostics.txt": (
            "SIMULATED DATA: No live network checks or packet captures are included.\n"
        ),
        "configuration-snapshot.txt": (
            "SIMULATED DATA: No live environment configuration is included.\n"
        ),
        "health-metrics.txt": (
            "SIMULATED DATA: No live health metrics are included.\n"
        ),
    }

    archive = io.BytesIO()
    with zipfile.ZipFile(
        archive, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as zip_file:
        for path, content in files.items():
            zip_file.writestr(path, content)

    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

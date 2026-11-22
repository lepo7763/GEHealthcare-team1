import re
import io
import zipfile
from datetime import datetime, timezone
from typing import List, Literal, Optional

from app.core.k8s_client import get_batch_v1_api, get_core_v1_api
from app.core_dumps.schemas import DEFAULT_MAX_MB, MAX_MAX_MB, CoreDumpParams
from app.diagnostics.service import CollectionInProgressError, collect_diagnostics
from app.log_collection.progress import tracker
from app.log_collection.schemas import CollectionProgressResponse, LogCollectionParams
from app.network_diagnostics.schemas import NetshootCollectionParams
from app.log_collection.service import ClusterUnreachableError
from app.umf_rti.schemas import UmfRtiParams
from app.umf_rti.service import UmfRtiPrerequisiteError
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

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


@router.get("/zip")
def download_diagnostics(
    services: List[Literal["container-logs", "umf-rti", "core-dumps", "firewall", "netshoot", "cms"]] = Query(
        default=["container-logs"],
        description=(
            "Repeat for each service: services=container-logs&services=umf-rti"
            "&services=core-dumps&services=firewall. At least one service is required."
        ),
    ),
    log_params: LogCollectionParams = Depends(),
    umf_params: UmfRtiParams = Depends(),
    netshoot_params: NetshootCollectionParams = Depends(),
    cms_start_datetime: Optional[str] = Query(
        default=None,
        description="CMS start time in UTC (YYYY-MM-DDTHH:MM:SS.mmm)",
    ),
    cms_end_datetime: Optional[str] = Query(
        default=None,
        description="CMS end time in UTC (YYYY-MM-DDTHH:MM:SS.mmm)",
    ),
    core_since: Optional[datetime] = Query(
        default=None, description="Core dumps: only cores dumped at/after this time."
    ),
    core_process: List[str] = Query(
        default=[], description="Core dumps: process name(s) to include (repeatable)."
    ),
    core_max_mb: int = Query(
        default=DEFAULT_MAX_MB,
        ge=1,
        le=MAX_MAX_MB,
        description="Core dumps: total size cap in MB (newest kept first).",
    ),
    core: client.CoreV1Api = Depends(get_core_v1_api),
    batch: client.BatchV1Api = Depends(get_batch_v1_api),
):
    """Collect container logs, a UMF RTI capture, node core dumps and/or firewall settings into one zip."""
    if tracker.running:
        raise HTTPException(
            status_code=409,
            detail="A diagnostic collection is already in progress.",
        )
    if not services:
        if "cms" in services:
            pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}"

            if not cms_start_datetime or not cms_end_datetime:
                raise HTTPException(
                    status_code=422,
                    detail="CMS requires start and end timestamps.",
                )

            if not (
                re.fullmatch(pattern, cms_start_datetime)
                and re.fullmatch(pattern, cms_end_datetime)
            ):
                raise HTTPException(
                    status_code=422,
                    detail="CMS timestamps must use YYYY-MM-DDTHH:MM:SS.mmm.",
                )

            try:
                start = datetime.strptime(
                    cms_start_datetime, "%Y-%m-%dT%H:%M:%S.%f"
                )
                end = datetime.strptime(
                    cms_end_datetime, "%Y-%m-%dT%H:%M:%S.%f"
                )
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid CMS date or time.",
                )

            if start >= end:
                raise HTTPException(
                    status_code=422,
                    detail="CMS end time must be after start time.",
                )
        raise HTTPException(
                    status_code=422,
                    detail="Select at least one diagnostic service.",
                )
    try:
        temp_zip = collect_diagnostics(
            core=core,
            batch=batch,
            services=list(services),
            log_params=log_params,
            umf_params=umf_params,
            netshoot_params = netshoot_params,
            core_dump_params=CoreDumpParams(
                since=core_since, processes=core_process, max_mb=core_max_mb
            ),
            cms_start_datetime = cms_start_datetime,
            cms_end_datetime = cms_end_datetime,     
        )
    except CollectionInProgressError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ClusterUnreachableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except UmfRtiPrerequisiteError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"iomt_diagnostics_{ts}.zip"

    # Can't use FileResponse cuz needs disk file path and SpooledTemporaryZip lives in memory/unlinked temp space
    # Also, this is streaming the zip's delivery to user. The zip creation itself is not streamed.
    return StreamingResponse(
        _stream_and_close(temp_zip),
        media_type="application/zip",
        # 'attachment' so don't try open in browser
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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

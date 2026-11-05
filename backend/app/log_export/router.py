from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .service import ExportError, fetch_export


router = APIRouter(prefix="/api/logs", tags=["Axone Log Export"])


@router.get("/export", response_class=Response)
def download_axone_logs(
    startTimestamp: str = Query(..., description="Local timestamp without a time zone"),
    endTimestamp: str = Query(..., description="Local timestamp without a time zone"),
    scope: Literal["device", "all"] = "device",
    format: Literal["csv", "json"] = "csv",
    deviceuuid: str | None = None,
    eventCategory: int | None = None,
):
    """Download Axone system logs using the guide's eight query combinations."""
    try:
        content = fetch_export(
            scope=scope,
            format=format,
            start_timestamp=startTimestamp,
            end_timestamp=endTimestamp,
            device_uuid=deviceuuid,
            event_category=eventCategory,
        )
    except ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"axone_{scope}_logs_{timestamp}.{format}"
    return Response(
        content=content,
        media_type="text/csv" if format == "csv" else "application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )

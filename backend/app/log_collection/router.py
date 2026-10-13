from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from kubernetes import client

from app.core.k8s_client import get_core_v1_api
from .schemas import LogCollectionParams
from .service import collect_all_cluster_logs, ClusterUnreachableError

router = APIRouter(prefix="/api/logs", tags=["Log Collection"])


def _stream_and_close(temp_file, chunk_size: int = 64 * 1024):
    try:
        while chunk := temp_file.read(chunk_size):
            yield chunk
    finally:
        temp_file.close()


@router.get("/zip")
def download_all_k8s_logs(
    params: LogCollectionParams = Depends(),
    v1: client.CoreV1Api = Depends(get_core_v1_api),
):
    try:
        temp_zip = collect_all_cluster_logs(v1=v1, params=params)
    except ClusterUnreachableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"k8s_cluster_logs_{ts}.zip"

    # Can't use FileResponse cuz needs disk file path and SpooledTemporaryZip lives in memory/unlinked temp space
    # Also, this is streaming the zip's delivery to user. The zip creation itself is not streamed.
    return StreamingResponse(
        _stream_and_close(temp_zip),
        media_type="application/zip",
        # 'attachment' so don't try open in browser
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

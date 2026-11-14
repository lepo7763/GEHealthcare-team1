from fastapi import APIRouter, Depends, HTTPException
from kubernetes import client

from app.core.k8s_client import get_batch_v1_api, get_core_v1_api

from .collector import CoreDumpCollectionError
from .schemas import CoreDumpListResponse
from .service import list_core_dumps

router = APIRouter(prefix="/api/core-dumps", tags=["Core Dumps"])


@router.get("", response_model=CoreDumpListResponse)
def get_core_dumps(
    core: client.CoreV1Api = Depends(get_core_v1_api),
    batch: client.BatchV1Api = Depends(get_batch_v1_api),
) -> CoreDumpListResponse:
    """List core files on the node (newest first) without downloading them.

    Runs a short-lived collector Job, so expect a few seconds of latency.
    """
    try:
        return list_core_dumps(core, batch)
    except CoreDumpCollectionError as e:
        raise HTTPException(status_code=503, detail=str(e))

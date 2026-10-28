# expose the service through API endpoints
from fastapi import APIRouter, Depends, HTTPException
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.core.k8s_client import get_core_v1_api
from app.tshark.service import capture_network

router = APIRouter(
    prefix="/api/network",
    tags=["Network Diagnostics"],
)


@router.post("/diagnostics")
def run_network_diagnostics(
    core: client.CoreV1Api = Depends(get_core_v1_api),
):
    try:
        return capture_network(core)
    except ApiException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Kubernetes API error: {exc.reason}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Network capture failed.",
        ) from exc

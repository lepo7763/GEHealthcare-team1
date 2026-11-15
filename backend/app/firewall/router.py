from fastapi import APIRouter, Depends, HTTPException
from kubernetes import client

from app.core.k8s_client import get_batch_v1_api, get_core_v1_api

from .collector import FirewallCollectionError
from .schemas import FirewallResponse
from .service import get_firewall

router = APIRouter(prefix="/api/firewall", tags=["Firewall"])


@router.get("", response_model=FirewallResponse)
def get_firewall_settings(
    core: client.CoreV1Api = Depends(get_core_v1_api),
    batch: client.BatchV1Api = Depends(get_batch_v1_api),
) -> FirewallResponse:
    """Current node firewall: parsed snapshot, printable report and raw outputs.

    Runs a short-lived privileged collector Job (read-only commands), so expect
    several seconds of latency.
    """
    try:
        return get_firewall(core, batch)
    except FirewallCollectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
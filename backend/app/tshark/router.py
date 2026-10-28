
"""TShark network diagnostics API."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.core.k8s_client import get_core_v1_api
from app.tshark.config import TSHARK_MAX_DURATION
from app.tshark.service import capture_network
from app.tshark.discovery import discover_pm_pods

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/network",
    tags=["Network Diagnostics"],
)


@router.post("/diagnostics")
def run_network_diagnostics(
    duration: int | None = Query(
        default=None,
        ge=1,
        le=TSHARK_MAX_DURATION,
        description="Capture duration in seconds",
    ),
    core: client.CoreV1Api = Depends(get_core_v1_api),
):
    try:
        return capture_network(core, duration=duration)

    except ApiException as exc:
        logger.exception("Kubernetes API error during capture")
        raise HTTPException(
            status_code=502,
            detail="Kubernetes could not execute the network capture.",
        ) from exc

    except Exception as exc:
        logger.exception("TShark capture failed")
        raise HTTPException(
            status_code=500,
            detail="Network capture failed. Check backend logs.",
        ) from exc

@router.get("/pm/pods")
def get_pm_pods(
    core: client.CoreV1Api = Depends(get_core_v1_api),
):
    try:
        return {
            "namespace": "pm",
            "pods": discover_pm_pods(core),
        }
    except ApiException as exc:
        logger.exception("PM pod discovery failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to discover Portrait Mobile pods.",
        ) from exc

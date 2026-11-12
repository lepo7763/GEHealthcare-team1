import os

from fastapi import APIRouter, Depends, HTTPException
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.core.k8s_client import get_core_v1_api, get_batch_v1_api
from .service import list_pods, validate_capture_target
from .schemas import (PodListResponse, PodInfo, CaptureRequest, CaptureTargetsResponse, NetshootCaptureStartRequest, NetshootCaptureStartResponse)
from fastapi.responses import Response
from .demo_capture import capture_demo_zip
from .job_service import discover_capture_targets, schedule_capture_jobs, CaptureSchedulingCleanupError




router = APIRouter(
    prefix="/api/network",
    tags=["Network Diagnostics"],
)


@router.get("/pods", response_model=PodListResponse)
def get_pods(
    v1: client.CoreV1Api = Depends(get_core_v1_api),
):
    try:
        return list_pods(v1, namespace="iomt-dev-1")

    except ApiException as e:
        if e.status == 403:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to list Kubernetes pods",
            ) from e

        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve Kubernetes pods",
        ) from e


@router.get(
    "/capture-targets",
    response_model=CaptureTargetsResponse,
)
def get_capture_targets(
    v1: client.CoreV1Api = Depends(get_core_v1_api),
):
    namespace = "iomt-dev-1"

    try:
        targets = discover_capture_targets(
            core_api=v1,
            namespace=namespace,
        )

        return {
            "namespace": namespace,
            "targets_by_node": targets,
        }

    except ApiException as e:
        if e.status == 403:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to discover capture targets",
            ) from e

        raise HTTPException(
            status_code=503,
            detail="Unable to discover capture targets",
        ) from e

@router.post(
    "/captures",
    status_code=202,
    response_model=NetshootCaptureStartResponse,
)
def start_netshoot_capture(
    request: NetshootCaptureStartRequest,
    core: client.CoreV1Api = Depends(get_core_v1_api),
    batch: client.BatchV1Api = Depends(get_batch_v1_api),
):
    """Validate configuration and schedule Pod-level Netshoot Jobs."""

    # Only allow explicitly approved namespaces.
    allowed = {
        name.strip()
        for name in os.environ.get(
            "IOMT_NETSHOOT_ALLOWED_NAMESPACES",
            "iomt-dev-1",
        ).split(",")
        if name.strip()
    }

    unauthorized = set(request.namespaces) - allowed

    if unauthorized:
        raise HTTPException(
            status_code=403,
            detail=f"Namespaces not approved for capture: {sorted(unauthorized)}",
        )

    try:
        scheduled = schedule_capture_jobs(
            core_api=core,
            batch_api=batch,
            namespaces=request.namespaces,
            duration_seconds=request.duration_seconds,
        )

    except CaptureSchedulingCleanupError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    "Capture scheduling failed, and some Jobs "
                    "may still require cleanup."
                ),
                "job_names": exc.job_names,
            },
    ) from exc

    except ApiException as exc:
        if exc.status == 403:
            raise HTTPException(
                status_code=403,
                detail="Insufficient Kubernetes permissions",
            ) from exc

        raise HTTPException(
            status_code=503,
            detail="Unable to schedule Netshoot Jobs",
        ) from exc

    if not scheduled:
        raise HTTPException(
            status_code=404,
            detail="No eligible running Pods found",
        )

    return {
        "duration_seconds": request.duration_seconds,
        "jobs_by_node": scheduled,
    }


@router.post("/captures/validate", response_model = PodInfo)
def validate_capture_request(
    request: CaptureRequest,
    v1: client.CoreV1Api = Depends(get_core_v1_api)
):
    return validate_capture_target(
        v1,
        pod_name = request.pod_name,
        namespace = "iomt-dev-1"
    )


@router.post("/captures/demo")
def download_demo_captures(
    v1: client.CoreV1Api = Depends(get_core_v1_api),
):
    archive = capture_demo_zip(v1)

    return Response(
        content=archive,
        media_type="application/zip",
        headers={
            "Content-Disposition":
                'attachment; filename="iomt-demo-captures.zip"'
        },
    )

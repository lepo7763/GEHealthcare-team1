from fastapi import APIRouter, Depends, HTTPException
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.core.k8s_client import get_core_v1_api
from .service import list_pods, validate_capture_target
from .schemas import (PodListResponse, PodInfo, CaptureRequest, CaptureTargetsResponse)
from fastapi.responses import Response
from .demo_capture import capture_demo_zip
from .job_service import discover_capture_targets



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

from fastapi import APIRouter

from .schemas import (
    DiscoverRequest,
    DiscoverResponse,
    EnvironmentCheckRequest,
    EnvironmentCheckResponse,
)
from .service import check_authentication, check_reachability, discover_components

router = APIRouter(prefix="/api/environments", tags=["Environments"])


@router.post("/check", response_model=EnvironmentCheckResponse)
def check_environment(req: EnvironmentCheckRequest) -> EnvironmentCheckResponse:
    """
    Runs both readiness gates for the Environments step.

    Reachability probes the operator-supplied host; authentication probes the
    cluster described by ~/.kube/config. See service.py for why these can point
    at different machines.
    """
    reachability = check_reachability(req.host, req.port)
    authentication = check_authentication()

    return EnvironmentCheckResponse(
        ok=reachability.ok and authentication.ok,
        host=req.host,
        port=req.port,
        reachability=reachability,
        authentication=authentication,
    )


@router.post("/discover", response_model=DiscoverResponse)
def discover_environment(req: DiscoverRequest) -> DiscoverResponse:
    """Connects to the platform and lists its nodes and services."""
    return discover_components(req.host, req.port, req.username, req.password)

from fastapi import APIRouter

from .schemas import EnvironmentCheckRequest, EnvironmentCheckResponse
from .service import check_authentication, check_reachability

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

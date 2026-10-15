from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints


class EnvironmentCheckRequest(BaseModel):
    host: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=253),
    ] = Field(
        ...,
        description="IPv4/IPv6 address or hostname of the platform to probe",
    )
    port: int = Field(
        default=6443,
        ge=1,
        le=65535,
        description="Kubernetes API server port to probe on the platform",
    )


class ReachabilityResult(BaseModel):
    """Outcome of opening a TCP connection to the platform's Kubernetes port."""

    ok: bool
    status: str
    message: str
    latency_ms: Optional[int] = None


class AuthenticationResult(BaseModel):
    """Outcome of validating the local ~/.kube/config against the cluster."""

    ok: bool
    status: str
    message: str
    allowed: Optional[bool] = None
    reason: Optional[str] = None
    context: Optional[str] = None
    server: Optional[str] = None
    user: Optional[str] = None


class EnvironmentCheckResponse(BaseModel):
    ok: bool
    host: str
    port: int
    reachability: ReachabilityResult
    authentication: AuthenticationResult

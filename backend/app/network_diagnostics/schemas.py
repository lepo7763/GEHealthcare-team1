from pydantic import BaseModel, Field


class PodInfo(BaseModel):
    name: str
    status: str
    ip: str | None = None


class PodListResponse(BaseModel):
    namespace: str
    pods: list[PodInfo]

class CaptureRequest(BaseModel):
    pod_name: str = Field(min_length=1)
    duration_seconds: int = Field(default=10, ge=1, le=30, strict=True, validate_default=True)

class CaptureTargetInfo(BaseModel):
    name: str
    namespace: str
    uid: str
    ip: str


class CaptureTargetsResponse(BaseModel):
    namespace: str
    targets_by_node: dict[str, list[CaptureTargetInfo]]

class NetshootCaptureStartRequest(BaseModel):
    """Configuration supplied by an engineer to start Pod-level capture."""

    namespaces: list[str] = Field(
        default_factory=lambda: ["iomt-dev-1"],
        min_length=1,
    )

    duration_seconds: int = Field(
        default=30,
        ge=1,
        le=600,
        strict=True,
    )

class ScheduledNetshootJob(BaseModel):
    """Information about a Netshoot Job created on one node."""

    job_name: str
    targets: list[CaptureTargetInfo]


class NetshootCaptureStartResponse(BaseModel):
    """Response returned after Netshoot Jobs are scheduled."""

    duration_seconds: int
    jobs_by_node: dict[str, ScheduledNetshootJob]


    
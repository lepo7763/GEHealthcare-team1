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


    
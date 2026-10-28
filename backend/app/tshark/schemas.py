from pydantic import BaseModel, ConfigDict, Field
# current resource policy in kubernetes/iomt-dev-resources.yaml
# validate the request’s capture settings

class WiresharkCaptureParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface: str = Field(
        default="any",
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9_.:-]+$",
        description="Capture interface available to the approved capture target",
    )
    duration_seconds: int = Field(
        default=60,
        ge=10,
        le=120,
        description="Maximum capture duration in seconds. Kept below the active cluster quota headroom.",
    )
    max_file_size_mb: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Maximum capture file size in megabytes. Intended to keep packet captures below the active dev quota.",
    )

    resource_cpu_limit: str = Field(
        default="250m",
        pattern=r"^[0-9]+m$",
        description="CPU limit for the capture pod; kept within the current dev K8s quota.",
    )
    resource_memory_limit: str = Field(
        default="128Mi",
        pattern=r"^[0-9]+(?:Mi|Gi)$",
        description="Memory limit for the capture pod; kept within the current dev K8s quota.",
    )
    resource_cpu_request: str = Field(
        default="50m",
        pattern=r"^[0-9]+m$",
        description="CPU request for the capture pod.",
    )
    resource_memory_request: str = Field(
        default="64Mi",
        pattern=r"^[0-9]+(?:Mi|Gi)$",
        description="Memory request for the capture pod.",
    )
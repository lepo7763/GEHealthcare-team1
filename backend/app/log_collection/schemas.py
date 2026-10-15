from pydantic import BaseModel, Field
from typing import List, Optional


class LogCollectionParams(BaseModel):
    max_bytes_per_container: int = Field(
        default=5 * 1024 * 1024,  # 5 MB default cap per log file
        gt=0,
        description="Maximum bytes to fetch per container log",
    )
    tail_lines: Optional[int] = Field(
        default=None, gt=0, description="Optional number of recent lines to fetch"
    )
    include_previous: bool = Field(
        default=True,
        description="Also fetch logs from previous crashed container instances",
    )
    throttle_delay_ms: int = Field(
        default=50,
        ge=0,
        le=5000,
        description="Delay in milliseconds between K8s API requests to reduce cluster load",
    )


class LogErrorEntry(BaseModel):
    namespace: str
    pod: str
    container: str
    reason: str
    status: Optional[int] = None


class LogCollectionManifest(BaseModel):
    timestamp_utc: str
    total_logs_collected: int
    collected_files: List[str] = []
    errors: List[LogErrorEntry] = []

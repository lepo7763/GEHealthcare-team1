from typing import List, Optional
from pydantic import BaseModel, Field


class UmfRtiParams(BaseModel):
    """
    Query parameters for UMF RTI collection on GET /api/logs/zip.
    Prefixed with `umf_` so they sit cleanly alongside container log params.
    """

    umf_domain_id: int = Field(
        default=12,
        ge=0,
        le=100,
        description="DDS Domain ID to join and inspect (e.g., 12 or 32)",
    )
    umf_duration_seconds: int = Field(
        default=120,
        ge=30,
        le=600,
        description="Duration in seconds to poll UMF RTI discovery",
    )
    umf_max_bytes: int = Field(
        default=20 * 1024 * 1024,  # 20 MiB default cap
        ge=1024,
        le=100 * 1024 * 1024,
        description="Maximum bytes of NDJSON discovery output to read from the collector pod",
    )


class UmfRtiCaptureResult(BaseModel):
    """
    Holds the raw NDJSON output, parsed entity counts, and execution metadata
    from a completed (or failed) UMF RTI Job run.
    """

    domain_id: int
    duration_seconds: int
    router_peer: str
    image: str
    namespace: str
    job_name: str
    pod_name: Optional[str] = None
    started_at_utc: str
    finished_at_utc: str
    exit_code: Optional[int] = None
    ndjson_text: str = ""
    log_bytes: int = 0
    truncated: bool = False
    participants_count: int = 0
    topics_count: int = 0
    writers_count: int = 0
    readers_count: int = 0
    collector_version: Optional[str] = None
    warnings: List[str] = []
    error: Optional[str] = None
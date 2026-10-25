"""Pydantic models for UMF RTI capture requests and results."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class UmfRtiParams(BaseModel):
    """Query parameters accepted by the diagnostics download endpoint."""

    umf_domain_id: int = Field(
        default=32,
        ge=0,
        le=100,
        description=(
            "UMF DDS domain. 32 is the live platform UMF domain in the lab; "
            "12 is selectable but requires an identity permitted on that domain."
        ),
    )
    umf_duration_seconds: int = Field(
        default=120,
        ge=30,
        le=600,
        description="How long the UMF RTI job listens for discovery data.",
    )
    umf_max_bytes: int = Field(
        default=20 * 1024 * 1024,
        ge=1024,
        le=100 * 1024 * 1024,
        description="Maximum collector log bytes fetched from the pod.",
    )


class UmfRtiCaptureResult(BaseModel):
    """Everything the orchestrator needs to write UMF RTI artifacts."""

    domain_id: int
    duration_seconds: int
    router_peer: str
    router_port: int
    namespace: str
    job_name: str
    pod_name: Optional[str] = None
    node_name: Optional[str] = None
    image: str
    status: str = "unknown"  # succeeded | failed | timeout
    exit_code: Optional[int] = None
    started_at_utc: str
    finished_at_utc: str
    log_text: str = ""
    log_bytes: int = 0
    truncated: bool = False
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    counts: Dict[str, int] = Field(default_factory=dict)
    collector_version: Optional[str] = None
    rti_version: Optional[str] = None
    job_deleted: bool = False

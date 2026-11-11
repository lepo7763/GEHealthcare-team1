"""Request params and result model for a UMF-RTI capture.

The end user chooses only a domain and a duration (`UmfRtiParams`); everything
else about how the capture runs lives in config.py. `UmfRtiCaptureResult`
describes what a recording produced and is serialized into the zip as
`summary.json`.
"""

from enum import IntEnum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class UmfDomain(IntEnum):
    """Domains the image's built-in Test certs authorize (7/12/13).

    Others (e.g. 32 trunk, 34 persistence) aren't in that cert scope and would
    fail the DDS security handshake, so they're rejected (422), not offered.
    An IntEnum (not Literal[7, 12, 13]) so the query-string value "13" is
    accepted. Must stay in sync with the domain labels in config.py.
    """

    VIEWER = 13
    SOURCE = 12
    LOGGER = 7


class UmfRtiParams(BaseModel):
    """What the end user picks: which domain to record and for how long."""

    umf_domain_id: UmfDomain = Field(
        default=UmfDomain.VIEWER,
        description="DDS domain to record (13 = viewpod / live vitals, 12 = sourcepod, 7 = logger)",
    )
    umf_duration_seconds: int = Field(
        default=60,
        ge=10,
        le=600,
        description="How long to record, in seconds",
    )


class UmfRtiCaptureResult(BaseModel):
    """Outcome of a capture run; serialized into the zip as summary.json."""

    domain_id: int
    duration_seconds: int

    # The recording is a set of SQLite files (user-data + discovery.db + metadata.db).
    recording_files: List[str] = Field(
        default_factory=list,
        description="Recording files bundled into the zip",
    )
    user_data_file: Optional[str] = Field(
        default=None,
        description="The user-data SQLite file holding the recorded samples",
    )

    # Parsed from the user-data DB: rows per topic table, and the sum.
    topic_sample_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Samples captured per topic",
    )
    total_samples: int = Field(
        default=0, description="Total samples captured across all topics"
    )

    # Non-fatal notes, e.g. "no samples captured (source may be idle)".
    warnings: List[str] = Field(default_factory=list)

    # Local temp dir holding the pulled recording files, for the zip step to read.
    # Excluded from serialization (not part of summary.json); the caller deletes it.
    recording_dir: Optional[str] = Field(default=None, exclude=True)

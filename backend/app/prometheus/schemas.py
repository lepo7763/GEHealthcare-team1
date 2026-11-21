from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PrometheusParams(BaseModel):
    """Time window to export. Empty bounds mean "everything"."""

    since: Optional[datetime] = Field(
        default=None, description="Only data at or after this time (UTC)."
    )
    until: Optional[datetime] = Field(
        default=None, description="Only data at or before this time (UTC)."
    )


class TsdbFile(BaseModel):
    """One file inside a data directory; ``path`` is relative to the host dir."""

    path: str
    size_bytes: int


class TsdbBlock(BaseModel):
    """A persisted TSDB block: an immutable directory covering [min_time, max_time)."""

    ulid: str
    data_dir: str  # relative to the host dir; "." when host_dir is the data dir
    min_time: datetime
    max_time: datetime
    num_samples: Optional[int] = None
    num_series: Optional[int] = None
    size_bytes: int = 0
    files: List[TsdbFile] = Field(default_factory=list, exclude=True)
    # Original level-1 blocks this one was compacted from (itself if not compacted).
    sources: List[str] = Field(default_factory=list, exclude=True)


class TsdbHead(BaseModel):
    """The in-memory head's on-disk state (WAL + mmapped head chunks).

    Covers from the newest block's max_time (``min_time``) up to now. These
    files are still being written, so they are copied without a checksum.
    """

    data_dir: str
    min_time: Optional[datetime] = None
    size_bytes: int = 0
    files: List[TsdbFile] = Field(default_factory=list, exclude=True)


class TsdbDataDir(BaseModel):
    path: str
    blocks: List[TsdbBlock] = Field(default_factory=list)
    head: Optional[TsdbHead] = None


class CollectedTsdbFile(BaseModel):
    path: str
    archive_path: Optional[str] = None
    size_bytes: int = 0
    sha256: Optional[str] = None
    verified: bool = False
    status: str  # collected | error
    error: Optional[str] = None


class PrometheusCollectionSummary(BaseModel):
    """prometheus/prometheus.json inside the package."""

    host_dir: str
    node: Optional[str] = None
    filters: PrometheusParams
    available_bytes: int = 0
    selected_bytes: int = 0
    covered_from: Optional[datetime] = None
    covered_until: Optional[datetime] = None
    data_dirs: List[TsdbDataDir] = Field(default_factory=list)
    collected: List[CollectedTsdbFile] = Field(default_factory=list)

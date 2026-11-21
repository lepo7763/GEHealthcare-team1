from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CoreDumpParams(BaseModel):
    """What the user filters on. Empty filters mean "everything"."""

    since: Optional[datetime] = Field(
        default=None, description="Only cores dumped at or after this time (UTC)."
    )
    until: Optional[datetime] = Field(
        default=None, description="Only cores dumped at or before this time (UTC)."
    )
    processes: List[str] = Field(
        default_factory=list, description="Only cores from these process names."
    )


class CoreDumpFile(BaseModel):
    """One core file on the node, with fields parsed from its name.

    ``path`` is relative to the core directory: a bare name for cores written
    by coredump_handler.sh, ``<pv-dir>/<file>`` for files inside a coredump PVC.
    """

    path: str
    source: str  # "kernel-handler" | "pvc:<namespace>/<claim>"
    size_bytes: int
    mtime_utc: datetime
    process: Optional[str] = None
    pid: Optional[int] = None
    signal: Optional[int] = None
    signal_name: Optional[str] = None
    uid: Optional[int] = None
    gid: Optional[int] = None
    # From the handler's %t when the name parses, else the file mtime.
    time_utc: datetime


class HostCoreConfig(BaseModel):
    """Kernel/handler settings that explain where cores go (or why none exist)."""

    core_pattern: Optional[str] = None
    core_pipe_limit: Optional[str] = None
    disk_total_bytes: Optional[int] = None
    disk_available_bytes: Optional[int] = None
    coredump_pvc_dirs: Dict[str, int] = Field(
        default_factory=dict, description="Coredump PV directory -> file count."
    )


class CoreDumpListResponse(BaseModel):
    files: List[CoreDumpFile] = Field(default_factory=list)
    total_bytes: int = 0
    host_config: HostCoreConfig = Field(default_factory=HostCoreConfig)
    host_dir: str
    collector_pod: Optional[str] = None
    node: Optional[str] = None


class CollectedCoreDump(BaseModel):
    """Per-file record in core-dumps/core_dumps.json inside the package."""

    file: CoreDumpFile
    archive_path: Optional[str] = None
    sha256: Optional[str] = None
    status: str  # collected | error
    error: Optional[str] = None


class CoreDumpCollectionSummary(BaseModel):
    host_dir: str
    node: Optional[str] = None
    filters: CoreDumpParams
    host_config: HostCoreConfig
    available_count: int
    available_bytes: int
    collected: List[CollectedCoreDump] = Field(default_factory=list)

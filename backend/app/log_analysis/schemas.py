from pydantic import BaseModel
from typing import List, Optional


class ContainerSummary(BaseModel):
    namespace: str
    pod: str
    container: str
    # True for <container>_previous.log, i.e. the log from before the container last crashed
    is_previous: bool
    total_lines: int
    error_lines: int
    warning_lines: int
    first_error: Optional[str] = None


class Recommendation(BaseModel):
    # Short name of the likely cause, e.g. "Lost etcd leadership"
    title: str
    # What the field engineer should check or do next
    action: str


class ErrorPattern(BaseModel):
    # Error line with timestamps, numbers and IDs replaced so repeats group together
    pattern: str
    count: int
    # A real line that matched, so the user sees what it actually looked like
    example: str
    # "namespace/pod/container" of every container this error showed up in
    containers: List[str]
    # Suggested next step, when the error matches a known rule (None if we don't recognize it)
    recommendation: Optional[Recommendation] = None


class AnalysisReport(BaseModel):
    collected_at: Optional[str] = None
    files_analyzed: int
    total_lines: int
    error_lines: int
    warning_lines: int
    # Containers that restarted at least once (a _previous.log exists for them)
    crashed_containers: List[str] = []
    top_errors: List[ErrorPattern] = []
    # Sorted with the noisiest containers first
    containers: List[ContainerSummary] = []
    # Containers whose logs the collector could not fetch, copied from manifest.json
    collection_errors: List[dict] = []
    # Files in the zip we did not analyze, with the reason
    skipped_files: List[str] = []

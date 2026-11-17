import json
import re
import zipfile
from collections import defaultdict
from typing import BinaryIO, Optional, Tuple

from .recommendations import recommend_action
from .schemas import AnalysisReport, ContainerSummary, ErrorPattern


class InvalidLogArchiveError(Exception):
    """Raised when the uploaded file is not a zip we can analyze."""

    pass


# Refuse archives that would unzip to more than this. A zip is tiny on the wire but can
# expand massively (a "zip bomb"), and we read every file into memory line by line.
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
TOP_ERRORS_LIMIT = 10
MAX_PATTERN_LENGTH = 200

# The collector calls K8s with timestamps=True, so every line starts with an RFC 3339 timestamp
# like "2026-10-03T21:13:50.346400123Z ". Strip it so it doesn't hide the log level.
K8S_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\S+\s")

# Services on the box log in different styles, so we check the common ones:
#   plain:  "ERROR something broke"   or "[ERROR]"
#   logfmt: "level=error msg=..."
#   JSON:   {"level":"error", ...}
#   klog (Kubernetes/k3s itself): "E1003 21:10:23.197077 ..." where E = error, W = warning
# Plain words are matched in UPPERCASE only on purpose: lowercase "error" shows up in
# normal messages like "0 errors" or "error rate 0.1%" and would flood the report.
ERROR_RE = re.compile(
    r"\b(ERROR|FATAL|PANIC|CRITICAL|SEVERE)\b"
    r"|^E\d{4}\s"
    r"|Traceback \(most recent call last\)"
    r"|\b\w+(Exception|Error):"
)
# level=/"level": values are lowercase in practice, so these two are case-insensitive
ERROR_LEVEL_RE = re.compile(r"level\"?[=:]\s*\"?(error|fatal|panic|critical)", re.IGNORECASE)
WARNING_RE = re.compile(r"\b(WARN|WARNING)\b|^W\d{4}\s")
WARNING_LEVEL_RE = re.compile(r"level\"?[=:]\s*\"?(warn|warning)\b", re.IGNORECASE)

# Used to turn "Timeout after 1500ms on 10.0.0.5" and "Timeout after 900ms on 10.0.0.7"
# into the same pattern so we can count how often each kind of error happens.
NORMALIZERS = [
    # klog header "E1003 21:10:23.197077   12600 " -> "E " (date, time and PID change every line)
    (re.compile(r"^([IWEF])\d{4} [\d:.]+\s+\d+\s"), r"\1 "),
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ][\d:.]+Z?"), "<TIME>"),
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "<UUID>"),
    (re.compile(r"\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b"), "<IP>"),
    # Go-style durations: 1500ms, 44.12s, 1m46.687s
    (re.compile(r"\b(\d+(\.\d+)?(ns|us|µs|ms|s|m|h))+\b"), "<DURATION>"),
    (re.compile(r"\b[0-9a-f]{8,}\b", re.I), "<HEX>"),
    # Only standalone numbers, so names like "k3s" or "v1" stay readable
    (re.compile(r"\b\d+\b"), "<N>"),
]


def classify_line(line: str) -> Optional[str]:
    """Returns "error", "warning", or None for a single log line."""
    line = K8S_TIMESTAMP.sub("", line, count=1)
    if ERROR_RE.search(line) or ERROR_LEVEL_RE.search(line):
        return "error"
    if WARNING_RE.search(line) or WARNING_LEVEL_RE.search(line):
        return "warning"
    return None


def normalize_error(line: str) -> str:
    """Replaces the parts of an error line that change every time (times, IDs, numbers)."""
    text = K8S_TIMESTAMP.sub("", line, count=1).strip()
    for pattern, placeholder in NORMALIZERS:
        text = pattern.sub(placeholder, text)
    return text[:MAX_PATTERN_LENGTH]


def _parse_log_path(path: str) -> Optional[Tuple[str, str, str, bool]]:
    """
    The collector writes logs to logs/<namespace>/<pod>/<container>.log
    (and <container>_previous.log for crashed containers). This is the contract
    with app/log_collection/service.py, so if that path changes this must change too.
    """
    parts = path.split("/")
    if len(parts) != 4 or parts[0] != "logs" or not parts[3].endswith(".log"):
        return None
    namespace, pod, filename = parts[1], parts[2], parts[3][: -len(".log")]
    is_previous = filename.endswith("_previous")
    container = filename[: -len("_previous")] if is_previous else filename
    if not namespace or not pod or not container:
        return None
    return namespace, pod, container, is_previous


def open_log_archive(file: BinaryIO) -> Tuple[zipfile.ZipFile, list]:
    """
    Opens an uploaded zip and returns (zipfile, file entries). Shared by the analysis and the
    privacy scan so both reject bad uploads the same way.
    """
    try:
        zf = zipfile.ZipFile(file)
    except zipfile.BadZipFile as e:
        raise InvalidLogArchiveError("File is not a valid zip archive") from e

    entries = [info for info in zf.infolist() if not info.is_dir()]
    if sum(info.file_size for info in entries) > MAX_UNCOMPRESSED_BYTES:
        zf.close()
        raise InvalidLogArchiveError(
            f"Archive unzips to more than {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB"
        )
    return zf, entries


def read_log_text(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    """Reads one file from the zip as text. Raises zipfile.BadZipFile/RuntimeError if unreadable."""
    # errors="replace" so one bad byte in a binary-ish log doesn't drop the whole file
    return zf.read(info).decode("utf-8", errors="replace")


def analyze_log_archive(file: BinaryIO) -> AnalysisReport:
    """Reads a zip produced by GET /api/logs/zip and summarizes errors and warnings in it."""
    zf, entries = open_log_archive(file)

    with zf:
        report = AnalysisReport(
            files_analyzed=0, total_lines=0, error_lines=0, warning_lines=0
        )
        # pattern -> {"count", "example", "containers"}
        patterns: dict = defaultdict(lambda: {"count": 0, "example": "", "containers": set()})

        for info in entries:
            if info.filename == "manifest.json":
                _read_manifest(zf, info, report)
                continue

            parsed = _parse_log_path(info.filename)
            if parsed is None:
                report.skipped_files.append(f"{info.filename} (not a container log)")
                continue
            namespace, pod, container, is_previous = parsed

            try:
                text = read_log_text(zf, info)
            except (zipfile.BadZipFile, RuntimeError) as e:
                report.skipped_files.append(f"{info.filename} (could not read: {e})")
                continue

            label = f"{namespace}/{pod}/{container}"
            summary = ContainerSummary(
                namespace=namespace,
                pod=pod,
                container=container,
                is_previous=is_previous,
                total_lines=0,
                error_lines=0,
                warning_lines=0,
            )

            for line in text.splitlines():
                if not line.strip():
                    continue
                summary.total_lines += 1
                level = classify_line(line)
                if level == "error":
                    summary.error_lines += 1
                    message = K8S_TIMESTAMP.sub("", line, count=1).strip()
                    if summary.first_error is None:
                        summary.first_error = message
                    entry = patterns[normalize_error(line)]
                    entry["count"] += 1
                    entry["example"] = entry["example"] or message
                    entry["containers"].add(label)
                elif level == "warning":
                    summary.warning_lines += 1

            if is_previous:
                report.crashed_containers.append(label)

            report.files_analyzed += 1
            report.total_lines += summary.total_lines
            report.error_lines += summary.error_lines
            report.warning_lines += summary.warning_lines
            report.containers.append(summary)

    if report.files_analyzed == 0 and not report.collection_errors:
        raise InvalidLogArchiveError(
            "No container logs found. Expected files like logs/<namespace>/<pod>/<container>.log"
        )

    # Noisiest containers first so the field engineer sees the likely culprit at the top
    report.containers.sort(key=lambda c: (-c.error_lines, -c.warning_lines, c.namespace, c.pod))
    report.crashed_containers.sort()
    report.top_errors = [
        ErrorPattern(
            pattern=pattern,
            count=data["count"],
            example=data["example"],
            containers=sorted(data["containers"]),
            recommendation=recommend_action(data["example"]),
        )
        for pattern, data in sorted(patterns.items(), key=lambda kv: -kv[1]["count"])[
            :TOP_ERRORS_LIMIT
        ]
    ]
    return report


def _read_manifest(zf: zipfile.ZipFile, info: zipfile.ZipInfo, report: AnalysisReport) -> None:
    """Copies collection time and fetch failures from the collector's manifest.json."""
    try:
        manifest = json.loads(zf.read(info))
    except (ValueError, zipfile.BadZipFile, RuntimeError):
        report.skipped_files.append("manifest.json (not valid JSON)")
        return
    report.collected_at = manifest.get("timestamp_utc")
    report.collection_errors = manifest.get("errors") or []

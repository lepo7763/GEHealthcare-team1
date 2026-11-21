"""Pure helpers: parse the collector's listing and core filenames, apply filters.

No Kubernetes here, so everything in this module is unit-testable directly.
"""

from __future__ import annotations

import posixpath
import re
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

from .schemas import (
    CoreDumpFile,
    CoreDumpParams,
    HostCoreConfig,
)

# coredump_handler.sh writes
#   /var/log/files/core.<%e>.pid<%p>.sig<%s>.usr<%u>.grp<%g>.time<%t>
# (whitespace in %e replaced by "_"); something later gzips it in place.
# %e may itself contain dots, so the process group is greedy and the numeric
# fields are anchored to the end.
_CORE_NAME = re.compile(
    r"^core\.(?P<process>.+)\.pid(?P<pid>\d+)\.sig(?P<signal>\d+)"
    r"\.usr(?P<uid>\d+)\.grp(?P<gid>\d+)\.time(?P<time>\d+)(?:\.gz)?$"
)

# local-path provisioner directory name: pvc-<uid>_<namespace>_<claim>
_PV_DIR = re.compile(r"^pvc-[0-9a-f-]+_(?P<namespace>[^_]+)_(?P<claim>.+)$")

# Signals that produce a core by default on Linux.
SIGNAL_NAMES = {
    3: "SIGQUIT",
    4: "SIGILL",
    5: "SIGTRAP",
    6: "SIGABRT",
    7: "SIGBUS",
    8: "SIGFPE",
    11: "SIGSEGV",
    24: "SIGXCPU",
    25: "SIGXFSZ",
    31: "SIGSYS",
}

# Shell run inside the collector pod (cwd = the read-only host mount).
# One record per line, tagged by its first field:
#   F <size> <mtime> <relative path>   a candidate core file
#   D <dir>                            a coredump PV directory
#   P <core_pattern>   L <core_pipe_limit>   S <total_kb> <avail_kb>
LISTING_SCRIPT = r"""
for f in core.*; do
  [ -f "$f" ] && stat -c 'F %s %Y %n' "$f"
done
for d in pvc-*coredump*; do
  [ -d "$d" ] || continue
  echo "D $d"
  find "$d" -type f -exec stat -c 'F %s %Y %n' {} \;
done
echo "P $(cat /proc/sys/kernel/core_pattern 2>/dev/null)"
echo "L $(cat /proc/sys/kernel/core_pipe_limit 2>/dev/null)"
df -P -k . 2>/dev/null | awk 'NR==2 {print "S", $2, $4}'
exit 0
"""


def _from_epoch(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def is_safe_relative_path(path: str) -> bool:
    """True for a plain relative path that stays inside the core directory."""
    if not path or path.startswith("/") or "\x00" in path or "\n" in path:
        return False
    normalized = posixpath.normpath(path)
    return normalized == path and not normalized.startswith("..")


def describe_source(path: str) -> str:
    if "/" not in path:
        return "kernel-handler"
    top = path.split("/", 1)[0]
    match = _PV_DIR.match(top)
    if match:
        return f"pvc:{match['namespace']}/{match['claim']}"
    return f"dir:{top}"


def parse_core_file(path: str, size_bytes: int, mtime: int) -> CoreDumpFile:
    """Build a CoreDumpFile, parsing handler fields from the basename if present."""
    mtime_utc = _from_epoch(mtime)
    entry = {
        "path": path,
        "source": describe_source(path),
        "size_bytes": size_bytes,
        "mtime_utc": mtime_utc,
        "time_utc": mtime_utc,
    }
    match = _CORE_NAME.match(posixpath.basename(path))
    if match:
        signal = int(match["signal"])
        entry.update(
            process=match["process"],
            pid=int(match["pid"]),
            signal=signal,
            signal_name=SIGNAL_NAMES.get(signal, f"SIG{signal}"),
            uid=int(match["uid"]),
            gid=int(match["gid"]),
            time_utc=_from_epoch(int(match["time"])),
        )
    return CoreDumpFile(**entry)


def parse_listing(output: str) -> Tuple[List[CoreDumpFile], HostCoreConfig]:
    """Parse LISTING_SCRIPT output. Unknown or malformed lines are ignored."""
    files: List[CoreDumpFile] = []
    config = HostCoreConfig()
    for raw in output.splitlines():
        tag, _, rest = raw.partition(" ")
        if tag == "F":
            parts = rest.split(" ", 2)
            if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
                continue
            path = parts[2]
            if not is_safe_relative_path(path):
                continue
            files.append(parse_core_file(path, int(parts[0]), int(parts[1])))
        elif tag == "D" and rest:
            config.coredump_pvc_dirs.setdefault(rest, 0)
        elif tag == "P":
            config.core_pattern = rest.strip() or None
        elif tag == "L":
            config.core_pipe_limit = rest.strip() or None
        elif tag == "S":
            parts = rest.split()
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                config.disk_total_bytes = int(parts[0]) * 1024
                config.disk_available_bytes = int(parts[1]) * 1024

    for f in files:
        top = f.path.split("/", 1)[0]
        if top in config.coredump_pvc_dirs:
            config.coredump_pvc_dirs[top] += 1

    files.sort(key=lambda f: (f.time_utc, f.path), reverse=True)
    return files, config


def select_files(
    files: Iterable[CoreDumpFile], params: CoreDumpParams
) -> List[CoreDumpFile]:
    """Apply the time and process filters; newest first. No size cap."""
    since: Optional[datetime] = params.since
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    wanted = {p for p in params.processes if p}
    return [
        f
        for f in sorted(files, key=lambda f: (f.time_utc, f.path), reverse=True)
        if (since is None or f.time_utc >= since)
        and (not wanted or f.process in wanted)
    ]


def archive_name(path: str) -> str:
    return f"core-dumps/{path}"

"""Pure helpers: parse the collector's TSDB listing and pick blocks by time.

A Prometheus data directory looks like::

    <data-dir>/
      01JD3.../            one directory per persisted block (named by ULID)
        meta.json          {"minTime": <ms>, "maxTime": <ms>, "stats": {...}}
        index, tombstones, chunks/000001 ...
      chunks_head/         mmapped chunks of the in-memory head
      wal/                 write-ahead log for the head (incl. checkpoint.N/)

Blocks are immutable and cover [minTime, maxTime): 2 h when first written,
compacted into larger blocks later (up to 10% of retention). Selection is
per block, so the exported window is rounded out to whole blocks.

No Kubernetes here, so everything in this module is unit-testable directly.
"""

from __future__ import annotations

import json
import posixpath
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.core_dumps.parsing import is_safe_relative_path

from .schemas import (
    PrometheusParams,
    TsdbBlock,
    TsdbDataDir,
    TsdbFile,
    TsdbHead,
)

ARCHIVE_ROOT = "prometheus"

# Crockford base32 ULID; excludes in-flight dirs like <ULID>.tmp-for-creation.
_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")

# Shell run inside the collector pod (cwd = the read-only host mount, $1 = depth).
# One record per line, tagged by its first field:
#   M <block dir> <meta.json on one line>   a persisted block
#   H <data dir>                            a data dir with a WAL (the head)
#   F <size> <path>                         a file of the preceding M/H record
LISTING_SCRIPT = r"""
depth="$2"
find . -maxdepth "$depth" -type f -name meta.json 2>/dev/null | while read -r m; do
  b="${m%/meta.json}"
  printf 'M %s ' "$b"; tr -d '\n\r' < "$m"; echo
  find "$b" -type f -exec stat -c 'F %s %n' {} \;
done
find . -maxdepth "$((depth - 1))" -type d -name wal 2>/dev/null | while read -r w; do
  d="${w%/wal}"
  echo "H $d"
  for x in "$d/wal" "$d/chunks_head"; do
    [ -d "$x" ] && find "$x" -type f -exec stat -c 'F %s %n' {} \;
  done
done
exit 0
"""


def _clean(path: str) -> str:
    """find prints ./a/b; make it a plain relative path ("." for the root)."""
    while path.startswith("./"):
        path = path[2:]
    return path or "."


def _from_ms(value) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _parse_block(path: str, meta_text: str) -> Optional[TsdbBlock]:
    name = posixpath.basename(path)
    if not _ULID.match(name) or not is_safe_relative_path(path):
        return None
    try:
        meta = json.loads(meta_text)
    except ValueError:
        return None
    if not isinstance(meta, dict):
        return None
    min_time, max_time = _from_ms(meta.get("minTime")), _from_ms(meta.get("maxTime"))
    if min_time is None or max_time is None:
        return None
    stats = meta.get("stats") if isinstance(meta.get("stats"), dict) else {}
    compaction = meta.get("compaction") if isinstance(meta.get("compaction"), dict) else {}
    sources = [s for s in compaction.get("sources") or [] if isinstance(s, str)]
    return TsdbBlock(
        ulid=name,
        data_dir=posixpath.dirname(path) or ".",
        min_time=min_time,
        max_time=max_time,
        num_samples=stats.get("numSamples"),
        num_series=stats.get("numSeries"),
        sources=sources or [name],
    )


def parse_listing(output: str) -> List[TsdbDataDir]:
    """Parse LISTING_SCRIPT output into data dirs. Malformed records are dropped."""
    dirs: Dict[str, TsdbDataDir] = {}
    target = None  # the TsdbBlock / TsdbHead the next F lines belong to

    def data_dir(path: str) -> TsdbDataDir:
        return dirs.setdefault(path, TsdbDataDir(path=path))

    for raw in output.splitlines():
        tag, _, rest = raw.partition(" ")
        if tag == "M":
            path, _, meta_text = rest.partition(" ")
            block = _parse_block(_clean(path), meta_text)
            target = block
            if block:
                data_dir(block.data_dir).blocks.append(block)
        elif tag == "H" and rest:
            path = _clean(rest)
            target = None
            if path == "." or is_safe_relative_path(path):
                head = TsdbHead(data_dir=path)
                data_dir(path).head = head
                target = head
        elif tag == "F" and target is not None:
            size, _, path = rest.partition(" ")
            path = _clean(path)
            if not size.isdigit() or not is_safe_relative_path(path):
                continue
            target.files.append(TsdbFile(path=path, size_bytes=int(size)))
            target.size_bytes += int(size)

    for d in dirs.values():
        d.blocks.sort(key=lambda b: b.min_time)
        if d.head and d.blocks:
            d.head.min_time = max(b.max_time for b in d.blocks)
    return sorted(dirs.values(), key=lambda d: d.path)


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def select(
    data_dirs: List[TsdbDataDir], params: PrometheusParams
) -> Tuple[List[TsdbBlock], List[TsdbHead]]:
    """Blocks overlapping [since, until], plus the head if the window reaches it."""
    since, until = _utc(params.since), _utc(params.until)
    blocks: List[TsdbBlock] = []
    heads: List[TsdbHead] = []
    for d in data_dirs:
        for b in d.blocks:
            # maxTime is exclusive.
            if (since is None or b.max_time > since) and (
                until is None or b.min_time <= until
            ):
                blocks.append(b)
        head = d.head
        if head and (until is None or head.min_time is None or until >= head.min_time):
            heads.append(head)
    return blocks, heads


def coverage(
    blocks: List[TsdbBlock], heads: List[TsdbHead]
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """(from, until) actually exported; until is None when it runs up to now."""
    starts = [b.min_time for b in blocks] + [h.min_time for h in heads if h.min_time]
    start = min(starts) if starts else None
    if heads:
        return start, None
    return start, (max(b.max_time for b in blocks) if blocks else None)


def archive_name(path: str) -> str:
    return f"{ARCHIVE_ROOT}/{path}"

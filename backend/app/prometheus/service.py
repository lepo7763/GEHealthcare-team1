"""List the Prometheus TSDB on the node and package a time slice of it."""

from __future__ import annotations

import os
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Callable, List, Optional

from kubernetes import client

from app.core.workdir import work_dir

from app.log_collection.progress import (
    PROMETHEUS_LABEL,
    PROMETHEUS_SERVICE_ID,
    tracker,
)
from app.log_collection.schemas import (
    CollectedService,
    LogCollectionManifest,
    LogErrorEntry,
)

from .collector import PrometheusCollectionError, PrometheusSession
from .config import PrometheusConfig, get_prometheus_config
from .parsing import ARCHIVE_ROOT, archive_name, coverage, select
from .schemas import (
    CollectedTsdbFile,
    PrometheusCollectionSummary,
    PrometheusParams,
    TsdbBlock,
    TsdbDataDir,
    TsdbFile,
    TsdbHead,
)

SUMMARY_PATH = f"{ARCHIVE_ROOT}/prometheus.json"
_ATTEMPTS = 3
_MB = 1024 * 1024

SessionFactory = Callable[..., PrometheusSession]


def _total_bytes(data_dirs: List[TsdbDataDir]) -> int:
    return sum(
        sum(b.size_bytes for b in d.blocks) + (d.head.size_bytes if d.head else 0)
        for d in data_dirs
    )


def _compression_for(path: str) -> int:
    # Chunks are already XOR-encoded and the WAL is snappy-compressed by
    # default; deflating gigabytes of them gains little and costs a lot.
    parts = path.split("/")
    if "chunks" in parts or "chunks_head" in parts or "wal" in parts:
        return zipfile.ZIP_STORED
    return zipfile.ZIP_DEFLATED


def _add_error(manifest: LogCollectionManifest, pod: str, path: str, reason: str) -> None:
    manifest.errors.append(
        LogErrorEntry(
            namespace="(node)",
            pod=pod,
            container=path,
            reason=reason,
            service=PROMETHEUS_SERVICE_ID,
        )
    )


class _Staged:
    """Files of one unit (a block, or a head) copied to local disk, not yet zipped."""

    def __init__(self) -> None:
        self.items: List[tuple] = []  # (local path, CollectedTsdbFile)

    def discard(self) -> None:
        for local, _ in self.items:
            try:
                os.unlink(local)
            except OSError:
                pass
        self.items = []


def _stage_file(
    session: PrometheusSession,
    f: TsdbFile,
    verify: bool,
    workdir: str,
    progress: "_Progress",
) -> tuple:
    """Copy one file to local disk; block files are checked (sha256 and size)
    against the node and retried, since a long exec stream can occasionally
    arrive damaged. Head files (WAL, head chunks) are being appended to, so
    they can't be checksummed; Prometheus repairs a torn final WAL record."""
    last: Optional[Exception] = None
    for _ in range(_ATTEMPTS):
        mark = progress.done
        fd, local = tempfile.mkstemp(dir=workdir, prefix="tsdb-")
        try:
            expected = session.remote_sha256(f.path) if verify else None
            with os.fdopen(fd, "wb") as out:
                digest, size = session.fetch(f.path, out, on_bytes=progress.add)
            if verify and (digest != expected or size != f.size_bytes):
                raise PrometheusCollectionError(
                    f"{f.path} arrived damaged ({size} of {f.size_bytes} bytes, "
                    "checksum mismatch)"
                )
            record = CollectedTsdbFile(
                path=f.path,
                archive_path=archive_name(f.path),
                size_bytes=size,
                sha256=digest,
                verified=verify,
                status="collected",
            )
            return local, record
        except PrometheusCollectionError as e:
            last = e
            os.unlink(local)
            progress.set(mark)
            if _vanished(e):
                break  # compacted/truncated away: retrying the same path can't help
    raise last


def _vanished(e: Exception) -> bool:
    return "No such file" in str(e) or "can't open" in str(e)


def _stage_unit(session, files, verify, workdir, progress) -> _Staged:
    staged = _Staged()
    try:
        for f in files:
            progress.current(f.path)
            staged.items.append(_stage_file(session, f, verify, workdir, progress))
    except BaseException:
        staged.discard()
        raise
    return staged


def _zip_staged(zf: zipfile.ZipFile, staged: _Staged) -> List[CollectedTsdbFile]:
    records = []
    for local, record in staged.items:
        info = zipfile.ZipInfo(
            record.archive_path, date_time=datetime.now(timezone.utc).timetuple()[:6]
        )
        info.compress_type = _compression_for(record.path)
        info.external_attr = 0o644 << 16
        with open(local, "rb") as src, zf.open(
            info, "w", force_zip64=record.size_bytes >= (1 << 31)
        ) as dst:
            while chunk := src.read(1024 * 1024):
                tracker.check_cancelled()
                dst.write(chunk)
        records.append(record)
    staged.discard()
    return records


class _Progress:
    def __init__(self) -> None:
        self.done = 0
        self.total = 0

    def grow(self, n: int) -> None:
        self.total += n
        tracker.set_service_total(PROMETHEUS_SERVICE_ID, -(-self.total // _MB), unit="MB")
        self.set(self.done)

    def add(self, n: int) -> None:
        self.set(self.done + n)

    def set(self, value: int) -> None:
        self.done = value
        tracker.set_service_completed(PROMETHEUS_SERVICE_ID, value // _MB)

    def current(self, text: str) -> None:
        tracker.set_service_current(PROMETHEUS_SERVICE_ID, text)


def _record_error(manifest, summary, session, unit: str, files, error: Exception) -> None:
    """A unit (block or head) could not be copied: none of its files are packaged."""
    message = f"{unit}: {error}"
    for f in files:
        summary.collected.append(
            CollectedTsdbFile(
                path=f.path, size_bytes=f.size_bytes, status="error", error=message
            )
        )
    _add_error(manifest, session.pod_name or "", unit, message)
    tracker.record_error(PROMETHEUS_SERVICE_ID, message)


def collect_prometheus_into(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    params: PrometheusParams,
    config: Optional[PrometheusConfig] = None,
    session_factory: SessionFactory = PrometheusSession,
) -> None:
    """Collect the blocks in the requested window into `zf`.

    Never raises for collection problems: a failed Job or file is recorded in
    the manifest (and prometheus.json) so the rest of the package survives.
    """
    config = config or get_prometheus_config()
    tracker.set_service_total(PROMETHEUS_SERVICE_ID, 0, unit="MB")
    tracker.set_service_current(PROMETHEUS_SERVICE_ID, "Starting collector pod")

    summary = PrometheusCollectionSummary(host_dir=config.host_dir, filters=params)
    written: List[str] = []
    service_error: Optional[str] = None
    workdir = tempfile.mkdtemp(prefix="prometheus-", dir=work_dir())

    try:
        with session_factory(core, batch, config) as session:
            summary.node = session.node_name
            tracker.set_service_current(PROMETHEUS_SERVICE_ID, "Listing TSDB blocks")
            data_dirs = session.list_data_dirs()
            summary.available_bytes = _total_bytes(data_dirs)
            if not data_dirs:
                raise PrometheusCollectionError(
                    f"No Prometheus data found under {config.host_dir} on the node "
                    "(set PROMETHEUS_HOST_DIR to the Prometheus data directory)."
                )

            progress = _Progress()
            copied: List[TsdbBlock] = []
            copied_sources: set = set()
            failed: set = set()
            head_done: Optional[TsdbHead] = None

            def copy_block(block: TsdbBlock) -> None:
                try:
                    staged = _stage_unit(session, block.files, True, workdir, progress)
                except PrometheusCollectionError as e:
                    # A block deleted mid-copy was compacted into a new one, which
                    # the re-listing below picks up; anything else is an error.
                    failed.add(block.ulid)
                    if not _vanished(e):
                        _record_error(
                            manifest, summary, session,
                            f"{block.data_dir}/{block.ulid}", block.files, e,
                        )
                    return
                records = _zip_staged(zf, staged)
                summary.collected.extend(records)
                written.extend(r.archive_path for r in records)
                copied.append(block)
                copied_sources.update(block.sources)

            # 1. Persisted blocks: immutable, the bulk of the data.
            blocks, _ = select(data_dirs, params)
            progress.grow(sum(b.size_bytes for b in blocks))
            for block in blocks:
                tracker.check_cancelled()
                copy_block(block)

            # 2. Re-list, pick up blocks created meanwhile (head compaction, or
            #    merges of blocks we couldn't finish), then copy the head last
            #    so it lines up with the newest block. Head files vanish when
            #    Prometheus truncates the WAL, so retry the whole head if so.
            for _ in range(_ATTEMPTS):
                tracker.set_service_current(PROMETHEUS_SERVICE_ID, "Re-listing TSDB")
                data_dirs = session.list_data_dirs()
                new_blocks, heads = select(data_dirs, params)
                new_blocks = [
                    b
                    for b in new_blocks
                    if b.ulid not in failed
                    and b.ulid not in {c.ulid for c in copied}
                    and not set(b.sources) <= copied_sources
                ]
                progress.grow(sum(b.size_bytes for b in new_blocks))
                for block in new_blocks:
                    tracker.check_cancelled()
                    copy_block(block)
                if not heads:
                    break
                head = heads[0]
                done_before, total_before = progress.done, progress.total
                progress.grow(head.size_bytes)
                try:
                    staged = _stage_unit(session, head.files, False, workdir, progress)
                except PrometheusCollectionError as e:
                    if _vanished(e):
                        progress.total = total_before
                        progress.set(done_before)
                        continue
                    _record_error(
                        manifest, summary, session, f"{head.data_dir} (head)", head.files, e
                    )
                    break
                records = _zip_staged(zf, staged)
                summary.collected.extend(records)
                written.extend(r.archive_path for r in records)
                head_done = head
                break
            else:
                raise PrometheusCollectionError(
                    "The Prometheus WAL kept changing while it was copied; try again."
                )

            copied.sort(key=lambda b: b.min_time)
            summary.covered_from, summary.covered_until = coverage(
                copied, [head_done] if head_done else []
            )
            summary.selected_bytes = sum(r.size_bytes for r in summary.collected)
            summary.data_dirs = [
                TsdbDataDir(
                    path=d.path,
                    blocks=[b for b in copied if b.data_dir == d.path],
                    head=head_done if head_done and head_done.data_dir == d.path else None,
                )
                for d in data_dirs
            ]
    except PrometheusCollectionError as e:
        service_error = str(e)
    except Exception as e:  # don't let an unexpected failure sink other services
        service_error = f"Prometheus collection failed: {e}"
    finally:
        try:
            os.rmdir(workdir)
        except OSError:
            pass

    zf.writestr(SUMMARY_PATH, summary.model_dump_json(indent=2))
    files_out = [*written, SUMMARY_PATH]
    manifest.collected_files.extend(files_out)

    if service_error:
        tracker.fail_service(PROMETHEUS_SERVICE_ID, service_error)
        _add_error(manifest, "(collector)", "(all)", service_error)
        manifest.services.append(
            CollectedService(
                id=PROMETHEUS_SERVICE_ID,
                label=PROMETHEUS_LABEL,
                status="error",
                files=files_out,
                error=service_error,
            )
        )
        return

    failed = sum(1 for r in summary.collected if r.status == "error")
    manifest.services.append(
        CollectedService(
            id=PROMETHEUS_SERVICE_ID,
            label=PROMETHEUS_LABEL,
            status="done",
            files=files_out,
            error=f"{failed} TSDB file(s) could not be collected (see manifest errors)."
            if failed
            else None,
        )
    )

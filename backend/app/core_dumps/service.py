"""List core dumps on the node and package them into the diagnostic zip."""

from __future__ import annotations

import os
import tempfile
import zipfile
from typing import Callable, List, Optional

from kubernetes import client

from app.log_collection.progress import (
    CORE_DUMPS_LABEL,
    CORE_DUMPS_SERVICE_ID,
    tracker,
)
from app.log_collection.schemas import (
    CollectedService,
    LogCollectionManifest,
    LogErrorEntry,
)

from .collector import CollectorSession, CoreDumpCollectionError
from .config import CoreDumpConfig, get_core_dump_config
from .parsing import archive_name, select_files
from .schemas import (
    CollectedCoreDump,
    CoreDumpCollectionSummary,
    CoreDumpFile,
    CoreDumpListResponse,
    CoreDumpParams,
    HostCoreConfig,
)

SUMMARY_PATH = "core-dumps/core_dumps.json"
_MB = 1024 * 1024

SessionFactory = Callable[..., CollectorSession]


def list_core_dumps(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    config: Optional[CoreDumpConfig] = None,
    session_factory: SessionFactory = CollectorSession,
) -> CoreDumpListResponse:
    """What's on the node right now (newest first), plus the host core config."""
    config = config or get_core_dump_config()
    with session_factory(core, batch, config) as session:
        files, host_config = session.list_files()
        return CoreDumpListResponse(
            files=files,
            total_bytes=sum(f.size_bytes for f in files),
            host_config=host_config,
            host_dir=config.host_dir,
            collector_pod=session.pod_name,
            node=session.node_name,
        )


def _compression_for(path: str) -> int:
    # Cores are already gzipped by the platform; don't burn CPU re-deflating.
    return zipfile.ZIP_STORED if path.endswith(".gz") else zipfile.ZIP_DEFLATED


def _zip_date(f: CoreDumpFile):
    t = f.mtime_utc
    return (max(t.year, 1980), t.month, t.day, t.hour, t.minute, t.second)


def _add_error(manifest: LogCollectionManifest, pod: str, path: str, reason: str) -> None:
    manifest.errors.append(
        LogErrorEntry(
            namespace="(node)",
            pod=pod,
            container=path,
            reason=reason,
            service=CORE_DUMPS_SERVICE_ID,
        )
    )


def _fetch_one(
    session: CollectorSession,
    f: CoreDumpFile,
    zf: zipfile.ZipFile,
    workdir: str,
    on_bytes: Callable[[int], None],
) -> CollectedCoreDump:
    """Stream one core to a temp file, verify sha256 against the node, zip it."""
    expected = session.remote_sha256(f.path)
    fd, local = tempfile.mkstemp(dir=workdir, prefix="core-")
    try:
        with os.fdopen(fd, "wb") as out:
            digest, size = session.fetch(f.path, out, on_bytes=on_bytes)
        if digest != expected:
            raise CoreDumpCollectionError(
                f"Checksum mismatch for {f.path} (file changed during transfer?)"
            )
        arcname = archive_name(f.path)
        info = zipfile.ZipInfo(arcname, date_time=_zip_date(f))
        info.compress_type = _compression_for(f.path)
        with open(local, "rb") as src, zf.open(
            info, "w", force_zip64=size >= (1 << 31)
        ) as dst:
            while chunk := src.read(1024 * 1024):
                tracker.check_cancelled()
                dst.write(chunk)
        return CollectedCoreDump(
            file=f, archive_path=arcname, sha256=digest, status="collected"
        )
    finally:
        try:
            os.unlink(local)
        except OSError:
            pass


def collect_core_dumps_into(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    params: CoreDumpParams,
    config: Optional[CoreDumpConfig] = None,
    session_factory: SessionFactory = CollectorSession,
) -> None:
    """Collect the selected cores into `zf` and record the result in `manifest`.

    Never raises for collection problems: a failed Job or file is recorded in
    the manifest (and core_dumps.json) so the rest of the package survives.
    """
    config = config or get_core_dump_config()
    tracker.set_service_total(CORE_DUMPS_SERVICE_ID, 0, unit="MB")
    tracker.set_service_current(CORE_DUMPS_SERVICE_ID, "Starting collector pod")

    summary = CoreDumpCollectionSummary(
        host_dir=config.host_dir,
        filters=params,
        host_config=HostCoreConfig(),
        available_count=0,
        available_bytes=0,
    )
    written: List[str] = []
    service_error: Optional[str] = None
    workdir = tempfile.mkdtemp(prefix="core-dumps-")

    try:
        with session_factory(core, batch, config) as session:
            summary.node = session.node_name
            tracker.set_service_current(CORE_DUMPS_SERVICE_ID, "Listing core files")
            files, summary.host_config = session.list_files()
            summary.available_count = len(files)
            summary.available_bytes = sum(f.size_bytes for f in files)
            selected = select_files(files, params)

            total_bytes = sum(f.size_bytes for f in selected)
            tracker.set_service_total(
                CORE_DUMPS_SERVICE_ID, -(-total_bytes // _MB), unit="MB"
            )
            done_bytes = 0

            def on_bytes(n: int) -> None:
                nonlocal done_bytes
                done_bytes += n
                tracker.set_service_completed(CORE_DUMPS_SERVICE_ID, done_bytes // _MB)

            for f in selected:
                start = done_bytes
                tracker.set_service_current(CORE_DUMPS_SERVICE_ID, f.path)
                try:
                    record = _fetch_one(session, f, zf, workdir, on_bytes)
                    written.append(record.archive_path)
                except CoreDumpCollectionError as e:
                    record = CollectedCoreDump(file=f, status="error", error=str(e))
                    _add_error(manifest, session.pod_name or "", f.path, str(e))
                    tracker.record_error(CORE_DUMPS_SERVICE_ID, str(e))
                # Keep the bar honest whether the file made it or not.
                done_bytes = start + f.size_bytes
                tracker.set_service_completed(CORE_DUMPS_SERVICE_ID, done_bytes // _MB)
                summary.collected.append(record)
    except CoreDumpCollectionError as e:
        service_error = str(e)
    except Exception as e:  # don't let an unexpected failure sink other services
        service_error = f"Core dump collection failed: {e}"
    finally:
        try:
            os.rmdir(workdir)
        except OSError:
            pass

    zf.writestr(SUMMARY_PATH, summary.model_dump_json(indent=2))
    files_out = [*written, SUMMARY_PATH]
    manifest.collected_files.extend(files_out)

    if service_error:
        tracker.fail_service(CORE_DUMPS_SERVICE_ID, service_error)
        _add_error(manifest, "(collector)", "(all)", service_error)
        manifest.services.append(
            CollectedService(
                id=CORE_DUMPS_SERVICE_ID,
                label=CORE_DUMPS_LABEL,
                status="error",
                files=files_out,
                error=service_error,
            )
        )
        return

    failed = sum(1 for r in summary.collected if r.status == "error")
    manifest.services.append(
        CollectedService(
            id=CORE_DUMPS_SERVICE_ID,
            label=CORE_DUMPS_LABEL,
            status="done",
            files=files_out,
            error=f"{failed} core file(s) could not be collected." if failed else None,
        )
    )

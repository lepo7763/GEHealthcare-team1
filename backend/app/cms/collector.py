
"""Add CMS snapshots to the combined diagnostic ZIP."""

import gzip
import tempfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath

from app.cms.service import collect_snapshot
from app.log_collection.progress import CMS_LABEL, CMS_SERVICE_ID, tracker
from app.log_collection.schemas import (
    CollectedService,
    LogCollectionManifest,
    LogErrorEntry,
)

MAX_CMS_FILE_BYTES = 512 * 1024 * 1024
MAX_CMS_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
MAX_CMS_FILES = 2000

def prepare_cms_logs(snapshot_path: Path, staging_dir: Path):
    """Safely decompress CMS logs into a temporary directory."""

    files = []
    seen = set()
    total_bytes = 0

    with zipfile.ZipFile(snapshot_path, "r") as snapshot:
        for entry in snapshot.infolist():
            if entry.is_dir():
                continue

            name = entry.filename
            parts = name.split("/")

            # Reject unsafe paths from the downloaded archive.
            if (
                name.startswith("/")
                or "\\" in name
                or ":" in parts[0]
                or any(part in ("", ".", "..") for part in parts)
            ):
                raise ValueError(f"Unsafe CMS archive path: {name}")

            relative = PurePosixPath(name)

            # Remove gzip compression from log files.
            if name.endswith(".gz"):
                relative = PurePosixPath(str(relative)[:-3])

            archive_name = f"cms/logs/{relative.as_posix()}"

            if archive_name in seen:
                raise ValueError(f"Duplicate CMS log: {archive_name}")

            seen.add(archive_name)

            if len(seen) > MAX_CMS_FILES:
                raise ValueError("CMS snapshot contains too many files")

            output = staging_dir.joinpath(*relative.parts)
            output.parent.mkdir(parents=True, exist_ok=True)

            file_bytes = 0

            with snapshot.open(entry) as source:
                if name.endswith(".gz"):
                    stream = gzip.GzipFile(fileobj=source, mode="rb")
                else:
                    stream = source

                try:
                    with output.open("wb") as destination:
                        while True:
                            chunk = stream.read(1024 * 1024)

                            if not chunk:
                                break

                            file_bytes += len(chunk)
                            total_bytes += len(chunk)

                            if file_bytes > MAX_CMS_FILE_BYTES:
                                raise ValueError("CMS log exceeds file size limit")

                            if total_bytes > MAX_CMS_TOTAL_BYTES:
                                raise ValueError("CMS logs exceed total size limit")

                            destination.write(chunk)
                finally:
                    if stream is not source:
                        stream.close()

            files.append((output, archive_name))

    if not files:
        raise ValueError("CMS snapshot contains no files")

    return files

def collect_cms_into(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    start_datetime: str,
    end_datetime: str,
) -> None:
    """Collect a CMS snapshot and add it to the diagnostic package."""

    tracker.set_service_total(CMS_SERVICE_ID, 1, unit="snapshots")
    tracker.set_service_current(CMS_SERVICE_ID, "Generating CMS snapshot")

    collected_files = []
    cleanup_warnings = []

    try:
        # Create a temporary directory for the downloaded CMS ZIP
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "snapshot.zip"

            # Generate, poll, download, verify, and clean up CMS
            collect_snapshot(
                start_datetime,
                end_datetime,
                destination,
                on_cleanup_warning=cleanup_warnings.append,
            )

            # Decompress the snapshot logs before adding them to the package.
            staging_dir = Path(temp_dir) / "cms-logs"

            prepared_files = prepare_cms_logs(
                destination,
                staging_dir,
            )

            for file_path, archive_name in prepared_files:
                zf.write(
                    file_path,
                    arcname=archive_name,
                    compress_type=zipfile.ZIP_DEFLATED,
                )

                collected_files.append(archive_name)

    except Exception as exc:
        message = f"CMS collection failed: {exc}"

        if cleanup_warnings:
            message += " | " + "; ".join(cleanup_warnings)

        tracker.fail_service(CMS_SERVICE_ID, message)

        manifest.errors.append(
            LogErrorEntry(
                namespace="compute",
                pod="(cms service)",
                container="(api)",
                reason=message,
                service=CMS_SERVICE_ID,
            )
        )

        manifest.services.append(
            CollectedService(
                id=CMS_SERVICE_ID,
                label=CMS_LABEL,
                status="error",
                error=message,
            )
        )
        return

    for warning in cleanup_warnings:
        manifest.errors.append(
            LogErrorEntry(
                namespace="compute",
                pod="(cms service)",
                container="(api)",
                reason=warning,
                service=CMS_SERVICE_ID,
            )
        )
        tracker.record_error(CMS_SERVICE_ID, warning)

    manifest.collected_files.extend(collected_files)

    manifest.services.append(
        CollectedService(
            id=CMS_SERVICE_ID,
            label=CMS_LABEL,
            status="done",
            files=collected_files,
            error="; ".join(cleanup_warnings) if cleanup_warnings else None,
        )
    )

    tracker.set_service_completed(CMS_SERVICE_ID, 1)

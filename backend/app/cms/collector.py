
"""Add CMS snapshots to the combined diagnostic ZIP."""

import tempfile
import zipfile
from pathlib import Path

from app.cms.service import collect_snapshot
from app.log_collection.progress import CMS_LABEL, CMS_SERVICE_ID, tracker
from app.log_collection.schemas import (
    CollectedService,
    LogCollectionManifest,
    LogErrorEntry,
)


def collect_cms_into(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    start_datetime: str,
    end_datetime: str,
) -> None:
    """Collect a CMS snapshot and add it to the diagnostic package."""

    tracker.set_service_total(CMS_SERVICE_ID, 1, unit="snapshots")
    tracker.set_service_current(CMS_SERVICE_ID, "Generating CMS snapshot")

    archive_path = "cms/snapshot.zip"
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

            # Add the original CMS ZIP to the combined diagnostic ZIP
            zf.write(
                destination,
                arcname=archive_path,
                compress_type=zipfile.ZIP_STORED,
            )

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

    manifest.collected_files.append(archive_path)

    manifest.services.append(
        CollectedService(
            id=CMS_SERVICE_ID,
            label=CMS_LABEL,
            status="done",
            files=[archive_path],
            error="; ".join(cleanup_warnings) if cleanup_warnings else None,
        )
    )

    tracker.set_service_completed(CMS_SERVICE_ID, 1)

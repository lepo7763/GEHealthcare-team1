
import json
import os
import tempfile
import zipfile
from pathlib import Path


def create_capture_archive(
    capture_dir: str,
    archive_path: str,
) -> str:
    """Package a Job's captured PCAPs, logs, and manifest."""

    directory = Path(capture_dir)
    manifest_path = directory / "manifest.json"

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    files = {"manifest.json"}

    for capture in manifest["captures"]:
        # Preserve diagnostic logs.
        files.add(capture["log_file"])

        # Include valid PCAPs, including empty captures.
        if capture["include_in_zip"]:
            files.add(capture["pcap_file"])

    # Reject unexpected paths outside the capture directory.
    for filename in files:
        if (
            not isinstance(filename, str)
            or not filename
            or filename in (".", "..")
            or "/" in filename
            or "\\" in filename
        ):
            raise ValueError(f"Unsafe archive filename: {filename!r}")

        path = directory / filename

        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(
                f"Required capture artifact missing or unsafe: {filename}"
            )

    destination = Path(archive_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Build in a temporary file to avoid exposing partial ZIPs.
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        suffix=".partial",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with zipfile.ZipFile(
            temporary_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            allowZip64=True,
        ) as archive:
            for filename in sorted(files):
                archive.write(
                    directory / filename,
                    arcname=filename,
                )

        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    return str(destination)

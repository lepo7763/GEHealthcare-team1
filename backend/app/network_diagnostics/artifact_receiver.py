
import hashlib
import os
import re
import secrets
import tempfile
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from app.network_diagnostics.artifact_upload import calculate_sha256


artifact_router = APIRouter()
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


@artifact_router.post(
    "/api/network/sessions/{session_id}/jobs/{job_name}/artifacts"
)
async def receive_capture_archive(
    session_id: str,
    job_name: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_archive_sha256: str | None = Header(default=None),
):
    """Receive, verify, and store one Job's ZIP archive."""

    token = os.environ.get("IOMT_ARTIFACT_UPLOAD_TOKEN")
    storage_root = os.environ.get("IOMT_ARTIFACT_STORAGE_DIR")

    if not token or not storage_root:
        raise HTTPException(503, "Artifact storage is not configured")

    if not authorization or not secrets.compare_digest(
        authorization, f"Bearer {token}"
    ):
        raise HTTPException(401, "Unauthorized artifact upload")

    for identifier in (session_id, job_name):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", identifier):
            raise HTTPException(422, "Invalid session or Job identifier")

    if not x_archive_sha256 or not re.fullmatch(
        r"[0-9a-f]{64}", x_archive_sha256
    ):
        raise HTTPException(422, "Invalid SHA-256 checksum")

    directory = Path(storage_root) / session_id
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    destination = directory / f"{job_name}.zip"

    # Temporary file and final destination use the same filesystem.
    with tempfile.NamedTemporaryFile(
        dir=directory, prefix=".upload-", delete=False
    ) as temp:
        temporary_path = Path(temp.name)

    digest = hashlib.sha256()
    size = 0

    try:
        with temporary_path.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)

                if size > MAX_ARCHIVE_BYTES:
                    raise HTTPException(413, "Archive exceeds size limit")

                digest.update(chunk)
                output.write(chunk)

            output.flush()
            os.fsync(output.fileno())

        actual_hash = digest.hexdigest()

        if size == 0 or actual_hash != x_archive_sha256:
            raise HTTPException(422, "Archive checksum mismatch")

        # Atomically create the stored file without overwriting
        # a previous upload for this Job.
        try:
            os.link(temporary_path, destination)
            duplicate = False

        except FileExistsError:
            existing_hash = calculate_sha256(destination)

            if existing_hash != actual_hash:
                raise HTTPException(
                    409, "Job archive already exists with different contents"
                )

            duplicate = True

        return {
            "stored": True,
            "sha256": actual_hash,
            "duplicate": duplicate,
            "session_id": session_id,
            "job_name": job_name,
        }

    finally:
        temporary_path.unlink(missing_ok=True)

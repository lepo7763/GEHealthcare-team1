
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def calculate_sha256(path: Path) -> str:
    """Calculate a file checksum without loading it all into memory."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def upload_capture_archive(
    archive_path: str,
    upload_url: str,
    token: str,
    max_attempts: int = 3,
    opener=urllib.request.urlopen,
    sleeper=time.sleep,
) -> dict:
    """Upload a ZIP and require backend storage confirmation."""

    archive = Path(archive_path)

    if not archive.is_file():
        raise FileNotFoundError(archive)

    if not archive.stat().st_size:
        raise ValueError("Archive is empty")

    if not upload_url.startswith(("http://", "https://")):
        raise ValueError("A valid HTTP(S) upload URL is required")

    if not token:
        raise ValueError("Upload authentication token is required")

    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be positive")

    expected_hash = calculate_sha256(archive)

    for attempt in range(1, max_attempts + 1):
        try:
            with archive.open("rb") as file:
                request = urllib.request.Request(
                    upload_url,
                    data=file,
                    headers={
                        "Content-Type": "application/zip",
                        "Content-Length": str(archive.stat().st_size),
                        "X-Archive-SHA256": expected_hash,
                        "Authorization": f"Bearer {token}",
                    },
                    method="POST",
                )

                with opener(request, timeout=30) as response:
                    acknowledgement = json.load(response)

        except urllib.error.HTTPError as exc:
            # Retry transient server errors, not authorization failures.
            if exc.code not in (408, 429) and exc.code < 500:
                raise

            if attempt == max_attempts:
                raise RuntimeError("Archive upload failed") from exc

        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == max_attempts:
                raise RuntimeError("Archive upload failed") from exc

        else:
            if (
                acknowledgement.get("stored") is not True
                or acknowledgement.get("sha256") != expected_hash
            ):
                raise ValueError("Backend did not confirm archive integrity")

            return acknowledgement

        sleeper(2 ** (attempt - 1))

    raise RuntimeError("Archive upload was not confirmed")

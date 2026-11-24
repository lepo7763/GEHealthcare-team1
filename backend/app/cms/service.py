import time
import json
import os
import shutil
import re
import zipfile
import logging

from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from typing import Callable


DEFAULT_CMS_URL = (
    "http://axone-compute-management.compute.svc.cluster.local"
)


def get_cms_url():
    return os.getenv("CMS_API_URL", DEFAULT_CMS_URL).rstrip("/")


#performs equivalent of "curl "http://100.64.41.21/cms/sprsnap/list""
def list_snapshots():
    url = f"{get_cms_url()}/cms/sprsnap/list"

    request = Request(url, method="GET")

    with urlopen(request, timeout=15) as response:
        data = response.read()
        return json.loads(data) if data.strip() else []

def generate_snapshot(start_datetime: str, end_datetime: str) -> str:
    url = f"{get_cms_url()}/cms/sprsnap/generate"

    payload = {
        "startdatetime": start_datetime,
        "enddatetime": end_datetime,
    }

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")

def download_snapshot(filename: str, destination: Path) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.zip", filename):
        raise ValueError("Invalid CMS snapshot filename")

    url = f"{get_cms_url()}/cms/sprsnap/download/{quote(filename, safe='')}"

    request = Request(url, method="GET")
    destination = Path(destination)

    try:
        with urlopen(request, timeout=300) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return destination

def delete_snapshot(filename: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.zip", filename):
        raise ValueError("Invalid CMS snapshot filename")

    url = f"{get_cms_url()}/cms/sprsnap/delete/{quote(filename, safe='')}"

    request = Request(url, method="DELETE")

    with urlopen(request, timeout=30) as response:
        if response.status != 204:
            raise RuntimeError(
                f"Unexpected CMS deletion status: {response.status}"
            )

def wait_for_snapshot(
    filename: str,
    timeout_seconds: int = 180,
    poll_interval: int = 3,
) -> None:

    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:

        snapshots = list_snapshots()

        if filename in snapshots:
            return

        time.sleep(poll_interval)

    raise TimeoutError(
        f"CMS snapshot {filename} was not available "
        f"after {timeout_seconds} seconds"
    )

def collect_snapshot(
    start_datetime: str,
    end_datetime: str,
    destination: Path,
    on_cleanup_warning: Callable[[str], None] | None = None,
) -> Path:

    # 1. Request a new snapshot from CMS
    response = generate_snapshot(start_datetime, end_datetime)

    # 2. Extract the filename from the API response
    prefix = "Sprsnap generation request submitted successfully:"

    if not response.startswith(prefix):
        raise RuntimeError(f"Unexpected CMS response: {response}")

    filename = response[len(prefix):].strip()

    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.zip", filename):
        raise ValueError("Invalid snapshot filename returned by CMS")

    destination = Path(destination)

    def cleanup_server_snapshot(preserve_original_error=False):
        try:
            delete_snapshot(filename)
        except Exception as exc:
            logging.exception(
                "Failed to delete CMS snapshot: %s", filename
            )

            warning = (
                f"CMS cleanup failed for {filename}. "
                f"The server-side snapshot may still exist: {exc}"
            )

            if on_cleanup_warning is not None:
                try:
                    on_cleanup_warning(warning)
                except Exception:
                    logging.exception("Could not record CMS cleanup warning")
            elif not preserve_original_error:
                raise

    try:
        # Wait for CMS to finish generating the snapshot
        wait_for_snapshot(filename)

        # Download the snapshot
        download_snapshot(filename, destination)

        # Verify the downloaded ZIP
        with zipfile.ZipFile(destination, "r") as archive:
            bad_file = archive.testzip()

            if bad_file is not None:
                raise RuntimeError(
                    f"Corrupted file inside CMS snapshot: {bad_file}"
                )

    except Exception:
        # Remove any incomplete local download
        destination.unlink(missing_ok=True)

        # Attempt server-side cleanup without hiding the original error
        cleanup_server_snapshot(preserve_original_error=True)
        raise

    else:
        # Collection succeeded, so delete the server-side copy
        cleanup_server_snapshot()
        return destination

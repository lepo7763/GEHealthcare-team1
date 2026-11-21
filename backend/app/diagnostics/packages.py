"""The most recent diagnostic package, kept on disk so the browser can download
it straight to the user's disk.

A package is stored as ``<work dir>/packages/<id>__<download filename>``, so the
file itself is the record and survives a backend restart. Only the latest
package is kept: registering a new one deletes the rest. The tool serves one
workstation and one collection at a time.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from app.core.workdir import work_dir

_SUBDIR = "packages"
_SEP = "__"
_ID = re.compile(r"^[0-9a-f]{32}$")
_lock = Lock()


@dataclass(frozen=True)
class Package:
    id: str
    path: str
    filename: str
    size_bytes: int


def new_package_file():
    """An open, named file on disk for the orchestrator to write the zip into."""
    return tempfile.NamedTemporaryFile(
        dir=work_dir(_SUBDIR), prefix="building-", suffix=".zip", delete=False
    )


def discard(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def register(path: str, filename: str) -> Package:
    """Make the finished zip at `path` the current package; delete every older one."""
    package_id = uuid.uuid4().hex
    directory = work_dir(_SUBDIR)
    final = os.path.join(directory, f"{package_id}{_SEP}{os.path.basename(filename)}")
    with _lock:
        os.replace(path, final)
        for name in os.listdir(directory):
            other = os.path.join(directory, name)
            if other != final:
                discard(other)
    return Package(
        id=package_id, path=final, filename=filename, size_bytes=os.path.getsize(final)
    )


def get(package_id: str) -> Optional[Package]:
    if not _ID.match(package_id):
        return None
    directory = work_dir(_SUBDIR)
    with _lock:
        for name in os.listdir(directory):
            found_id, sep, filename = name.partition(_SEP)
            if sep and found_id == package_id:
                path = os.path.join(directory, name)
                return Package(
                    id=package_id,
                    path=path,
                    filename=filename,
                    size_bytes=os.path.getsize(path),
                )
    return None

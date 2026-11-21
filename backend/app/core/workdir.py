"""On-disk scratch space for packages and transfers.

Packages (a Prometheus export alone can be tens of GB) are built on real disk,
not in /tmp, which is often a small RAM-backed tmpfs.
"""

import os
from pathlib import Path


def work_dir(*parts: str) -> str:
    """$IOMT_WORK_DIR (default ~/.cache/iomt-analysis-tool)/<parts>, created on demand."""
    base = os.environ.get("IOMT_WORK_DIR") or os.path.join(
        Path.home(), ".cache", "iomt-analysis-tool"
    )
    path = os.path.join(base, *parts)
    os.makedirs(path, exist_ok=True)
    return path

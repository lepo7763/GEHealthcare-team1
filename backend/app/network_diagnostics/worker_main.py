import os
import sys

from app.network_diagnostics.capture_worker import run_capture_session
from app.network_diagnostics.artifact_packaging import create_capture_archive
from pathlib import Path
from time import sleep


def main() -> int:
    """Start a capture session using the Job's environment variables."""

    try:
        raw_targets = os.environ.get("CAPTURE_TARGETS_JSON")

        if raw_targets is None:
            raise ValueError("CAPTURE_TARGETS_JSON is required")

        duration = int(os.environ.get("CAPTURE_DURATION_SECONDS", "60"))
        output_dir = os.environ.get("CAPTURE_OUTPUT_DIR", "/captures")

        collect_grace_seconds = int(os.environ.get("CAPTURE_COLLECT_GRACE_SECONDS", "120"))

        if not 1 <= collect_grace_seconds <= 180:
            raise ValueError("Collection grace period must be 1-180 seconds")

        manifest = run_capture_session(
            raw_targets=raw_targets,
            duration_seconds=duration,
            output_dir=output_dir,
        )

    except ValueError as exc:
        print(f"Invalid capture configuration: {exc}", file=sys.stderr)
        return 2

    #package the completed session files
    archive_path = str(Path(output_dir) / "job-artifacts.zip")

    try:
        create_capture_archive(
            capture_dir = output_dir,
            archive_path = archive_path,
        )

        #signal that the archive is ready for retrieval
        done_path = Path(output_dir) / ".done"
        done_path.touch()

    except(OSError, ValueError, KeyError) as exc:
        print(f"Artifact packaging failed: {exc}", file = sys.stderr)
        return 1

    print(f"Capture archive created: {archive_path}")
    
    print(
        f"Capture session finished: "
        f"{len(manifest['captures'])} captures, "
        f"{len(manifest['unavailable'])} unavailable targets"
    )

    print(f"Waiting {collect_grace_seconds} seconds for artifact retrieval")
    sleep(collect_grace_seconds)

    return 0


if __name__ == "__main__":
    sys.exit(main())


import os
import sys

from app.network_diagnostics.capture_worker import run_capture_session


def main() -> int:
    """Start a capture session using the Job's environment variables."""

    try:
        raw_targets = os.environ.get("CAPTURE_TARGETS_JSON")

        if raw_targets is None:
            raise ValueError("CAPTURE_TARGETS_JSON is required")

        duration = int(os.environ.get("CAPTURE_DURATION_SECONDS", "60"))
        output_dir = os.environ.get("CAPTURE_OUTPUT_DIR", "/captures")

        manifest = run_capture_session(
            raw_targets=raw_targets,
            duration_seconds=duration,
            output_dir=output_dir,
        )

    except ValueError as exc:
        print(f"Invalid capture configuration: {exc}", file=sys.stderr)
        return 2

    print(
        f"Capture session finished: "
        f"{len(manifest['captures'])} captures, "
        f"{len(manifest['unavailable'])} unavailable targets"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

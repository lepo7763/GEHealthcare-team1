import json
import subprocess
import os
import signal
import time 
import struct

from collections.abc import Callable
from pathlib import Path
from app.network_diagnostics.runtime_discovery import resolve_pod_pid



def load_capture_targets(raw_json: str) -> list[dict]:
    """Parse and validate the target list supplied by FastAPI."""

    targets = json.loads(raw_json)

    if not isinstance(targets, list):
        raise ValueError("Capture targets must be a list")

    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("Each target must be a dictionary")

        for field in ("name", "namespace", "uid"):
            value = target.get(field)

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Capture target has missing or invalid {field}"
                )

    return targets

def resolve_capture_targets(
    targets: list[dict],
    resolver: Callable[[str, str], int] = resolve_pod_pid,
) -> dict:
    """Resolve target Pods and record unavailable targets."""

    resolved = []
    unavailable = []

    for target in targets:
        try:
            pid = resolver(
                target["uid"],
                target["namespace"],
            )

            resolved.append({
                **target,
                "pid": pid,
            })

        except (ValueError, subprocess.SubprocessError) as exc:
            unavailable.append({
                "name": target["name"],
                "namespace": target["namespace"],
                "uid": target["uid"],
                "reason": str(exc),
            })

    return {
        "resolved": resolved,
        "unavailable": unavailable,
    }

def build_tcpdump_command(pid: int, output_path: str) -> list[str]:
    """Build a tcpdump command for a target Pod's network namespace.
    nsenter -t PID -n -> enter the target process's network namespace
    -- -> separate nsenter options from command to execute
    tcpdump -i any -> capture traffic across all interfaces in that namespace including loopback
    -nn -> disable hostname and port anme resolution
    -s 0 -> capture complete packets rather than truncating them
    -U -> write packets to the pcap as they arrive
    -w output_path -> save binary packets to the specified file
    """

    if type(pid) is not int or pid <= 0:
        raise ValueError("A valid host PID is required")

    if not isinstance(output_path, str) or not output_path:
        raise ValueError("A PCAP output path is required")

    return [
        "nsenter",
        "-t", str(pid),
        "-n",
        "--",
        "tcpdump",
        "-i", "any",
        "-nn",
        "-s", "0",
        "-U",
        "-w", output_path,
    ]


def start_capture_processes(
    targets: list[dict],
    output_dir: str,
    resolver: Callable[[str, str], int] = resolve_pod_pid,
    popen_factory: Callable = subprocess.Popen,
) -> dict:
    """Start concurrent captures, recording individual failures."""

    capture_dir = Path(output_dir)
    capture_dir.mkdir(parents=True, exist_ok=True)

    running = []
    unavailable = []

    for index, target in enumerate(targets, start=1):
        try:
            # Resolve immediately before launching the capture.
            pid = resolver(target["uid"], target["namespace"])

            pcap_path = capture_dir / f"capture-{index}.pcap"
            log_path = capture_dir / f"capture-{index}.log"

            command = build_tcpdump_command(
                pid, str(pcap_path)
            )

            with log_path.open("wb") as log_file:
                process = popen_factory(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=log_file,
                    start_new_session=True,
                )

            running.append({
                "target": target,
                "pcap_path": str(pcap_path),
                "log_path": str(log_path),
                "process": process,
            })

        except (
            ValueError,
            subprocess.SubprocessError,
            OSError,
            KeyError,
        ) as exc:
            unavailable.append({
                "name": target.get("name", "unknown"),
                "uid": target.get("uid", "unknown"),
                "reason": str(exc),
            })

    return {
        "running": running,
        "unavailable": unavailable,
    }


def finish_capture_processes(
    running: list[dict],
    duration_seconds: int,
    grace_seconds: int = 10,
) -> list[dict]:
    """Stop captures after the requested duration and collect exit codes."""

    if type(duration_seconds) is not int or duration_seconds <= 0:
        raise ValueError("Capture duration must be a positive integer")

    if type(grace_seconds) is not int or grace_seconds <= 0:
        raise ValueError("Grace period must be a positive integer")

    if not running:
        return []

    results = []

    try:
        time.sleep(duration_seconds)

    finally:
        # Signal all running captures before waiting for any of them.
        for capture in running:
            process = capture["process"]

            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass

        # Wait for each capture to finish.
        for capture in running:
            process = capture["process"]
            forced = False

            try:
                exit_code = process.wait(timeout=grace_seconds)

            except subprocess.TimeoutExpired:
                forced = True

                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

                try:
                    exit_code = process.wait(timeout=grace_seconds)
                except subprocess.TimeoutExpired:
                    exit_code = None

            results.append({
                "target": capture["target"],
                "pcap_path": capture["pcap_path"],
                "log_path": capture["log_path"],
                "exit_code": exit_code,
                "forced_stop": forced,
            })

    return results


def inspect_pcap_file(path: str) -> dict:
    """Check PCAP structure and count recorded packets."""

    pcap_path = Path(path)

    if not pcap_path.is_file():
        return {"status": "missing", "packet_count": 0}

    file_size = pcap_path.stat().st_size

    if file_size < 24:
        return {"status": "invalid", "packet_count": 0}

    # Classic PCAP supports two byte orders and two timestamp precisions.
    magic_formats = {
        b"\xd4\xc3\xb2\xa1": "<",
        b"\xa1\xb2\xc3\xd4": ">",
        b"\x4d\x3c\xb2\xa1": "<",
        b"\xa1\xb2\x3c\x4d": ">",
    }

    with pcap_path.open("rb") as pcap:
        header = pcap.read(24)
        endian = magic_formats.get(header[:4])

        if endian is None:
            return {"status": "invalid", "packet_count": 0}

        major, minor = struct.unpack(endian + "HH", header[4:8])
        snaplen = struct.unpack(endian + "I", header[16:20])[0]

        if (major, minor) != (2, 4) or snaplen == 0:
            return {"status": "invalid", "packet_count": 0}

        packet_count = 0
        position = 24

        while position < file_size:
            if file_size - position < 16:
                return {"status": "invalid", "packet_count": 0}

            record = pcap.read(16)
            _, _, captured_len, original_len = struct.unpack(
                endian + "IIII", record
            )
            position += 16

            if (
                captured_len > original_len
                or captured_len > snaplen
                or captured_len > file_size - position
            ):
                return {"status": "invalid", "packet_count": 0}

            pcap.seek(captured_len, 1)
            position += captured_len
            packet_count += 1

    return {
        "status": "captured" if packet_count > 0 else "empty",
        "packet_count": packet_count,
    }


def summarize_capture_results(results: list[dict]) -> list[dict]:
    """Combine process outcomes with PCAP inspection results."""

    summaries = []

    for result in results:
        pcap = inspect_pcap_file(result["pcap_path"])

        if result["forced_stop"]:
            process_status = "interrupted"
        elif result["exit_code"] == 0:
            process_status = "completed"
        elif result["exit_code"] is None:
            process_status = "unconfirmed"
        else:
            process_status = "failed"

        summaries.append({
            **result,
            "process_status": process_status,
            "pcap_status": pcap["status"],
            "packet_count": pcap["packet_count"],
            "include_in_zip": pcap["status"] in ("captured", "empty"),
        })

    return summaries


def run_capture_session(
    raw_targets: str,
    duration_seconds: int,
    output_dir: str,
    resolver: Callable[[str, str], int] = resolve_pod_pid,
    popen_factory: Callable = subprocess.Popen,
) -> dict:
    """Run a capture session and write its result manifest."""

    if type(duration_seconds) is not int or duration_seconds <= 0:
        raise ValueError("Capture duration must be a positive integer")

    # Step 1: Parse and validate the requested targets.
    targets = load_capture_targets(raw_targets)

    # Step 2: Resolve PIDs and start concurrent captures.
    launched = start_capture_processes(
        targets,
        output_dir,
        resolver=resolver,
        popen_factory=popen_factory,
    )

    # Step 3: Stop captures after the requested duration.
    finished = finish_capture_processes(
        launched["running"],
        duration_seconds,
    )

    # Step 4: Inspect the resulting PCAP files.
    summaries = summarize_capture_results(finished)

    # Step 5: Build serializable capture metadata.
    captures = []

    for summary in summaries:
        captures.append({
            "target": summary["target"],
            "pcap_file": (
                Path(summary["pcap_path"]).name
                if summary["include_in_zip"] else None
            ),
            "log_file": Path(summary["log_path"]).name,
            "process_status": summary["process_status"],
            "pcap_status": summary["pcap_status"],
            "packet_count": summary["packet_count"],
            "exit_code": summary["exit_code"],
            "forced_stop": summary["forced_stop"],
            "include_in_zip": summary["include_in_zip"],
        })

    manifest = {
        "format_version": 1,
        "requested_duration_seconds": duration_seconds,
        "targets_requested": len(targets),
        "captures": captures,
        "unavailable": launched["unavailable"],
    }

    # Step 6: Save the manifest alongside the PCAP files.
    manifest_path = Path(output_dir) / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    return manifest




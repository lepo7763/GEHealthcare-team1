"""Snapshot the node firewall for the UI and package it into the diagnostic zip."""

from __future__ import annotations

import shlex
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Tuple

from kubernetes import client

from app.log_collection.progress import FIREWALL_LABEL, FIREWALL_SERVICE_ID, tracker
from app.log_collection.schemas import (
    CollectedService,
    LogCollectionManifest,
    LogErrorEntry,
)

from .collector import FirewallCollectionError, FirewallSession
from .config import FirewallConfig, get_firewall_config
from .parsing import (
    INFO_COMMAND,
    INFO_FILE,
    MISSING_EXIT_CODE,
    build_snapshot,
    render_report,
)
from .schemas import FirewallResponse, FirewallSnapshot

REPORT_PATH = "firewall/report.txt"
SUMMARY_PATH = "firewall/summary.json"
CONFIG_PREFIX = "firewall/etc/firewalld/"

SessionFactory = Callable[..., FirewallSession]


@dataclass
class FirewallCapture:
    snapshot: FirewallSnapshot
    outputs: Dict[str, Tuple[str, int]]
    config_files: Dict[str, bytes] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def capture_firewall(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    config: Optional[FirewallConfig] = None,
    session_factory: SessionFactory = FirewallSession,
    include_config_files: bool = True,
    on_step: Callable[[str], None] = lambda _: None,
) -> FirewallCapture:
    """Run the collector once. Raises FirewallCollectionError if nothing ran."""
    config = config or get_firewall_config()
    on_step("Starting collector pod")
    with session_factory(core, batch, config) as session:
        on_step("Reading firewall state")
        outputs = session.run_commands()
        snapshot = build_snapshot(
            outputs, _now(), node=session.node_name, collector_pod=session.pod_name
        )
        files: Dict[str, bytes] = {}
        if include_config_files:
            on_step("Copying /etc/firewalld")
            try:
                files = session.config_files()
            except FirewallCollectionError as e:
                snapshot.errors.append(f"/etc/firewalld not collected: {e}")
        return FirewallCapture(snapshot=snapshot, outputs=outputs, config_files=files)


def get_firewall(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    config: Optional[FirewallConfig] = None,
    session_factory: SessionFactory = FirewallSession,
) -> FirewallResponse:
    capture = capture_firewall(
        core, batch, config, session_factory, include_config_files=False
    )
    return FirewallResponse(
        snapshot=capture.snapshot,
        report=render_report(capture.snapshot),
        outputs={cid: text for cid, (text, _rc) in capture.outputs.items()},
    )


def collect_firewall_into(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    config: Optional[FirewallConfig] = None,
    session_factory: SessionFactory = FirewallSession,
) -> None:
    """Write only firewall/firewall-info.txt
    (`firewall-cmd --zone=external --list-all`) into `zf`.

    Never raises for collection problems; failures go in the manifest.
    """
    steps = 2
    tracker.set_service_total(FIREWALL_SERVICE_ID, steps, unit="steps")
    config = config or get_firewall_config()

    try:
        tracker.set_service_completed(FIREWALL_SERVICE_ID, 0, current="Starting collector pod")
        with session_factory(core, batch, config) as session:
            tracker.set_service_completed(FIREWALL_SERVICE_ID, 1, current="Reading firewall state")
            outputs = session.run_commands((INFO_COMMAND,))
            pod_name = session.pod_name
    except Exception as e:  # FirewallCollectionError or anything unexpected
        message = (
            str(e) if isinstance(e, FirewallCollectionError)
            else f"Firewall collection failed: {e}"
        )
        tracker.fail_service(FIREWALL_SERVICE_ID, message)
        manifest.errors.append(LogErrorEntry(
            namespace="(node)", pod="(collector)", container="(all)",
            reason=message, service=FIREWALL_SERVICE_ID,
        ))
        manifest.services.append(CollectedService(
            id=FIREWALL_SERVICE_ID, label=FIREWALL_LABEL, status="error", error=message,
        ))
        return

    text, rc = outputs.get(INFO_COMMAND.id, ("", None))
    written = []
    errors = []
    if rc is None or rc == MISSING_EXIT_CODE or rc not in INFO_COMMAND.ok_exit_codes:
        detail = text.strip().splitlines()[0] if text.strip() else "no output"
        errors.append(f"{shlex.join(INFO_COMMAND.argv)} failed (exit {rc}): {detail}")
    if text:
        zf.writestr(INFO_FILE, text)
        written.append(INFO_FILE)

    for err in errors:
        manifest.errors.append(LogErrorEntry(
            namespace="(node)", pod=pod_name or "", container="(firewall)",
            reason=err, service=FIREWALL_SERVICE_ID,
        ))
    manifest.collected_files.extend(written)
    manifest.services.append(CollectedService(
        id=FIREWALL_SERVICE_ID,
        label=FIREWALL_LABEL,
        status="done",
        files=written,
        error=f"{len(errors)} firewall command(s) failed." if errors else None,
    ))
    tracker.set_service_completed(FIREWALL_SERVICE_ID, steps)

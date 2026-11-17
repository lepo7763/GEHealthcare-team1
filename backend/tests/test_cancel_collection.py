"""Cancelling a running diagnostic collection.

Cancellation is cooperative: POST /api/logs/cancel sets a flag, collectors
check it at checkpoints, unwind through their cleanup (deleting their Jobs),
and the orchestrator packages whatever already finished.
"""

import hashlib
import io
import json
import zipfile
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from kubernetes import client

from app.core.k8s_client import get_batch_v1_api, get_core_v1_api
from app.core_dumps.parsing import parse_listing
from app.core_dumps.schemas import CoreDumpParams
from app.core_dumps.service import SUMMARY_PATH, collect_core_dumps_into
from app.diagnostics import service as diagnostics_service
from app.diagnostics.service import collect_diagnostics
from app.log_collection.progress import (
    AXONE_LOGS_SERVICE_ID,
    CONTAINER_LOGS_SERVICE_ID,
    CORE_DUMPS_SERVICE_ID,
    FIREWALL_SERVICE_ID,
    UMF_RTI_SERVICE_ID,
    CollectionCancelled,
    ServiceProgress,
    tracker,
)
from app.log_collection.schemas import LogCollectionManifest, LogCollectionParams
from app.main import app
from app.umf_rti.config import UmfRtiConfig
from app.umf_rti.schemas import UmfRtiParams
from app.umf_rti.service import capture_umf_rti

test_client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_tracker():
    tracker.reset()
    yield
    tracker.reset()


def make_pod(name, namespace="default", containers=("app",)):
    return client.V1Pod(
        metadata=client.V1ObjectMeta(namespace=namespace, name=name),
        spec=client.V1PodSpec(containers=[client.V1Container(name=c) for c in containers]),
        status=client.V1PodStatus(container_statuses=[]),
    )


def read_manifest(temp_zip):
    with zipfile.ZipFile(temp_zip) as zf:
        return zf.namelist(), json.loads(zf.read("manifest.json"))


def services_by_id(manifest):
    return {s["id"]: s for s in manifest["services"]}


def tracker_statuses():
    return {s["id"]: s["status"] for s in tracker.snapshot()["services"]}


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


def test_cancel_is_refused_when_nothing_is_running():
    assert tracker.request_cancel() is False
    assert tracker.cancel_requested is False


def test_cancel_request_sets_flag_and_checkpoint_raises():
    tracker.begin([ServiceProgress(id=CONTAINER_LOGS_SERVICE_ID, label="Logs")])
    assert tracker.request_cancel() is True
    assert tracker.snapshot()["cancel_requested"] is True
    assert "Cancelling" in tracker.snapshot()["message"]
    with pytest.raises(CollectionCancelled):
        tracker.raise_if_cancelled()


def test_new_run_clears_a_previous_cancel():
    tracker.begin([ServiceProgress(id=CONTAINER_LOGS_SERVICE_ID, label="Logs")])
    tracker.request_cancel()
    tracker.finish_cancelled()
    assert tracker.try_begin([ServiceProgress(id=CONTAINER_LOGS_SERVICE_ID, label="Logs")])
    assert tracker.cancel_requested is False
    tracker.raise_if_cancelled()  # must not raise


def test_finish_cancelled_keeps_done_and_marks_the_rest():
    tracker.begin(
        [
            ServiceProgress(id="a", label="A"),
            ServiceProgress(id="b", label="B"),
            ServiceProgress(id="c", label="C"),
        ]
    )
    tracker.set_service_total("a", 1)
    tracker.complete_service("a")
    tracker.set_service_total("b", 5)
    tracker.request_cancel()
    tracker.finish_cancelled()

    snap = tracker.snapshot()
    assert snap["status"] == "cancelled"
    assert snap["finished_at"]
    assert tracker_statuses() == {"a": "done", "b": "cancelled", "c": "skipped"}
    assert "1 finished service" in snap["message"]
    assert tracker.running is False


def test_complete_service_does_not_hide_a_failure():
    tracker.begin([ServiceProgress(id="a", label="A")])
    tracker.fail_service("a", "boom")
    tracker.complete_service("a")
    assert tracker_statuses() == {"a": "error"}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def test_cancel_endpoint_returns_409_when_idle():
    response = test_client.post("/api/logs/cancel")
    assert response.status_code == 409
    assert "No diagnostic collection" in response.json()["detail"]


def test_cancel_endpoint_accepts_a_running_collection():
    tracker.begin([ServiceProgress(id=CONTAINER_LOGS_SERVICE_ID, label="Logs")])
    response = test_client.post("/api/logs/cancel")
    assert response.status_code == 202
    assert response.json()["cancel_requested"] is True
    assert test_client.get("/api/logs/progress").json()["cancel_requested"] is True


def test_cancelled_download_is_a_partial_package():
    core = MagicMock(spec=client.CoreV1Api)
    batch = MagicMock(spec=client.BatchV1Api)
    core.list_pod_for_all_namespaces.return_value = client.V1PodList(
        items=[make_pod("p1"), make_pod("p2")]
    )

    def read_log(**kwargs):
        tracker.request_cancel()  # user clicks Cancel while the first log is read
        return "line\n"

    core.read_namespaced_pod_log.side_effect = read_log
    app.dependency_overrides[get_core_v1_api] = lambda: core
    app.dependency_overrides[get_batch_v1_api] = lambda: batch
    try:
        response = test_client.get("/api/logs/zip?throttle_delay_ms=0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "_partial.zip" in response.headers["content-disposition"]
    _, manifest = read_manifest(io.BytesIO(response.content))
    assert manifest["status"] == "cancelled"
    assert test_client.get("/api/logs/progress").json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _run(core, batch, services, **kwargs):
    return collect_diagnostics(
        core=core,
        batch=batch,
        services=services,
        log_params=LogCollectionParams(throttle_delay_ms=0),
        umf_params=UmfRtiParams(),
        **kwargs,
    )


def test_cancel_mid_service_keeps_written_files_and_skips_the_rest():
    core = MagicMock(spec=client.CoreV1Api)
    batch = MagicMock(spec=client.BatchV1Api)
    core.list_pod_for_all_namespaces.return_value = client.V1PodList(
        items=[make_pod("p1"), make_pod("p2"), make_pod("p3")]
    )

    def read_log(**kwargs):
        tracker.request_cancel()
        return "line\n"

    core.read_namespaced_pod_log.side_effect = read_log

    temp_zip = _run(core, batch, [CONTAINER_LOGS_SERVICE_ID, FIREWALL_SERVICE_ID])
    names, manifest = read_manifest(temp_zip)

    # The container being read when Cancel was clicked still finishes; the
    # next checkpoint stops the service.
    assert core.read_namespaced_pod_log.call_count == 1
    assert "logs/default/p1/app.log" in names
    assert "logs/default/p2/app.log" not in names

    assert manifest["status"] == "cancelled"
    services = services_by_id(manifest)
    assert services[CONTAINER_LOGS_SERVICE_ID]["status"] == "cancelled"
    assert services[CONTAINER_LOGS_SERVICE_ID]["files"] == ["logs/default/p1/app.log"]
    assert services[FIREWALL_SERVICE_ID]["status"] == "skipped"

    # The firewall collector never started, so no Job was ever created.
    batch.create_namespaced_job.assert_not_called()
    assert tracker.snapshot()["status"] == "cancelled"
    assert tracker_statuses() == {
        CONTAINER_LOGS_SERVICE_ID: "cancelled",
        FIREWALL_SERVICE_ID: "skipped",
    }


def test_cancel_between_services_keeps_finished_service(monkeypatch):
    def fake_container_logs(zf, manifest, core, params):
        zf.writestr("logs/ns/pod/app.log", "ok\n")
        manifest.collected_files.append("logs/ns/pod/app.log")
        tracker.request_cancel()  # Cancel lands just as this service finishes
        return ["logs/ns/pod/app.log"]

    monkeypatch.setattr(
        diagnostics_service, "collect_container_logs_into", fake_container_logs
    )
    axone = MagicMock()
    monkeypatch.setattr(diagnostics_service, "fetch_axone_csv", axone)

    temp_zip = _run(
        MagicMock(), MagicMock(), [CONTAINER_LOGS_SERVICE_ID, AXONE_LOGS_SERVICE_ID]
    )
    names, manifest = read_manifest(temp_zip)

    assert "logs/ns/pod/app.log" in names
    services = services_by_id(manifest)
    assert services[CONTAINER_LOGS_SERVICE_ID]["status"] == "done"
    assert services[AXONE_LOGS_SERVICE_ID]["status"] == "skipped"
    axone.assert_not_called()
    assert tracker_statuses() == {
        CONTAINER_LOGS_SERVICE_ID: "done",
        AXONE_LOGS_SERVICE_ID: "skipped",
    }


def test_uncancelled_run_still_completes_normally(monkeypatch):
    monkeypatch.setattr(
        diagnostics_service,
        "collect_container_logs_into",
        lambda zf, manifest, core, params: [],
    )
    temp_zip = _run(MagicMock(), MagicMock(), [CONTAINER_LOGS_SERVICE_ID])
    _, manifest = read_manifest(temp_zip)
    assert manifest["status"] == "complete"
    assert tracker.snapshot()["status"] == "done"


# ---------------------------------------------------------------------------
# Collectors clean up their Kubernetes Jobs
# ---------------------------------------------------------------------------


def test_umf_cancel_deletes_the_capture_job():
    tracker.begin([ServiceProgress(id=UMF_RTI_SERVICE_ID, label="UMF RTI")])
    core = MagicMock(spec=client.CoreV1Api)
    batch = MagicMock(spec=client.BatchV1Api)
    batch.create_namespaced_job.return_value = client.V1Job(
        metadata=client.V1ObjectMeta(name="umf-rti-capture-abc")
    )
    core.list_namespaced_pod.return_value = client.V1PodList(items=[])
    tracker.request_cancel()

    with pytest.raises(CollectionCancelled):
        capture_umf_rti(core, batch, UmfRtiParams(), UmfRtiConfig(poll_interval_seconds=0))

    batch.delete_namespaced_job.assert_called_once()
    assert batch.delete_namespaced_job.call_args.kwargs["name"] == "umf-rti-capture-abc"


T0 = 1794521196
CORE_A = "core.a.pid1.sig11.usr0.grp0.time100"
CORE_B = "core.b.pid2.sig6.usr0.grp0.time200"


class FakeCoreSession:
    """Stands in for the core-dump collector session; records that it exited."""

    def __init__(self, contents, cancel_during=None, cancel_after=None):
        self.contents = contents
        self.cancel_during = cancel_during
        self.cancel_after = cancel_after
        self.pod_name = "core-dump-collector-x"
        self.node_name = "node-1"
        self.exited = False

    def __call__(self, core, batch, config):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.exited = True  # the real session deletes its Job here

    def list_files(self):
        lines = [f"F {len(d)} {T0} {p}" for p, d in self.contents.items()]
        return parse_listing("\n".join(lines) + "\nP |handler\nL 1\n")

    def remote_sha256(self, path):
        return hashlib.sha256(self.contents[path]).hexdigest()

    def fetch(self, path, sink, on_bytes=None):
        data = self.contents[path]
        if path == self.cancel_during:
            tracker.request_cancel()
        sink.write(data)
        if on_bytes:
            on_bytes(len(data))
        if path == self.cancel_after:
            tracker.request_cancel()
        return hashlib.sha256(data).hexdigest(), len(data)


def _collect_cores(session):
    tracker.begin([ServiceProgress(id=CORE_DUMPS_SERVICE_ID, label="Core Dumps", unit="MB")])
    buf = io.BytesIO()
    manifest = LogCollectionManifest(timestamp_utc="t", total_logs_collected=0)
    with zipfile.ZipFile(buf, "w") as zf:
        with pytest.raises(CollectionCancelled):
            collect_core_dumps_into(
                zf, manifest, MagicMock(), MagicMock(), CoreDumpParams(),
                session_factory=session,
            )
    buf.seek(0)
    return zipfile.ZipFile(buf), manifest


def test_core_dump_cancel_mid_transfer_drops_the_partial_file():
    session = FakeCoreSession({CORE_A: b"aaaa", CORE_B: b"bbbb"}, cancel_during=CORE_B)
    zf, manifest = _collect_cores(session)

    assert session.exited
    assert not [n for n in zf.namelist() if n.startswith("core-dumps/core.")]
    assert SUMMARY_PATH in zf.namelist()
    # The orchestrator, not the collector, records the cancelled service.
    assert manifest.services == []


def test_core_dump_cancel_between_files_keeps_finished_cores():
    session = FakeCoreSession({CORE_A: b"aaaa", CORE_B: b"bbbb"}, cancel_after=CORE_B)
    zf, manifest = _collect_cores(session)

    assert session.exited
    cores = [n for n in zf.namelist() if n.startswith("core-dumps/core.")]
    assert cores == [f"core-dumps/{CORE_B}"]  # newest first; A never started
    summary = json.loads(zf.read(SUMMARY_PATH))
    assert [r["file"]["path"] for r in summary["collected"]] == [CORE_B]
    assert f"core-dumps/{CORE_B}" in manifest.collected_files

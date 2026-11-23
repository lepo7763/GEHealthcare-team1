"""Axone Logs as a tool in the diagnostic package (GET /api/logs/zip)."""

import io
import zipfile
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.diagnostics.service as diag_service
import app.log_collection.router as logs_router
from app.log_collection.progress import AXONE_LOGS_SERVICE_ID, ServiceProgress, tracker
from app.log_collection.schemas import LogCollectionManifest
from app.log_export.schemas import AxoneLogParams
from app.log_export.service import ExportError
from app.main import app

api = TestClient(app)
DEVICE_UUID = "d4e5f6a7-1234-5678-9abc-def012345678"
AXONE_QUERY = (
    "services=axone-logs&axone_scope=device"
    f"&axone_device_uuid={DEVICE_UUID}"
    "&axone_start_timestamp=2024-01-15T09:00:00.000"
    "&axone_end_timestamp=2024-01-15T09:45:00.000"
)
VALID_PARAMS = AxoneLogParams(
    axone_scope="device",
    axone_device_uuid=DEVICE_UUID,
    axone_start_timestamp="2024-01-15T09:00:00.000",
    axone_end_timestamp="2024-01-15T09:45:00.000",
)


@pytest.fixture
def no_k8s():
    from app.core.k8s_client import get_batch_v1_api, get_core_v1_api

    app.dependency_overrides[get_core_v1_api] = lambda: MagicMock()
    app.dependency_overrides[get_batch_v1_api] = lambda: MagicMock()
    yield
    app.dependency_overrides.clear()
    tracker.reset()


@pytest.fixture
def fake_collect(monkeypatch):
    seen = {}

    def collect(**kwargs):
        seen.update(kwargs)
        return io.BytesIO(b"PK")

    monkeypatch.setattr(logs_router, "collect_diagnostics", collect)
    return seen


def test_zip_endpoint_passes_axone_params(no_k8s, fake_collect):
    resp = api.get(f"/api/logs/zip?{AXONE_QUERY}&axone_event_category=3")
    assert resp.status_code == 200
    assert fake_collect["services"] == ["axone-logs"]
    p = fake_collect["axone_params"]
    assert p.axone_scope == "device" and p.axone_device_uuid == DEVICE_UUID
    assert p.axone_event_category == 3


@pytest.mark.parametrize(
    "query,message",
    [
        ("services=axone-logs", "start and end time"),
        (AXONE_QUERY.replace(DEVICE_UUID, "../../etc/passwd"), "device UUID"),
        (AXONE_QUERY.replace("09:45:00.000", "08:00:00.000"), "after start"),
        (AXONE_QUERY.replace("09:00:00.000", "09:00:00Z"), "without a time zone"),
        (
            AXONE_QUERY.replace("axone_scope=device", "axone_scope=all").replace(
                "09:45:00.000", "10:00:00.000"
            ),
            "within the same hour",
        ),
    ],
)
def test_zip_endpoint_rejects_bad_axone_filters_before_collecting(
    no_k8s, fake_collect, query, message
):
    resp = api.get(f"/api/logs/zip?{query}")
    assert resp.status_code == 422
    assert message in resp.json()["detail"]
    assert fake_collect == {}  # nothing started


def test_zip_endpoint_rejects_unknown_scope(no_k8s, fake_collect):
    resp = api.get("/api/logs/zip?" + AXONE_QUERY.replace("axone_scope=device", "axone_scope=pod"))
    assert resp.status_code == 422 and fake_collect == {}


def test_axone_filters_ignored_when_tool_not_selected(no_k8s, fake_collect):
    resp = api.get("/api/logs/zip?services=firewall&axone_scope=device")
    assert resp.status_code == 200 and fake_collect["services"] == ["firewall"]


def test_zip_endpoint_maps_export_errors_to_status(no_k8s, monkeypatch):
    def collect(**kwargs):
        raise ExportError(503, "Could not reach the Axone log service.")

    monkeypatch.setattr(logs_router, "collect_diagnostics", collect)
    resp = api.get(f"/api/logs/zip?{AXONE_QUERY}")
    assert resp.status_code == 503 and "Axone" in resp.json()["detail"]


# --- collector -------------------------------------------------------------------------


@pytest.fixture
def progress():
    tracker.try_begin([ServiceProgress(id=AXONE_LOGS_SERVICE_ID, label="Axone", unit="files")])
    yield
    tracker.reset()


def _collect(selected):
    buf = io.BytesIO()
    manifest = LogCollectionManifest(timestamp_utc="t", total_logs_collected=0)
    with zipfile.ZipFile(buf, "w") as zf:
        diag_service._collect_axone_logs(zf, manifest, VALID_PARAMS, selected)
    buf.seek(0)
    return zipfile.ZipFile(buf), manifest


def test_csv_is_added_to_package(progress, monkeypatch):
    monkeypatch.setattr(diag_service, "fetch_axone_csv", lambda p: b"time,description\r\n")
    zf, manifest = _collect([AXONE_LOGS_SERVICE_ID])
    assert zf.read("axone/axone_device_logs.csv") == b"time,description\r\n"
    assert manifest.services[0].status == "done"
    assert manifest.collected_files == ["axone/axone_device_logs.csv"]


def test_export_failure_is_recorded_when_other_tools_selected(progress, monkeypatch):
    def boom(p):
        raise ExportError(503, "Could not reach the Axone log service.")

    monkeypatch.setattr(diag_service, "fetch_axone_csv", boom)
    zf, manifest = _collect([AXONE_LOGS_SERVICE_ID, "firewall"])
    assert zf.namelist() == []
    assert manifest.services[0].status == "error"
    assert "Could not reach" in manifest.errors[0].reason
    assert tracker.snapshot()["services"][0]["status"] == "error"


def test_export_failure_is_raised_when_axone_is_the_only_tool(progress, monkeypatch):
    def boom(p):
        raise ExportError(503, "Could not reach the Axone log service.")

    monkeypatch.setattr(diag_service, "fetch_axone_csv", boom)
    with pytest.raises(ExportError):
        _collect([AXONE_LOGS_SERVICE_ID])

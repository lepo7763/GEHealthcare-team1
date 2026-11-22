import io
import json
import zipfile
import pytest

from app.cms import service
from app.cms import collector
from app.log_collection.schemas import LogCollectionManifest
from app.diagnostics import service as diagnostics
from app.log_collection.progress import tracker
from app.log_collection.schemas import LogCollectionParams
from app.umf_rti.schemas import UmfRtiParams
from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.log_collection.router as logs_router

def test_collect_snapshot_success(monkeypatch, tmp_path):
    filename = "SerialUnknown_test.zip"
    deleted_snapshots = []

    # Simulate CMS accepting a generation request
    monkeypatch.setattr(
        service,
        "generate_snapshot",
        lambda start, end: (
            f"Sprsnap generation request submitted successfully: {filename}"
        ),
    )

    # Simulate the snapshot becoming available
    monkeypatch.setattr(
        service,
        "wait_for_snapshot",
        lambda name: None,
    )

    # Simulate downloading a valid ZIP
    def fake_download(name, destination):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("compute-pods.log", "Example CMS logs")

        return destination

    monkeypatch.setattr(service, "download_snapshot", fake_download)

    # Record which server-side snapshot gets deleted
    monkeypatch.setattr(
        service,
        "delete_snapshot",
        lambda name: deleted_snapshots.append(name),
    )

    destination = tmp_path / "cms-test.zip"

    result = service.collect_snapshot(
        "2026-11-19T00:00:00.000",
        "2026-11-19T00:05:00.000",
        destination,
    )

    assert result == destination
    assert destination.exists()
    assert zipfile.is_zipfile(destination)
    assert deleted_snapshots == [filename]

def test_collect_snapshot_download_failure(monkeypatch, tmp_path):
    filename = "SerialUnknown_test.zip"
    deleted_snapshots = []

    # Simulate successful snapshot generation
    monkeypatch.setattr(
        service,
        "generate_snapshot",
        lambda start, end: (
            f"Sprsnap generation request submitted successfully: {filename}"
        ),
    )

    # Simulate successful polling
    monkeypatch.setattr(
        service,
        "wait_for_snapshot",
        lambda name: None,
    )

    # Simulate a download that fails halfway through
    def fake_download(name, destination):
        destination.write_bytes(b"incomplete download")
        raise OSError("Simulated download failure")

    monkeypatch.setattr(service, "download_snapshot", fake_download)

    # Track server-side deletion
    monkeypatch.setattr(
        service,
        "delete_snapshot",
        lambda name: deleted_snapshots.append(name),
    )

    destination = tmp_path / "cms-test.zip"

    with pytest.raises(OSError, match="Simulated download failure"):
        service.collect_snapshot(
            "2026-11-19T00:00:00.000",
            "2026-11-19T00:05:00.000",
            destination,
        )

    # The incomplete local file should be removed
    assert not destination.exists()

    # The server-side snapshot should also be deleted
    assert deleted_snapshots == [filename]

def test_collect_snapshot_cleanup_failure(monkeypatch, tmp_path, caplog):
    filename = "SerialUnknown_test.zip"

    monkeypatch.setattr(
        service,
        "generate_snapshot",
        lambda start, end: (
            f"Sprsnap generation request submitted successfully: {filename}"
        ),
    )

    monkeypatch.setattr(
        service,
        "wait_for_snapshot",
        lambda name: None,
    )

    # Simulate an incomplete download
    def fake_download(name, destination):
        destination.write_bytes(b"incomplete download")
        raise OSError("Download failed")

    # Simulate the server refusing to delete the snapshot
    def fake_delete(name):
        raise OSError("CMS deletion failed")

    monkeypatch.setattr(service, "download_snapshot", fake_download)
    monkeypatch.setattr(service, "delete_snapshot", fake_delete)

    destination = tmp_path / "cms-test.zip"

    with pytest.raises(OSError, match="Download failed"):
        service.collect_snapshot(
            "2026-11-19T00:00:00.000",
            "2026-11-19T00:05:00.000",
            destination,
        )

    # The incomplete local ZIP should be removed
    assert not destination.exists()

    # The failed server-side cleanup should be logged
    assert "Failed to delete CMS snapshot" in caplog.text
    assert "CMS deletion failed" in caplog.text


def test_cms_added_to_diagnostic_zip(monkeypatch, tmp_path):
    # Simulate a successful CMS download
    def fake_collect(start, end, destination, on_cleanup_warning=None):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr(
                "compute-pods.log.gz",
                b"Example CMS log data",
            )
        return destination

    monkeypatch.setattr(
        collector,
        "collect_snapshot",
        fake_collect,
    )

    manifest = LogCollectionManifest(
        timestamp_utc="2026-11-19T00:00:00Z",
        total_logs_collected=0,
    )

    output = tmp_path / "diagnostics.zip"

    # Build the final diagnostic ZIP
    with zipfile.ZipFile(output, "w") as zf:
        collector.collect_cms_into(
            zf,
            manifest,
            "2026-11-19T00:00:00.000",
            "2026-11-19T00:05:00.000",
        )

        zf.writestr(
            "manifest.json",
            manifest.model_dump_json(),
        )

    # Verify the final ZIP and nested CMS archive
    with zipfile.ZipFile(output, "r") as zf:
        assert "cms/snapshot.zip" in zf.namelist()

        cms_data = zf.read("cms/snapshot.zip")

        with zipfile.ZipFile(io.BytesIO(cms_data)) as cms_zip:
            assert cms_zip.read("compute-pods.log.gz") == (
                b"Example CMS log data"
            )

        manifest_data = json.loads(zf.read("manifest.json"))

        assert "cms/snapshot.zip" in manifest_data["collected_files"]
        assert any(
            item["id"] == "cms" and item["status"] == "done"
            for item in manifest_data["services"]
        )


def test_cms_through_diagnostics_orchestrator(monkeypatch):
    start = "2026-11-19T00:00:00.000"
    end = "2026-11-19T00:05:00.000"
    received_times = []

    # Simulate the CMS service returning a valid ZIP
    def fake_collect(start_datetime, end_datetime, destination, on_cleanup_warning=None):
        received_times.append((start_datetime, end_datetime))

        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr(
                "compute-pods.log.gz",
                b"Example CMS logs",
            )

        return destination

    monkeypatch.setattr(
        collector,
        "collect_snapshot",
        fake_collect,
    )

    tracker.reset()
    result = None

    try:
        # Request CMS through the real diagnostics orchestrator
        result = diagnostics.collect_diagnostics(
            core=None,
            batch=None,
            services=["cms"],
            log_params=LogCollectionParams(),
            umf_params=UmfRtiParams(),
            cms_start_datetime=start,
            cms_end_datetime=end,
        )

        # Inspect the resulting diagnostic ZIP
        with zipfile.ZipFile(result) as archive:
            assert "cms/snapshot.zip" in archive.namelist()

            manifest = json.loads(
                archive.read("manifest.json")
            )

            assert any(
                item["id"] == "cms" and item["status"] == "done"
                for item in manifest["services"]
            )

        # Confirm the correct time range reached the collector
        assert received_times == [(start, end)]

        # Confirm orchestration completed
        assert tracker.snapshot()["status"] == "done"

    finally:
        if result is not None:
            result.close()
        tracker.reset()


def test_cms_fastapi_endpoint(monkeypatch):
    received = {}

    def fake_collect_diagnostics(**kwargs):
        received.update(kwargs)

        # Simulate the final ZIP returned by the orchestrator
        output = io.BytesIO()

        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(
                "cms/snapshot.zip",
                b"Simulated CMS snapshot",
            )

        output.seek(0)
        return output

    monkeypatch.setattr(
        logs_router,
        "collect_diagnostics",
        fake_collect_diagnostics,
    )

    # Test only the diagnostics router, with mocked K8s clients
    app = FastAPI()
    app.include_router(logs_router.router)

    app.dependency_overrides[logs_router.get_core_v1_api] = lambda: None
    app.dependency_overrides[logs_router.get_batch_v1_api] = lambda: None

    logs_router.tracker.reset()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/logs/zip",
                params={
                    "services": "cms",
                    "cms_start_datetime": "2026-11-19T00:00:00.000",
                    "cms_end_datetime": "2026-11-19T00:05:00.000",
                },
            )

        assert response.status_code == 200
        assert received["services"] == ["cms"]

        assert received["cms_start_datetime"] == (
            "2026-11-19T00:00:00.000"
        )
        assert received["cms_end_datetime"] == (
            "2026-11-19T00:05:00.000"
        )

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert "cms/snapshot.zip" in archive.namelist()

    finally:
        logs_router.tracker.reset()


def test_cms_cleanup_warning_preserves_archive(monkeypatch, tmp_path):
    warning = "CMS cleanup failed: server-side snapshot may remain"

    def fake_collect(start, end, destination, on_cleanup_warning=None):
        # Simulate downloading a valid CMS archive
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("compute-pods.log.gz", b"Example CMS logs")

        # Simulate the server-side DELETE request failing
        if on_cleanup_warning is not None:
            on_cleanup_warning(warning)

        return destination

    monkeypatch.setattr(collector, "collect_snapshot", fake_collect)

    manifest = LogCollectionManifest(
        timestamp_utc="2026-11-19T00:00:00Z",
        total_logs_collected=0,
    )

    output = tmp_path / "diagnostics.zip"

    with zipfile.ZipFile(output, "w") as zf:
        collector.collect_cms_into(
            zf,
            manifest,
            "2026-11-19T00:00:00.000",
            "2026-11-19T00:05:00.000",
        )

    # The valid CMS archive must still be included
    with zipfile.ZipFile(output) as zf:
        assert "cms/snapshot.zip" in zf.namelist()

    # CMS collection should be marked successful
    cms_result = next(
        item for item in manifest.services if item.id == "cms"
    )
    assert cms_result.status == "done"

    # But the engineer must also see the cleanup warning
    assert warning in cms_result.error
    assert any(
        warning in item.reason
        for item in manifest.errors
        if item.service == "cms"
    )

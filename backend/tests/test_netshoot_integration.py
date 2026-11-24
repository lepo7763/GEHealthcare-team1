import io
import json
import zipfile

from pathlib import Path
from unittest.mock import Mock

import pytest

from app.diagnostics import service
from app.log_collection.progress import tracker
from app.log_collection.schemas import LogCollectionParams
from app.umf_rti.schemas import UmfRtiParams
from app.network_diagnostics.schemas import NetshootCollectionParams
from fastapi.testclient import TestClient
from app.main import app
from app.core.k8s_client import (
    get_core_v1_api,
    get_batch_v1_api
)


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_core_v1_api,
        lambda: Mock(),
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        get_batch_v1_api,
        lambda: Mock(),
    )

    return TestClient(app)



@pytest.fixture(autouse=True)
def reset_tracker(monkeypatch):
    tracker.reset()

    monkeypatch.setenv(
        "IOMT_NETSHOOT_ALLOWED_NAMESPACES",
        "iomt-dev-1",
    )

    yield

    tracker.reset()

def test_netshoot_diagnostics_zip(monkeypatch):

    def fake_collect(**kwargs):
        directory = Path(kwargs["destination_dir"])
        archive_path = directory / "job-a.zip"

        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("manifest.json", "{}")
            archive.writestr("capture-1.pcap", b"test data")

        return {"node-a": archive_path}, {}, {}

    mock_collect = Mock(side_effect=fake_collect)

    monkeypatch.setattr(
        service,
        "collect_netshoot_captures",
        mock_collect,
    )

    with service.collect_diagnostics(
        core=Mock(),
        batch=Mock(),
        services=["netshoot"],
        log_params=LogCollectionParams(),
        umf_params=UmfRtiParams(),
        netshoot_params=NetshootCollectionParams(
            netshoot_duration_seconds=45
        ),
    ) as result:

        with zipfile.ZipFile(result) as archive:
            path = "netshoot/node-a/job-a.zip"

            assert path in archive.namelist()

            manifest = json.loads(
                archive.read("manifest.json")
            )

            assert manifest["services"][0]["status"] == "done"
            assert path in manifest["collected_files"]

            with zipfile.ZipFile(
                io.BytesIO(archive.read(path))
            ) as worker_archive:

                assert worker_archive.read(
                    "capture-1.pcap"
                ) == b"test data"

    kwargs = mock_collect.call_args.kwargs

    assert kwargs["duration_seconds"] == 45
    assert kwargs["namespaces"] is None

    assert not Path(kwargs["destination_dir"]).exists()

def test_netshoot_diagnostics_partial_failure(monkeypatch):

    def fake_collect(**kwargs):
        directory = Path(kwargs["destination_dir"])
        archive_path = directory / "job-a.zip"

        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("manifest.json", "{}")

        return (
            {"node-a": archive_path},
            {"node-b": "Retrieval timed out"},
            {"job-c": "Deletion failed"},
        )

    monkeypatch.setattr(
        service,
        "collect_netshoot_captures",
        fake_collect,
    )

    with service.collect_diagnostics(
        core=Mock(),
        batch=Mock(),
        services=["netshoot"],
        log_params=LogCollectionParams(),
        umf_params=UmfRtiParams(),
    ) as result:

        with zipfile.ZipFile(result) as archive:
            assert (
                "netshoot/node-a/job-a.zip"
                in archive.namelist()
            )

            manifest = json.loads(
                archive.read("manifest.json")
            )

            assert manifest["services"][0]["status"] == "error"
            assert len(manifest["errors"]) == 2

            assert "node-b" in manifest["errors"][0]["reason"]
            assert "job-c" in manifest["errors"][1]["reason"]

def test_netshoot_diagnostics_discovery_denied(monkeypatch):
    from kubernetes.client.exceptions import ApiException

    mock_collect = Mock(
        side_effect=ApiException(
            status=403,
            reason="Forbidden",
        )
    )

    monkeypatch.setattr(
        service,
        "collect_netshoot_captures",
        mock_collect,
    )

    with service.collect_diagnostics(
        core=Mock(),
        batch=Mock(),
        services=["netshoot"],
        log_params=LogCollectionParams(),
        umf_params=UmfRtiParams(),
    ) as result:

        with zipfile.ZipFile(result) as archive:
            manifest = json.loads(
                archive.read("manifest.json")
            )

            assert manifest["services"][0]["status"] == "error"
            assert "403" in manifest["errors"][0]["reason"]

    mock_collect.assert_called_once()

def test_netshoot_api_download(monkeypatch, api_client):

    def fake_collect(**kwargs):
        path = Path(kwargs["destination_dir"]) / "job-a.zip"

        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("manifest.json", "{}")
            archive.writestr("capture-1.pcap", b"test data")

        return {"node-a": path}, {}, {}

    mock_collect = Mock(side_effect=fake_collect)

    monkeypatch.setattr(
        service,
        "collect_netshoot_captures",
        mock_collect,
    )

    response = api_client.get(
        "/api/logs/zip",
        params={
            "services": "netshoot",
            "netshoot_duration_seconds": 60,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "netshoot/node-a/job-a.zip" in archive.namelist()

    assert mock_collect.call_args.kwargs["duration_seconds"] == 60

def test_netshoot_api_combined_services(monkeypatch, api_client):

    def fake_netshoot(**kwargs):
        path = Path(kwargs["destination_dir"]) / "job-a.zip"

        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("manifest.json", "{}")

        return {"node-a": path}, {}, {}

    def fake_logs(zf, manifest, core, params):
        path = "logs/example.log"

        zf.writestr(path, "Example container log")
        manifest.collected_files.append(path)

        return [path]

    monkeypatch.setattr(
        service, "collect_netshoot_captures", fake_netshoot
    )

    monkeypatch.setattr(
        service, "collect_container_logs_into", fake_logs
    )

    response = api_client.get(
        "/api/logs/zip",
        params=[
            ("services", "container-logs"),
            ("services", "netshoot"),
        ],
    )

    assert response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "logs/example.log" in archive.namelist()
        assert "netshoot/node-a/job-a.zip" in archive.namelist()

        manifest = json.loads(archive.read("manifest.json"))

        assert len(manifest["services"]) == 2

@pytest.mark.parametrize("duration", [0, -1, 601])
def test_netshoot_api_invalid_duration(api_client, duration):

    response = api_client.get(
        "/api/logs/zip",
        params={
            "services": "netshoot",
            "netshoot_duration_seconds": duration,
        },
    )

    assert response.status_code == 422

@pytest.mark.parametrize("scope", ["both", "host"])
def test_netshoot_restricted_namespace_rejects_host_capture(
    monkeypatch, scope
):
    monkeypatch.setenv(
        "IOMT_NETSHOOT_TEST_NAMESPACE",
        "iomt-dev-1",
    )

    mock_collect = Mock()

    monkeypatch.setattr(
        service,
        "collect_netshoot_captures",
        mock_collect,
    )

    with service.collect_diagnostics(
        core=Mock(),
        batch=Mock(),
        services=["netshoot"],
        log_params=LogCollectionParams(),
        umf_params=UmfRtiParams(),
        netshoot_params=NetshootCollectionParams(
            netshoot_scope=scope,
        ),
    ) as result:

        with zipfile.ZipFile(result) as archive:
            manifest = json.loads(
                archive.read("manifest.json")
            )

            assert manifest["services"][0]["status"] == "error"
            assert "namespace-restricted" in (
                manifest["errors"][0]["reason"]
            )

    mock_collect.assert_not_called()

def test_netshoot_restricted_namespace_allows_pod_capture(monkeypatch):
    monkeypatch.setenv(
        "IOMT_NETSHOOT_TEST_NAMESPACE",
        "iomt-dev-1",
    )

    def fake_collect(**kwargs):
        directory = Path(kwargs["destination_dir"])
        archive_path = directory / "test-capture.zip"

        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("capture-1.pcap", b"test data")

        return {"test-node": archive_path}, {}, {}

    mock_collect = Mock(side_effect=fake_collect)

    monkeypatch.setattr(
        service,
        "collect_netshoot_captures",
        mock_collect,
    )

    with service.collect_diagnostics(
        core=Mock(),
        batch=Mock(),
        services=["netshoot"],
        log_params=LogCollectionParams(),
        umf_params=UmfRtiParams(),
        netshoot_params=NetshootCollectionParams(
            netshoot_duration_seconds=15,
            netshoot_scope="pod",
        ),
    ) as result:
        with zipfile.ZipFile(result) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["services"][0]["status"] == "done"

    kwargs = mock_collect.call_args.kwargs

    assert kwargs["namespaces"] == ["iomt-dev-1"]
    assert kwargs["scope"] == "pod"
    assert kwargs["duration_seconds"] == 15
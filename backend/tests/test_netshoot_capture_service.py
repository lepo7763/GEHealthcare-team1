from types import SimpleNamespace
from unittest.mock import Mock
from pydantic import ValidationError

import pytest
import base64
import hashlib
import io
import zipfile

from app.network_diagnostics import capture_service
from app.network_diagnostics.capture_service import (wait_for_worker_pod, NetshootCaptureError,)
from app.network_diagnostics.schemas import NetshootCollectionParams

from kubernetes.client.exceptions import ApiException
from app.network_diagnostics.capture_service import (wait_for_archive, collect_worker_archive, collect_worker_archives, cleanup_capture_jobs, collect_netshoot_captures)
from app.network_diagnostics.capture_service import retrieve_capture_archive

from threading import Barrier

def test_wait_for_worker_pod_success(monkeypatch):
    core = Mock()

    pending_pod = SimpleNamespace(
        metadata=SimpleNamespace(name="worker-abc"),
        status=SimpleNamespace(phase="Pending"),
    )

    running_pod = SimpleNamespace(
        metadata=SimpleNamespace(name="worker-abc"),
        status=SimpleNamespace(phase="Running"),
    )

    core.list_namespaced_pod.side_effect = [
        SimpleNamespace(items=[]),
        SimpleNamespace(items=[pending_pod]),
        SimpleNamespace(items=[running_pod]),
    ]

    monkeypatch.setattr(capture_service, "sleep", Mock())

    result = wait_for_worker_pod(core, "test-job")

    assert result == "worker-abc"
    assert core.list_namespaced_pod.call_count == 3

@pytest.mark.parametrize("phase", ["Failed", "Succeeded"])
def test_wait_for_worker_pod_terminated(phase):
    core = Mock()

    core.list_namespaced_pod.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name="worker-abc"),
                status=SimpleNamespace(phase=phase),
            )
        ]
    )

    with pytest.raises(NetshootCaptureError):
        wait_for_worker_pod(core, "test-job")

def test_wait_for_worker_pod_timeout(monkeypatch):
    core = Mock()

    core.list_namespaced_pod.return_value = SimpleNamespace(
        items=[]
    )

    monkeypatch.setattr(
        capture_service,
        "monotonic",
        Mock(side_effect=[0, 0, 61]),
    )

    monkeypatch.setattr(capture_service, "sleep", Mock())

    with pytest.raises(NetshootCaptureError):
        wait_for_worker_pod(core, "test-job")

def test_wait_for_archive_success(monkeypatch):
    core = Mock()

    core.read_namespaced_pod.return_value = SimpleNamespace(
        status=SimpleNamespace(phase="Running")
    )

    mock_stream = Mock(
        side_effect=["", "", "NETSHOOT_ARCHIVE_READY\n"]
    )

    monkeypatch.setattr(capture_service, "stream", mock_stream)
    monkeypatch.setattr(capture_service, "sleep", Mock())

    wait_for_archive(core, "worker-abc")

    assert mock_stream.call_count == 3

@pytest.mark.parametrize("phase", ["Failed", "Succeeded"])
def test_wait_for_archive_terminated(monkeypatch, phase):
    core = Mock()

    core.read_namespaced_pod.return_value = SimpleNamespace(
        status=SimpleNamespace(phase=phase)
    )

    mock_stream = Mock()
    monkeypatch.setattr(capture_service, "stream", mock_stream)

    with pytest.raises(NetshootCaptureError):
        wait_for_archive(core, "worker-abc")

    mock_stream.assert_not_called()

def test_wait_for_archive_forbidden(monkeypatch):
    core = Mock()

    core.read_namespaced_pod.return_value = SimpleNamespace(
        status=SimpleNamespace(phase="Running")
    )

    mock_stream = Mock(
        side_effect=ApiException(status=403)
    )

    monkeypatch.setattr(capture_service, "stream", mock_stream)

    with pytest.raises(NetshootCaptureError):
        wait_for_archive(core, "worker-abc")

    mock_stream.assert_called_once()

def test_wait_for_archive_timeout(monkeypatch):
    core = Mock()

    core.read_namespaced_pod.return_value = SimpleNamespace(
        status=SimpleNamespace(phase="Running")
    )

    monkeypatch.setattr(
        capture_service, "stream", Mock(return_value="")
    )

    monkeypatch.setattr(capture_service, "sleep", Mock())

    monkeypatch.setattr(
        capture_service,
        "monotonic",
        Mock(side_effect=[0, 0, 181]),
    )

    with pytest.raises(NetshootCaptureError):
        wait_for_archive(core, "worker-abc")

def test_retrieve_capture_archive_success(monkeypatch, tmp_path):
    core = Mock()

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("capture-1.pcap", b"example data")

    data = buffer.getvalue()
    checksum = hashlib.sha256(data).hexdigest()

    responses = [
        f"{len(data)}\n{checksum} job-artifacts.zip\n"
    ]

    for offset in range(0, len(data), 64):
        chunk = data[offset:offset + 64]
        responses.append(base64.b64encode(chunk).decode())

    monkeypatch.setattr(
        capture_service,
        "stream",
        Mock(side_effect=responses),
    )

    destination = tmp_path / "capture.zip"

    result = retrieve_capture_archive(
        core,
        "worker-abc",
        destination,
        chunk_bytes=64,
    )

    assert result == destination
    assert destination.read_bytes() == data

def test_retrieve_capture_archive_oversized(monkeypatch, tmp_path):
    mock_stream = Mock(
        return_value=f"1024\n{'0' * 64} job-artifacts.zip"
    )

    monkeypatch.setattr(
        capture_service, "stream", mock_stream
    )

    with pytest.raises(NetshootCaptureError):
        retrieve_capture_archive(
            Mock(),
            "worker-abc",
            tmp_path / "capture.zip",
            max_bytes=512,
        )

    mock_stream.assert_called_once()
    assert not (tmp_path / "capture.zip").exists()

def test_retrieve_capture_archive_bad_checksum(
    monkeypatch, tmp_path
):
    data = b"example data"

    monkeypatch.setattr(
        capture_service,
        "stream",
        Mock(side_effect=[
            f"{len(data)}\n{'0' * 64} job-artifacts.zip",
            base64.b64encode(data).decode(),
        ]),
    )

    with pytest.raises(
        NetshootCaptureError,
        match="checksum mismatch",
    ):
        retrieve_capture_archive(
            Mock(),
            "worker-abc",
            tmp_path / "capture.zip",
        )

    assert not (tmp_path / "capture.zip").exists()
    assert not list(tmp_path.glob("*.partial"))

def test_collect_worker_archive_success(monkeypatch, tmp_path):
    core = Mock()
    destination = tmp_path / "capture.zip"

    mock_wait_pod = Mock(return_value="worker-abc")
    mock_wait_archive = Mock()
    mock_retrieve = Mock(return_value=destination)

    monkeypatch.setattr(
        capture_service,
        "wait_for_worker_pod",
        mock_wait_pod,
    )

    monkeypatch.setattr(
        capture_service,
        "wait_for_archive",
        mock_wait_archive,
    )

    monkeypatch.setattr(
        capture_service,
        "retrieve_capture_archive",
        mock_retrieve,
    )

    result = collect_worker_archive(
        core,
        "test-job",
        destination,
        duration_seconds=600,
    )

    mock_wait_pod.assert_called_once_with(
        core, "test-job"
    )

    mock_wait_archive.assert_called_once_with(
        core,
        "worker-abc",
        timeout_seconds=720,
    )

    mock_retrieve.assert_called_once_with(
        core,
        "worker-abc",
        destination,
    )

    assert result == destination

def test_collect_worker_archive_not_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(
        capture_service,
        "wait_for_worker_pod",
        Mock(return_value="worker-abc"),
    )

    monkeypatch.setattr(
        capture_service,
        "wait_for_archive",
        Mock(side_effect=NetshootCaptureError("Timeout")),
    )

    mock_retrieve = Mock()

    monkeypatch.setattr(
        capture_service,
        "retrieve_capture_archive",
        mock_retrieve,
    )

    with pytest.raises(NetshootCaptureError):
        collect_worker_archive(
            Mock(),
            "test-job",
            tmp_path / "capture.zip",
            duration_seconds=30,
        )

    mock_retrieve.assert_not_called()

def test_collect_worker_archives_success(
    monkeypatch, tmp_path
):
    core = Mock()
    barrier = Barrier(2, timeout=5)

    jobs = {
        "node-a": {"job_name": "job-a"},
        "node-b": {"job_name": "job-b"},
    }

    def fake_collect(config, job_name, destination, duration):
        barrier.wait()
        return destination

    monkeypatch.setattr(
        capture_service,
        "collect_worker_archive_independent",
        fake_collect,
    )

    archives, errors = collect_worker_archives(
        core, jobs, tmp_path, 30
    )

    assert archives == {
        "node-a": tmp_path / "job-a.zip",
        "node-b": tmp_path / "job-b.zip",
    }

    assert errors == {}

def test_collect_worker_archives_partial_failure(
    monkeypatch, tmp_path
):
    jobs = {
        "node-a": {"job_name": "job-a"},
        "node-b": {"job_name": "job-b"},
    }

    def fake_collect(config, job_name, destination, duration):
        if job_name == "job-b":
            raise NetshootCaptureError("Retrieval failed")

        return destination

    monkeypatch.setattr(
        capture_service,
        "collect_worker_archive_independent",
        fake_collect,
    )

    archives, errors = collect_worker_archives(
        Mock(), jobs, tmp_path, 30
    )

    assert archives == {
        "node-a": tmp_path / "job-a.zip"
    }

    assert errors == {
        "node-b": "Retrieval failed"
    }

def test_collect_worker_archives_empty(tmp_path):
    archives, errors = collect_worker_archives(
        Mock(), {}, tmp_path, 30
    )

    assert archives == {}
    assert errors == {}

def test_cleanup_capture_jobs_partial_failure():
    batch = Mock()

    jobs = {
        "node-a": {"job_name": "job-a"},
        "node-b": {"job_name": "job-b"},
        "node-c": {"job_name": "job-c"},
    }

    batch.delete_namespaced_job.side_effect = [
        ApiException(status=403),
        ApiException(status=404),
        None,
    ]

    errors = cleanup_capture_jobs(batch, jobs)

    assert errors == {
        "job-a": "Kubernetes API error: 403"
    }

    assert batch.delete_namespaced_job.call_count == 3

def test_collect_netshoot_captures_success(
    monkeypatch, tmp_path
):
    core = Mock()
    batch = Mock()

    jobs = {
        "node-a": {"job_name": "job-a"}
    }

    expected_archives = {
        "node-a": tmp_path / "job-a.zip"
    }

    mock_schedule = Mock(return_value=jobs)
    mock_collect = Mock(
        return_value=(expected_archives, {})
    )

    monkeypatch.setattr(
        capture_service,
        "schedule_capture_jobs",
        mock_schedule,
    )

    monkeypatch.setattr(
        capture_service,
        "collect_worker_archives",
        mock_collect,
    )

    archives, errors, cleanup_errors = (
        collect_netshoot_captures(
            core, batch, ["iomt-dev-1"], tmp_path, 30
        )
    )

    assert archives == expected_archives
    assert errors == {}
    assert cleanup_errors == {}

    batch.delete_namespaced_job.assert_called_once_with(
        name="job-a",
        namespace=capture_service.DIAGNOSTICS_NAMESPACE,
        propagation_policy="Foreground",
        _request_timeout=10,
    )

def test_collect_netshoot_captures_failure(
    monkeypatch, tmp_path
):
    batch = Mock()

    jobs = {
        "node-a": {"job_name": "job-a"},
        "node-b": {"job_name": "job-b"},
    }

    monkeypatch.setattr(
        capture_service,
        "schedule_capture_jobs",
        Mock(return_value=jobs),
    )

    monkeypatch.setattr(
        capture_service,
        "collect_worker_archives",
        Mock(side_effect=NetshootCaptureError("Failed")),
    )

    with pytest.raises(NetshootCaptureError):
        collect_netshoot_captures(
            Mock(), batch, ["iomt-dev-1"], tmp_path, 30
        )

    assert batch.delete_namespaced_job.call_count == 2

def test_collect_netshoot_captures_no_targets(
    monkeypatch, tmp_path
):
    batch = Mock()

    monkeypatch.setattr(
        capture_service,
        "schedule_capture_jobs",
        Mock(return_value={}),
    )

    with pytest.raises(
        NetshootCaptureError,
        match="No eligible running Pods",
    ):
        collect_netshoot_captures(
            Mock(), batch, ["iomt-dev-1"], tmp_path, 30
        )

    batch.delete_namespaced_job.assert_not_called()

def test_netshoot_collection_params_default():
    params = NetshootCollectionParams()

    assert params.netshoot_duration_seconds == 30


@pytest.mark.parametrize("duration", [1, 600])
def test_netshoot_collection_params_valid(duration):
    params = NetshootCollectionParams(
        netshoot_duration_seconds=duration
    )

    assert params.netshoot_duration_seconds == duration


@pytest.mark.parametrize("duration", [0, -1, 601])
def test_netshoot_collection_params_invalid(duration):
    with pytest.raises(ValidationError):
        NetshootCollectionParams(
            netshoot_duration_seconds=duration
        )
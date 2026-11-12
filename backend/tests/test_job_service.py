from app.network_diagnostics.job_service import (discover_targets_across_namespaces, build_netshoot_job, submit_netshoot_job, get_netshoot_job_status, 
                                                 discover_capture_targets,schedule_capture_jobs, find_ready_sandbox_id, extract_sandbox_pid, resolve_pod_pid,
                                                 CRI_SOCKET_PATH, CaptureSchedulingCleanupError)


from app.network_diagnostics.capture_worker import (load_capture_targets, resolve_capture_targets, build_tcpdump_command, start_capture_processes, 
                                                    finish_capture_processes, inspect_pcap_file, summarize_capture_results, run_capture_session)


from app.network_diagnostics import worker_main

from app.network_diagnostics.artifact_packaging import (
    create_capture_archive,
)

from app.network_diagnostics.artifact_upload import (upload_capture_archive,)

from app.network_diagnostics.artifact_receiver import artifact_router

from kubernetes.client.exceptions import ApiException

from fastapi import FastAPI
from fastapi.testclient import TestClient


from types import SimpleNamespace
from unittest.mock import Mock, patch

import json
import pytest
import struct
import hashlib

def test_build_netshoot_job():
    job = build_netshoot_job("test-node")

    assert job.metadata.namespace == "iomt-integration"
    assert job.metadata.generate_name == "netshoot-diagnostics-"

    pod_spec = job.spec.template.spec

    assert pod_spec.node_name == "test-node"
    assert pod_spec.restart_policy == "Never"

    container = pod_spec.containers[0]

    assert container.name == "netshoot"
    assert container.resources.limits["cpu"] == "250m"
    assert job.spec.backoff_limit == 0


def test_submit_netshoot_job():
    # Simulate the Kubernetes Batch API.
    mock_batch = Mock()

    # Simulate Kubernetes returning a generated Job name.
    mock_batch.create_namespaced_job.return_value = (
        SimpleNamespace(
            metadata=SimpleNamespace(
                name="netshoot-diagnostics-abc123"
            )
        )
    )

    result = submit_netshoot_job(
        batch_api=mock_batch,
        node_name="test-node",
    )

    assert result == "netshoot-diagnostics-abc123"

    mock_batch.create_namespaced_job.assert_called_once()

    # Inspect the arguments we sent to Kubernetes.
    kwargs = mock_batch.create_namespaced_job.call_args.kwargs

    assert kwargs["namespace"] == "iomt-integration"
    assert kwargs["body"].spec.template.spec.node_name == "test-node"
    assert kwargs["_request_timeout"] == 10


@pytest.mark.parametrize(
    "conditions, active, succeeded, failed, expected",
    [
        ([], 0, 0, 0, "pending"),
        ([], 1, 0, 0, "active"),
        ([("Complete", "True")], 0, 1, 0, "complete"),
        ([("Failed", "True")], 0, 0, 1, "failed"),
        ([], 1, 0, 1, "active"),
    ],
)
def test_get_netshoot_job_status(
    conditions, active, succeeded, failed, expected
):
    mock_batch = Mock()

    mock_batch.read_namespaced_job_status.return_value = (
        SimpleNamespace(
            status=SimpleNamespace(
                active=active,
                succeeded=succeeded,
                failed=failed,
                conditions=[
                    SimpleNamespace(type=t, status=s)
                    for t, s in conditions
                ],
            )
        )
    )

    result = get_netshoot_job_status(
        mock_batch,
        "netshoot-diagnostics-abc123",
    )

    assert result["state"] == expected
    assert result["failed"] == failed

    mock_batch.read_namespaced_job_status.assert_called_once_with(
        name="netshoot-diagnostics-abc123",
        namespace="iomt-integration",
        _request_timeout=10,
    )


def test_discover_capture_targets():
    mock_core = Mock()

    def make_pod(name, uid, node, ip, phase="Running"):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                name=name,
                uid=uid,
                deletion_timestamp=None,
            ),
            spec=SimpleNamespace(
                node_name=node,
                host_network=False,
            ),
            status=SimpleNamespace(
                phase=phase,
                pod_ip=ip,
            ),
        )

    mock_core.list_namespaced_pod.return_value = SimpleNamespace(
        items=[
            make_pod("http-test-1", "uid-1", "node-A", "10.0.0.1"),
            make_pod("http-test-2", "uid-2", "node-A", "10.0.0.2"),
            make_pod("backend", "uid-3", "node-B", "10.0.0.3"),
            make_pod("pending", "uid-4", "node-B", None, "Pending"),
        ]
    )

    result = discover_capture_targets(
        mock_core,
        namespace="iomt-dev-1",
    )

    assert len(result) == 2
    assert len(result["node-A"]) == 2
    assert len(result["node-B"]) == 1

    assert result["node-A"][0]["name"] == "http-test-1"
    assert result["node-A"][0]["uid"] == "uid-1"

    mock_core.list_namespaced_pod.assert_called_once_with(
        namespace="iomt-dev-1",
        _request_timeout=10,
    )

    
def test_schedule_capture_jobs():
    mock_core = Mock()
    mock_batch = Mock()

    def make_pod(name, uid, node, ip):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                name=name,
                uid=uid,
                deletion_timestamp=None,
            ),
            spec=SimpleNamespace(
                node_name=node,
                host_network=False,
            ),
            status=SimpleNamespace(
                phase="Running",
                pod_ip=ip,
            ),
        )

    mock_core.list_namespaced_pod.return_value = SimpleNamespace(
        items=[
            make_pod("pod-1", "uid-1", "node-A", "10.0.0.1"),
            make_pod("pod-2", "uid-2", "node-A", "10.0.0.2"),
            make_pod("pod-3", "uid-3", "node-B", "10.0.0.3"),
        ]
    )

    mock_batch.create_namespaced_job.side_effect = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="job-A")
        ),
        SimpleNamespace(
            metadata=SimpleNamespace(name="job-B")
        ),
    ]

    result = schedule_capture_jobs(
        mock_core,
        mock_batch,
        ["iomt-dev-1"],
    )

    assert len(result) == 2

    assert result["node-A"]["job_name"] == "job-A"
    assert len(result["node-A"]["targets"]) == 2

    assert result["node-B"]["job_name"] == "job-B"
    assert len(result["node-B"]["targets"]) == 1

    assert mock_batch.create_namespaced_job.call_count == 2


def test_discover_targets_across_namespaces():
    mock_core = Mock()

    def make_pod(name, uid, node, ip):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                name=name,
                uid=uid,
                deletion_timestamp=None,
            ),
            spec=SimpleNamespace(
                node_name=node,
                host_network=False,
            ),
            status=SimpleNamespace(
                phase="Running",
                pod_ip=ip,
            ),
        )

    mock_core.list_namespaced_pod.side_effect = [
        SimpleNamespace(
            items=[
                make_pod("http-test-1", "uid-1", "node-A", "10.0.0.1"),
                make_pod("http-test-2", "uid-2", "node-A", "10.0.0.2"),
            ]
        ),
        SimpleNamespace(
            items=[
                make_pod("backend", "uid-3", "node-A", "10.0.0.3"),
                make_pod("other", "uid-4", "node-B", "10.0.0.4"),
            ]
        ),
    ]

    result = discover_targets_across_namespaces(
        mock_core,
        ["iomt-dev-1", "iomt-integration"],
    )

    assert len(result) == 2
    assert len(result["node-A"]) == 3
    assert len(result["node-B"]) == 1

    assert result["node-A"][2]["name"] == "backend"
    assert result["node-A"][2]["namespace"] == "iomt-integration"

    assert mock_core.list_namespaced_pod.call_count == 2

    
def test_schedule_jobs_across_namespaces():
    mock_core = Mock()
    mock_batch = Mock()

    def make_pod(name, uid, node, ip):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                name=name,
                uid=uid,
                deletion_timestamp=None,
            ),
            spec=SimpleNamespace(
                node_name=node,
                host_network=False,
            ),
            status=SimpleNamespace(
                phase="Running",
                pod_ip=ip,
            ),
        )

    mock_core.list_namespaced_pod.side_effect = [
        SimpleNamespace(items=[
            make_pod("backend", "uid-1", "node-A", "10.0.0.1"),
        ]),
        SimpleNamespace(items=[
            make_pod("backend", "uid-2", "node-A", "10.0.0.2"),
            make_pod("database", "uid-3", "node-B", "10.0.0.3"),
        ]),
    ]

    mock_batch.create_namespaced_job.side_effect = [
        SimpleNamespace(metadata=SimpleNamespace(name="job-A")),
        SimpleNamespace(metadata=SimpleNamespace(name="job-B")),
    ]

    result = schedule_capture_jobs(
        mock_core,
        mock_batch,
        ["iomt-dev-1", "iomt-integration"],
    )

    assert len(result) == 2
    assert mock_batch.create_namespaced_job.call_count == 2

    node_a = result["node-A"]["targets"]

    assert len(node_a) == 2
    assert {pod["uid"] for pod in node_a} == {
        "uid-1",
        "uid-2",
    }
    assert {pod["namespace"] for pod in node_a} == {
        "iomt-dev-1",
        "iomt-integration",
    }

    assert len(result["node-B"]["targets"]) == 1


def test_job_receives_capture_targets():
    targets = [
        {
            "name": "http-test-1",
            "namespace": "iomt-dev-1",
            "uid": "uid-123",
            "ip": "10.0.0.1",
        }
    ]

    job = build_netshoot_job(
        node_name="node-A",
        targets=targets,
    )

    container = job.spec.template.spec.containers[0]

    env_vars = {
        variable.name: variable.value
        for variable in container.env
    }

    received_targets = json.loads(
        env_vars["CAPTURE_TARGETS_JSON"]
    )

    assert received_targets == targets
    assert job.spec.template.spec.node_name == "node-A"


def test_find_ready_sandbox_id():
    sandboxes = [
        {
            "id": "old-sandbox",
            "metadata": {"uid": "uid-123"},
            "state": "SANDBOX_NOTREADY",
        },
        {
            "id": "active-sandbox",
            "metadata": {"uid": "uid-123"},
            "state": "SANDBOX_READY",
        },
        {
            "id": "other-pod-sandbox",
            "metadata": {"uid": "uid-456"},
            "state": "SANDBOX_READY",
        },
    ]

    result = find_ready_sandbox_id("uid-123", sandboxes)

    assert result == "active-sandbox"


def test_find_ready_sandbox_id_missing():
    sandboxes = [
        {
            "id": "old-sandbox",
            "metadata": {"uid": "uid-123"},
            "state": "SANDBOX_NOTREADY",
        }
    ]

    with pytest.raises(ValueError):
        find_ready_sandbox_id("uid-123", sandboxes)

def test_extract_sandbox_pid():
    inspection = {
        "info": {
            "pid": 13314
        }
    }

    assert extract_sandbox_pid(inspection) == 13314


@pytest.mark.parametrize(
    "inspection",
    [
        {},
        {"info": {}},
        {"info": {"pid": 0}},
        {"info": {"pid": "invalid"}},
    ],
)
def test_extract_sandbox_pid_invalid(inspection):
    with pytest.raises(ValueError):
        extract_sandbox_pid(inspection)

def test_resolve_pod_pid_calls_crictl(monkeypatch):
    from types import SimpleNamespace

    commands = []
    responses = iter([
        '{"items": [{"id": "sandbox-123", '
        '"metadata": {"uid": "uid-123"}, '
        '"state": "SANDBOX_READY"}]}',
        '{"info": {"pid": 13314}}',
    ])

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=next(responses))

    monkeypatch.setattr(
        "app.network_diagnostics.runtime_discovery.subprocess.run",
        fake_run,
    )

    pid = resolve_pod_pid("uid-123", "iomt-dev-1")

    assert pid == 13314
    assert len(commands) == 2
    assert commands[0][-5:] == [
        "pods", "--namespace", "iomt-dev-1", "-o", "json"
    ]
    assert commands[1][-2:] == [
        "inspectp", "sandbox-123"
    ]

def test_load_capture_targets():
    targets = [
        {
            "name": "http-test-1",
            "namespace": "iomt-dev-1",
            "uid": "uid-123",
            "ip": "100.64.64.182",
        }
    ]

    result = load_capture_targets(json.dumps(targets))

    assert result == targets


@pytest.mark.parametrize(
    "raw_json",
    [
        "{}",
        '[{"name": "http-test-1"}]',
        '[{"name": "", "namespace": "iomt-dev-1", "uid": "uid-123"}]',
        '["http-test-1"]',
    ],
)
def test_load_capture_targets_invalid(raw_json):
    with pytest.raises(ValueError):
        load_capture_targets(raw_json)

def test_resolve_capture_targets_partial_success():
    targets = [
        {"name": "pod-1", "namespace": "iomt-dev-1", "uid": "uid-1"},
        {"name": "pod-2", "namespace": "iomt-dev-1", "uid": "uid-2"},
        {"name": "pod-3", "namespace": "iomt-dev-1", "uid": "uid-3"},
    ]

    def fake_resolver(uid, namespace):
        if uid == "uid-2":
            raise ValueError("No Ready sandbox found")

        return {
            "uid-1": 1001,
            "uid-3": 1003,
        }[uid]

    result = resolve_capture_targets(targets, fake_resolver)

    assert len(result["resolved"]) == 2
    assert len(result["unavailable"]) == 1

    assert result["resolved"][0]["pid"] == 1001
    assert result["resolved"][1]["pid"] == 1003

    assert result["unavailable"][0]["uid"] == "uid-2"

def test_build_tcpdump_command():
    command = build_tcpdump_command(
        13314,
        "/tmp/http-test-1.pcap",
    )

    assert command == [
        "nsenter",
        "-t", "13314",
        "-n",
        "--",
        "tcpdump",
        "-i", "any",
        "-nn",
        "-s", "0",
        "-U",
        "-w", "/tmp/http-test-1.pcap",
    ]


@pytest.mark.parametrize("pid", [0, -1, "13314", True])
def test_build_tcpdump_command_invalid_pid(pid):
    with pytest.raises(ValueError):
        build_tcpdump_command(pid, "/tmp/test.pcap")

def test_start_capture_processes_partial_success(tmp_path):
    from types import SimpleNamespace

    targets = [
        {"name": "pod-1", "namespace": "iomt-dev-1", "uid": "uid-1"},
        {"name": "pod-2", "namespace": "iomt-dev-1", "uid": "uid-2"},
        {"name": "pod-3", "namespace": "iomt-dev-1", "uid": "uid-3"},
    ]

    commands = []

    def fake_resolver(uid, namespace):
        if uid == "uid-2":
            raise ValueError("Sandbox unavailable")

        return {"uid-1": 1001, "uid-3": 1003}[uid]

    def fake_popen(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(pid=2000 + len(commands))

    result = start_capture_processes(
        targets,
        str(tmp_path),
        resolver=fake_resolver,
        popen_factory=fake_popen,
    )

    assert len(result["running"]) == 2
    assert len(result["unavailable"]) == 1
    assert result["unavailable"][0]["uid"] == "uid-2"

    assert commands[0][0:4] == [
        "nsenter", "-t", "1001", "-n"
    ]
    assert commands[1][0:4] == [
        "nsenter", "-t", "1003", "-n"
    ]

    assert result["running"][0]["process"].pid == 2001
    assert result["running"][1]["process"].pid == 2002


def test_finish_capture_processes(monkeypatch):
    import signal
    from types import SimpleNamespace

    events = []

    def fake_sleep(seconds):
        events.append(("sleep", seconds))

    def fake_killpg(pid, sig):
        events.append(("signal", pid, sig))

    def fake_wait(timeout):
        events.append(("wait", timeout))
        return 0

    process = SimpleNamespace(
        pid=2001,
        poll=lambda: None,
        wait=fake_wait,
    )

    running = [{
        "target": {"name": "pod-1", "uid": "uid-1"},
        "process": process,
        "pcap_path": "/tmp/capture-1.pcap",
        "log_path": "/tmp/capture-1.log",
    }]

    monkeypatch.setattr(
        "app.network_diagnostics.capture_worker.time.sleep",
        fake_sleep,
    )
    monkeypatch.setattr(
        "app.network_diagnostics.capture_worker.os.killpg",
        fake_killpg,
    )

    results = finish_capture_processes(
        running,
        duration_seconds=60,
    )

    assert events == [
        ("sleep", 60),
        ("signal", 2001, signal.SIGINT),
        ("wait", 10),
    ]

    assert results[0]["exit_code"] == 0
    assert results[0]["forced_stop"] is False


def test_finish_capture_processes_timeout(monkeypatch):
    import signal
    import subprocess
    from types import SimpleNamespace

    events = []
    wait_calls = 0

    def fake_sleep(seconds):
        events.append(("sleep", seconds))

    def fake_killpg(pid, sig):
        events.append(("signal", pid, sig))

    def fake_wait(timeout):
        nonlocal wait_calls
        wait_calls += 1

        if wait_calls == 1:
            raise subprocess.TimeoutExpired(
                cmd="tcpdump",
                timeout=timeout,
            )

        return -9

    process = SimpleNamespace(
        pid=2001,
        poll=lambda: None,
        wait=fake_wait,
    )

    running = [{
        "target": {"name": "pod-1", "uid": "uid-1"},
        "process": process,
        "pcap_path": "/tmp/capture-1.pcap",
        "log_path": "/tmp/capture-1.log",
    }]

    monkeypatch.setattr(
        "app.network_diagnostics.capture_worker.time.sleep",
        fake_sleep,
    )
    monkeypatch.setattr(
        "app.network_diagnostics.capture_worker.os.killpg",
        fake_killpg,
    )

    results = finish_capture_processes(
        running,
        duration_seconds=60,
        grace_seconds=10,
    )

    assert events == [
        ("sleep", 60),
        ("signal", 2001, signal.SIGINT),
        ("signal", 2001, signal.SIGKILL),
    ]

    assert results[0]["forced_stop"] is True
    assert results[0]["exit_code"] == -9
    assert wait_calls == 2


def test_inspect_pcap_empty(tmp_path):
    pcap = tmp_path / "empty.pcap"

    header = struct.pack(
        "<IHHIIII",
        0xA1B2C3D4, 2, 4, 0, 0, 65535, 1
    )
    pcap.write_bytes(header)

    result = inspect_pcap_file(str(pcap))

    assert result == {
        "status": "empty",
        "packet_count": 0,
    }


def test_inspect_pcap_with_packets(tmp_path):
    pcap = tmp_path / "capture.pcap"

    header = struct.pack(
        "<IHHIIII",
        0xA1B2C3D4, 2, 4, 0, 0, 65535, 1
    )
    packet = struct.pack(
        "<IIII", 0, 0, 4, 4
    ) + b"test"

    pcap.write_bytes(header + packet)

    result = inspect_pcap_file(str(pcap))

    assert result["status"] == "captured"
    assert result["packet_count"] == 1


def test_inspect_pcap_invalid(tmp_path):
    pcap = tmp_path / "invalid.pcap"
    pcap.write_bytes(b"not a valid pcap file")

    assert inspect_pcap_file(str(pcap))["status"] == "invalid"


def test_inspect_pcap_truncated_packet(tmp_path):
    pcap = tmp_path / "truncated.pcap"

    header = struct.pack(
        "<IHHIIII",
        0xA1B2C3D4, 2, 4, 0, 0, 65535, 1
    )
    packet = struct.pack(
        "<IIII", 0, 0, 10, 10
    ) + b"test"

    pcap.write_bytes(header + packet)

    assert inspect_pcap_file(str(pcap))["status"] == "invalid"


def test_inspect_pcap_missing(tmp_path):
    result = inspect_pcap_file(str(tmp_path / "missing.pcap"))

    assert result["status"] == "missing"


def test_summarize_preserves_interrupted_pcap(tmp_path):
    pcap = tmp_path / "capture.pcap"

    header = struct.pack(
        "<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1
    )
    packet = struct.pack("<IIII", 0, 0, 4, 4) + b"test"
    pcap.write_bytes(header + packet)

    results = [{
        "target": {"name": "pod-1"},
        "pcap_path": str(pcap),
        "exit_code": -9,
        "forced_stop": True,
    }]

    summary = summarize_capture_results(results)[0]

    assert summary["process_status"] == "interrupted"
    assert summary["pcap_status"] == "captured"
    assert summary["packet_count"] == 1
    assert summary["include_in_zip"] is True


def test_summarize_preserves_empty_pcap(tmp_path):
    pcap = tmp_path / "empty.pcap"

    header = struct.pack(
        "<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1
    )
    pcap.write_bytes(header)

    results = [{
        "target": {"name": "pod-2"},
        "pcap_path": str(pcap),
        "exit_code": 0,
        "forced_stop": False,
    }]

    summary = summarize_capture_results(results)[0]

    assert summary["process_status"] == "completed"
    assert summary["pcap_status"] == "empty"
    assert summary["include_in_zip"] is True


def test_summarize_excludes_missing_pcap(tmp_path):
    results = [{
        "target": {"name": "pod-3"},
        "pcap_path": str(tmp_path / "missing.pcap"),
        "exit_code": 1,
        "forced_stop": False,
    }]

    summary = summarize_capture_results(results)[0]

    assert summary["process_status"] == "failed"
    assert summary["pcap_status"] == "missing"
    assert summary["include_in_zip"] is False


def test_run_capture_session_creates_manifest(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    targets = [
        {"name": "pod-1", "namespace": "iomt-dev-1", "uid": "uid-1"},
        {"name": "pod-2", "namespace": "iomt-dev-1", "uid": "uid-2"},
    ]

    def fake_resolver(uid, namespace):
        if uid == "uid-2":
            raise ValueError("No Ready sandbox found")
        return 13314

    def fake_popen(command, **kwargs):
        # Simulate tcpdump producing a valid PCAP with one packet.
        header = struct.pack(
            "<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1
        )
        packet = struct.pack(
            "<IIII", 0, 0, 4, 4
        ) + b"test"

        Path(command[-1]).write_bytes(header + packet)

        return SimpleNamespace(
            pid=2001,
            poll=lambda: 0,
            wait=lambda timeout: 0,
        )

    # Avoid actually waiting for the capture duration.
    monkeypatch.setattr(
        "app.network_diagnostics.capture_worker.time.sleep",
        lambda seconds: None,
    )

    manifest = run_capture_session(
        json.dumps(targets),
        duration_seconds=60,
        output_dir=str(tmp_path),
        resolver=fake_resolver,
        popen_factory=fake_popen,
    )

    assert manifest["targets_requested"] == 2
    assert len(manifest["captures"]) == 1
    assert len(manifest["unavailable"]) == 1

    capture = manifest["captures"][0]
    assert capture["pcap_status"] == "captured"
    assert capture["packet_count"] == 1
    assert capture["include_in_zip"] is True

    manifest_file = tmp_path / "manifest.json"
    assert manifest_file.exists()

    saved = json.loads(manifest_file.read_text())
    assert saved["captures"][0]["target"]["name"] == "pod-1"
    assert saved["unavailable"][0]["uid"] == "uid-2"

    
def test_worker_main_reads_environment(monkeypatch, tmp_path):
    targets = [
        {"name": "pod-1", "namespace": "iomt-dev-1", "uid": "uid-1"}
    ]

    received = {}

    def fake_session(raw_targets, duration_seconds, output_dir):
        received["targets"] = json.loads(raw_targets)
        received["duration"] = duration_seconds
        received["output_dir"] = output_dir

        return {
            "captures": [{"target": targets[0]}],
            "unavailable": [],
        }

    def fake_archive(capture_dir, archive_path):
        received["archive_source"] = capture_dir
        received["archive_path"] = archive_path
        return archive_path

    monkeypatch.setenv("CAPTURE_TARGETS_JSON", json.dumps(targets))
    monkeypatch.setenv("CAPTURE_DURATION_SECONDS", "60")
    monkeypatch.setenv("CAPTURE_OUTPUT_DIR", str(tmp_path))

    monkeypatch.setattr(
        worker_main,
        "run_capture_session",
        fake_session,
    )

    monkeypatch.setattr(
        worker_main,
        "create_capture_archive",
        fake_archive,
    )

    result = worker_main.main()

    assert result == 0
    assert received["targets"] == targets
    assert received["duration"] == 60
    assert received["output_dir"] == str(tmp_path)
    assert received["archive_source"] == str(tmp_path)
    assert received["archive_path"] == str(tmp_path / "job-artifacts.zip")


def test_worker_main_rejects_missing_targets(monkeypatch):
    monkeypatch.delenv("CAPTURE_TARGETS_JSON", raising=False)

    assert worker_main.main() == 2


def test_build_netshoot_job_worker_configuration():
    job = build_netshoot_job(
        "test-node",
        targets=[],
        duration_seconds=60,
    )

    pod = job.spec.template.spec
    container = pod.containers[0]

    assert pod.host_pid is True
    assert pod.automount_service_account_token is False
    assert container.image == "iomt-netshoot-worker:dev"
    assert container.command is None

    env = {item.name: item.value for item in container.env}
    assert env["CAPTURE_DURATION_SECONDS"] == "60"
    assert env["CAPTURE_OUTPUT_DIR"] == "/captures"

    assert container.security_context.privileged is True
    assert any(
        volume.host_path is not None
        and volume.host_path.path == CRI_SOCKET_PATH
        for volume in pod.volumes
    )
    assert job.spec.active_deadline_seconds == 360


def test_create_capture_archive(tmp_path):
    import zipfile

    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()

    (capture_dir / "capture-1.pcap").write_bytes(b"example pcap")
    (capture_dir / "capture-1.log").write_text("50 packets captured")
    (capture_dir / "capture-2.log").write_text("capture failed")

    manifest = {
        "captures": [
            {
                "pcap_file": "capture-1.pcap",
                "log_file": "capture-1.log",
                "include_in_zip": True,
            },
            {
                "pcap_file": None,
                "log_file": "capture-2.log",
                "include_in_zip": False,
            },
        ]
    }

    (capture_dir / "manifest.json").write_text(
        json.dumps(manifest)
    )

    output = tmp_path / "job-artifacts.zip"

    result = create_capture_archive(
        str(capture_dir),
        str(output),
    )

    assert result == str(output)
    assert output.exists()

    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "capture-1.pcap",
            "capture-1.log",
            "capture-2.log",
        }


def test_create_capture_archive_missing_pcap(tmp_path):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()

    manifest = {
        "captures": [
            {
                "pcap_file": "missing.pcap",
                "log_file": "capture-1.log",
                "include_in_zip": True,
            }
        ]
    }

    (capture_dir / "manifest.json").write_text(
        json.dumps(manifest)
    )
    (capture_dir / "capture-1.log").write_text("capture log")

    with pytest.raises(FileNotFoundError):
        create_capture_archive(
            str(capture_dir),
            str(tmp_path / "job-artifacts.zip"),
        )

def test_worker_main_archive_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPTURE_TARGETS_JSON", "[]")
    monkeypatch.setenv("CAPTURE_DURATION_SECONDS", "60")
    monkeypatch.setenv("CAPTURE_OUTPUT_DIR", str(tmp_path))

    monkeypatch.setattr(
        worker_main,
        "run_capture_session",
        lambda **kwargs: {"captures": [], "unavailable": []},
    )

    def fake_archive(capture_dir, archive_path):
        raise OSError("Unable to write ZIP")

    monkeypatch.setattr(
        worker_main,
        "create_capture_archive",
        fake_archive,
    )

    assert worker_main.main() == 1


def test_upload_capture_archive_success(tmp_path):
    import hashlib
    import io
    import json

    data = b"example archive contents"
    archive = tmp_path / "job-artifacts.zip"
    archive.write_bytes(data)

    expected_hash = hashlib.sha256(data).hexdigest()

    def fake_opener(request, timeout):
        assert request.get_method() == "POST"
        assert request.data.read() == data

        return io.BytesIO(json.dumps({
            "stored": True,
            "sha256": expected_hash,
        }).encode())

    result = upload_capture_archive(
        str(archive),
        "https://example.test/api/network/artifacts",
        "test-token",
        opener=fake_opener,
    )

    assert result["stored"] is True
    assert result["sha256"] == expected_hash


def test_upload_capture_archive_retries(tmp_path):
    import urllib.error

    archive = tmp_path / "job-artifacts.zip"
    archive.write_bytes(b"example archive")

    attempts = []
    delays = []

    def failing_opener(request, timeout):
        attempts.append(1)
        raise urllib.error.URLError("Connection unavailable")

    with pytest.raises(RuntimeError):
        upload_capture_archive(
            str(archive),
            "https://example.test/api/network/artifacts",
            "test-token",
            max_attempts=3,
            opener=failing_opener,
            sleeper=delays.append,
        )

    assert len(attempts) == 3
    assert delays == [1, 2]


def test_receive_archive_and_duplicate(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "IOMT_ARTIFACT_UPLOAD_TOKEN", "test-token"
    )
    monkeypatch.setenv(
        "IOMT_ARTIFACT_STORAGE_DIR", str(tmp_path)
    )

    app = FastAPI()
    app.include_router(artifact_router)
    client = TestClient(app)

    archive_data = b"example archive data"
    digest = hashlib.sha256(archive_data).hexdigest()

    url = "/api/network/sessions/session-1/jobs/job-1/artifacts"
    headers = {
        "Authorization": "Bearer test-token",
        "X-Archive-SHA256": digest,
        "Content-Type": "application/zip",
    }

    first = client.post(
        url, content=archive_data, headers=headers
    )

    assert first.status_code == 200
    assert first.json()["stored"] is True
    assert first.json()["duplicate"] is False

    stored = tmp_path / "session-1" / "job-1.zip"
    assert stored.read_bytes() == archive_data

    # Simulate a retry after the acknowledgement was lost.
    second = client.post(
        url, content=archive_data, headers=headers
    )

    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert stored.read_bytes() == archive_data



def test_receive_archive_conflicting_upload(tmp_path, monkeypatch):
    monkeypatch.setenv("IOMT_ARTIFACT_UPLOAD_TOKEN", "test-token")
    monkeypatch.setenv("IOMT_ARTIFACT_STORAGE_DIR", str(tmp_path))

    app = FastAPI()
    app.include_router(artifact_router)
    client = TestClient(app)

    url = "/api/network/sessions/session-1/jobs/job-1/artifacts"

    def upload(data):
        return client.post(
            url,
            content=data,
            headers={
                "Authorization": "Bearer test-token",
                "X-Archive-SHA256": hashlib.sha256(data).hexdigest(),
            },
        )

    first = upload(b"original archive")
    second = upload(b"different archive")

    assert first.status_code == 200
    assert second.status_code == 409

    stored = tmp_path / "session-1" / "job-1.zip"
    assert stored.read_bytes() == b"original archive"


def test_receive_archive_invalid_checksum(tmp_path, monkeypatch):
    monkeypatch.setenv("IOMT_ARTIFACT_UPLOAD_TOKEN", "test-token")
    monkeypatch.setenv("IOMT_ARTIFACT_STORAGE_DIR", str(tmp_path))

    app = FastAPI()
    app.include_router(artifact_router)
    client = TestClient(app)

    response = client.post(
        "/api/network/sessions/session-1/jobs/job-1/artifacts",
        content=b"corrupted archive",
        headers={
            "Authorization": "Bearer test-token",
            "X-Archive-SHA256": "0" * 64,
        },
    )

    assert response.status_code == 422
    assert not (tmp_path / "session-1" / "job-1.zip").exists()


def test_receive_archive_unauthorized(tmp_path, monkeypatch):
    monkeypatch.setenv("IOMT_ARTIFACT_UPLOAD_TOKEN", "test-token")
    monkeypatch.setenv("IOMT_ARTIFACT_STORAGE_DIR", str(tmp_path))

    app = FastAPI()
    app.include_router(artifact_router)
    client = TestClient(app)

    data = b"example archive"

    response = client.post(
        "/api/network/sessions/session-1/jobs/job-1/artifacts",
        content=data,
        headers={
            "X-Archive-SHA256": hashlib.sha256(data).hexdigest(),
        },
    )

    assert response.status_code == 401
    assert not (tmp_path / "session-1" / "job-1.zip").exists()

def test_schedule_capture_jobs_forwards_duration():
    """Verify requested duration reaches the Kubernetes Job."""

    mock_core = Mock()
    mock_batch = Mock()

    mock_core.list_namespaced_pod.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(
                    name="http-test-1",
                    uid="uid-1",
                    deletion_timestamp=None,
                ),
                spec=SimpleNamespace(
                    node_name="test-node",
                    host_network=False,
                ),
                status=SimpleNamespace(
                    phase="Running",
                    pod_ip="10.0.0.1",
                ),
            )
        ]
    )

    mock_batch.create_namespaced_job.return_value.metadata.name = "test-job"

    schedule_capture_jobs(
        core_api=mock_core,
        batch_api=mock_batch,
        namespaces=["iomt-dev-1"],
        duration_seconds=120,
    )

    job = mock_batch.create_namespaced_job.call_args.kwargs["body"]
    container = job.spec.template.spec.containers[0]

    env = {item.name: item.value for item in container.env}

    assert env["CAPTURE_DURATION_SECONDS"] == "120"

def test_schedule_capture_jobs_rolls_back_on_failure():
    """Previously created Jobs are deleted if later scheduling fails."""

    mock_core = Mock()
    mock_batch = Mock()

    def make_pod(name, node):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                name=name,
                uid=f"uid-{name}",
                deletion_timestamp=None,
            ),
            spec=SimpleNamespace(
                node_name=node,
                host_network=False,
            ),
            status=SimpleNamespace(
                phase="Running",
                pod_ip="10.0.0.1",
            ),
        )

    mock_core.list_namespaced_pod.return_value = SimpleNamespace(
        items=[
            make_pod("pod-a", "node-A"),
            make_pod("pod-b", "node-B"),
        ]
    )

    mock_batch.create_namespaced_job.side_effect = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="job-A")
        ),
        ApiException(status=503, reason="Scheduling failed"),
    ]

    with pytest.raises(ApiException) as exc:
        schedule_capture_jobs(
            core_api=mock_core,
            batch_api=mock_batch,
            namespaces=["iomt-dev-1"],
            duration_seconds=30,
        )

    assert exc.value.status == 503

    mock_batch.delete_namespaced_job.assert_called_once_with(
        name="job-A",
        namespace="iomt-integration",
        propagation_policy="Foreground",
        _request_timeout=10,
    )

def test_schedule_capture_jobs_reports_failed_rollback():
    """Report Job names when rollback cannot remove created Jobs."""

    mock_core = Mock()
    mock_batch = Mock()

    # Simulate Kubernetes refusing to delete the first Job.
    mock_batch.delete_namespaced_job.side_effect = ApiException(
        status=403,
        reason="Forbidden",
    )

    targets = {
        "node-A": [{"name": "pod-a"}],
        "node-B": [{"name": "pod-b"}],
    }

    with patch(
        "app.network_diagnostics.job_service.discover_targets_across_namespaces",
        return_value=targets,
    ), patch(
        "app.network_diagnostics.job_service.submit_netshoot_job",
        side_effect=[
            "job-A",
            ApiException(status=503, reason="Scheduling failed"),
        ],
    ):
        with pytest.raises(CaptureSchedulingCleanupError) as exc:
            schedule_capture_jobs(
                core_api=mock_core,
                batch_api=mock_batch,
                namespaces=["iomt-dev-1"],
                duration_seconds=30,
            )

    assert exc.value.job_names == ["job-A"]

    mock_batch.delete_namespaced_job.assert_called_once()
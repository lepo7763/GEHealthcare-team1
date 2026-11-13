import base64
import json
import zipfile
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.diagnostics.service import collect_diagnostics
from app.log_collection.progress import tracker
from app.log_collection.schemas import LogCollectionParams
from app.tshark.config import TSHARK_DIAGNOSTICS_NAMESPACE
from app.tshark.service import (
    ANALYSIS_BEGIN,
    ANALYSIS_END,
    CAPTURE_STARTED,
    PCAP_BEGIN,
    PCAP_END,
    TSharkCaptureError,
    _wait_for_capture,
    build_capture_job,
    capture_network,
)
from app.umf_rti.schemas import UmfRtiParams


ANALYSIS_CSV = (
    "frame.len,frame.protocols,ip.src,ip.dst,ipv6.src,ipv6.dst,"
    "tcp.srcport,tcp.dstport,tcp.flags.reset,"
    "tcp.analysis.retransmission,dns.flags.rcode\n"
    "64,tcp:ip,10.0.0.1,10.0.0.2,,,,,1,,\n"
)
PCAPNG = b"\x0a\x0d\x0d\x0a-test-pcapng"


def _successful_clients(logs=None):
    batch = Mock()
    batch.read_namespaced_job.side_effect = ApiException(status=404)
    batch.create_namespaced_job.return_value = None
    batch.read_namespaced_job_status.return_value = SimpleNamespace(
        status=SimpleNamespace(
            conditions=[SimpleNamespace(type="Complete", status="True")]
        )
    )

    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(name="tshark-capture-pod"),
        status=client.V1PodStatus(
            phase="Succeeded",
            container_statuses=[
                client.V1ContainerStatus(
                    name="tshark",
                    image="test-image",
                    image_id="test-image-id",
                    ready=False,
                    restart_count=0,
                    state=client.V1ContainerState(
                        terminated=client.V1ContainerStateTerminated(exit_code=0)
                    ),
                )
            ],
        ),
    )
    core = Mock()
    core.list_namespaced_pod.return_value = SimpleNamespace(items=[pod])
    core.read_namespaced_pod_log.return_value = logs or "\n".join(
        (
            CAPTURE_STARTED,
            ANALYSIS_BEGIN,
            ANALYSIS_CSV,
            ANALYSIS_END,
            PCAP_BEGIN,
            base64.b64encode(PCAPNG).decode("ascii"),
            PCAP_END,
        )
    )
    return core, batch

# Test that the capture job is properly bounded and does not use host network
def test_build_capture_job_is_bounded_and_does_not_use_host_network():
    job = build_capture_job(30, capture_id="a" * 32)
    five_minute_job = build_capture_job(300, capture_id="b" * 32)
    pod_spec = job.spec.template.spec
    capture = pod_spec.containers[0]

    assert job.metadata.namespace == TSHARK_DIAGNOSTICS_NAMESPACE
    assert job.metadata.name == "tshark-capture-" + "a" * 16
    assert capture.image
    assert capture.security_context.privileged is False
    assert capture.security_context.allow_privilege_escalation is False
    assert pod_spec.host_network is not True
    assert pod_spec.host_pid is not True
    assert pod_spec.automount_service_account_token is False
    assert job.spec.backoff_limit == 0
    assert job.spec.ttl_seconds_after_finished
    assert "-a duration:30" in capture.command[-1]
    assert "-w /captures/capture.pcapng" in capture.command[-1]
    five_minute_command = five_minute_job.spec.template.spec.containers[0].command[-1]
    assert "-a duration:300" in five_minute_command


def test_capture_network_runs_job_analyzes_packets_and_cleans_up():
    core, batch = _successful_clients()
    states = []

    result = capture_network(
        core,
        batch,
        duration=2,
        include_pcap=True,
        on_state=states.append,
    )

    assert result["status"] == "completed"
    assert result["captureState"] == "completed"
    assert result["packetsCaptured"] == result["packetsAnalyzed"] == 1
    assert result["diagnostics"][0]["count"] == 1
    assert result["pcapBytes"] == PCAPNG
    assert result["namespace"] == TSHARK_DIAGNOSTICS_NAMESPACE
    assert result["workload"].startswith("tshark-capture-")
    assert "deploying" in states
    assert "processing" in states
    batch.create_namespaced_job.assert_called_once()
    batch.delete_namespaced_job.assert_called_once()
    assert batch.delete_namespaced_job.call_args.kwargs["propagation_policy"] == "Foreground"


def test_capture_network_reports_zero_packets_as_failed_visibility():
    empty_logs = "\n".join(
        (
            CAPTURE_STARTED,
            ANALYSIS_BEGIN,
            ANALYSIS_CSV.splitlines()[0],
            ANALYSIS_END,
            PCAP_BEGIN,
            base64.b64encode(PCAPNG).decode("ascii"),
            PCAP_END,
        )
    )
    core, batch = _successful_clients(empty_logs)

    result = capture_network(core, batch, include_pcap=True)

    assert result["captureState"] == "failed"
    assert result["packetsCaptured"] == 0
    assert "network visibility is not established" in result["error"]
    assert result["pcapBytes"] == PCAPNG
    batch.delete_namespaced_job.assert_called_once()


def test_capture_network_reuses_an_existing_idempotent_job():
    core, batch = _successful_clients()
    batch.read_namespaced_job.side_effect = None
    batch.read_namespaced_job.return_value = SimpleNamespace()

    result = capture_network(core, batch, capture_id="b" * 32)

    assert result["status"] == "completed"
    batch.create_namespaced_job.assert_not_called()
    batch.delete_namespaced_job.assert_called_once_with(
        name="tshark-capture-" + "b" * 16,
        namespace=TSHARK_DIAGNOSTICS_NAMESPACE,
        propagation_policy="Foreground",
        grace_period_seconds=0,
        _request_timeout=20,
    )


def test_capture_progress_reports_elapsed_capture_seconds(monkeypatch):
    core, batch = _successful_clients()
    batch.read_namespaced_job_status.side_effect = [
        SimpleNamespace(status=SimpleNamespace(conditions=[])),
        SimpleNamespace(
            status=SimpleNamespace(
                conditions=[SimpleNamespace(type="Complete", status="True")]
            )
        ),
    ]
    now = [0.0]
    monkeypatch.setattr("app.tshark.service.time.monotonic", lambda: now[0])
    monkeypatch.setattr(
        "app.tshark.service.time.sleep",
        lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    progress = []

    pod, _ = _wait_for_capture(
        core,
        batch,
        "tshark-capture-example",
        3,
        on_state=None,
        on_progress=lambda completed, total: progress.append((completed, total)),
    )

    assert pod.metadata.name == "tshark-capture-pod"
    assert progress[0] == (0, 3)
    assert (1, 3) in progress


def test_capture_network_maps_kubernetes_permission_errors_and_cleans_up():
    core, batch = _successful_clients()
    batch.create_namespaced_job.side_effect = ApiException(
        status=403, reason="Forbidden"
    )

    with pytest.raises(TSharkCaptureError, match="Kubernetes denied") as error:
        capture_network(core, batch)

    assert error.value.status_code == 403
    batch.delete_namespaced_job.assert_not_called()


def test_capture_network_reports_image_pull_failure_and_cleans_up():
    core, batch = _successful_clients()
    pod = core.list_namespaced_pod.return_value.items[0]
    pod.status.container_statuses[0].state = client.V1ContainerState(
        waiting=client.V1ContainerStateWaiting(
            reason="ImagePullBackOff",
            message="image is not available",
        )
    )
    batch.read_namespaced_job_status.return_value.status.conditions = []

    with pytest.raises(TSharkCaptureError, match="Capture image could not be pulled"):
        capture_network(core, batch)

    batch.delete_namespaced_job.assert_called_once()


@pytest.mark.parametrize("duration", [0, 301])
def test_capture_network_rejects_duration_before_creating_a_job(duration):
    core, batch = _successful_clients()

    with pytest.raises(ValueError, match="Capture duration"):
        capture_network(core, batch, duration=duration)

    batch.create_namespaced_job.assert_not_called()


def test_diagnostics_zip_includes_tshark_analysis_and_pcap(monkeypatch):
    import app.diagnostics.service as diagnostics_service

    batch = Mock()
    result = {
        "status": "completed",
        "captureState": "completed",
        "error": None,
        "pod": "capture-pod",
        "packetsCaptured": 1,
        "packetsAnalyzed": 1,
        "pcapBytes": PCAPNG,
        "cleanupJobName": "tshark-capture-example",
        "diagnostics": [{"type": "TCP_RESET", "count": 1}],
    }
    capture_mock = Mock(return_value=result)
    monkeypatch.setattr(diagnostics_service, "capture_network", capture_mock)

    archive = collect_diagnostics(
        core=Mock(),
        batch=batch,
        services=["wireshark-tshark"],
        log_params=LogCollectionParams(),
        umf_params=UmfRtiParams(),
        tshark_duration=300,
    )
    try:
        with zipfile.ZipFile(archive) as zip_file:
            assert zip_file.read("network/tshark-capture.pcapng") == PCAPNG
            analysis = json.loads(
                zip_file.read("network/tshark-analysis.json")
            )
            manifest = json.loads(zip_file.read("manifest.json"))
    finally:
        archive.close()

    assert "pcapBytes" not in analysis
    assert capture_mock.call_args.kwargs["duration"] == 300
    assert manifest["services"][0]["status"] == "done"
    assert set(manifest["services"][0]["files"]) == {
        "network/tshark-analysis.json",
        "network/tshark-capture.pcapng",
    }
    batch.delete_namespaced_job.assert_called_once_with(
        name="tshark-capture-example",
        namespace=TSHARK_DIAGNOSTICS_NAMESPACE,
        propagation_policy="Foreground",
        grace_period_seconds=0,
        _request_timeout=20,
    )
    tracker.reset()

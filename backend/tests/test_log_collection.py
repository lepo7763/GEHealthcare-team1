import io
import json
import zipfile
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.main import app
from app.core.k8s_client import get_core_v1_api

test_client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures & Helpers to Build Realistic (and Broken) K8s Objects
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_k8s_v1():
    """
    Overrides the FastAPI K8s client dependency with a strict MagicMock.
    Automatically cleans up after each test so tests never leak state.
    """
    mock_api = MagicMock(spec=client.CoreV1Api)
    app.dependency_overrides[get_core_v1_api] = lambda: mock_api
    yield mock_api
    app.dependency_overrides.clear()


def make_pod(
    namespace="default",
    name="test-pod",
    containers=("app",),
    init_containers=(),
    ephemeral_containers=(),
    restarts=None,
):
    """Helper to build real kubernetes.client.V1Pod objects for testing."""
    restarts = restarts or {}

    def _make_statuses(names):
        if not names:
            return None
        return [
            client.V1ContainerStatus(
                name=c,
                image="busybox",
                image_id="docker://123",
                ready=True,
                restart_count=restarts.get(c, 0),
            )
            for c in names
        ]

    return client.V1Pod(
        metadata=client.V1ObjectMeta(namespace=namespace, name=name),
        spec=client.V1PodSpec(
            containers=[client.V1Container(name=c) for c in containers],
            init_containers=[client.V1Container(name=c) for c in init_containers] or None,
            ephemeral_containers=[client.V1EphemeralContainer(name=c) for c in ephemeral_containers] or None,
        ),
        status=client.V1PodStatus(
            container_statuses=_make_statuses(containers),
            init_container_statuses=_make_statuses(init_containers),
            ephemeral_container_statuses=_make_statuses(ephemeral_containers),
        ),
    )


def unzip_response(response) -> tuple[dict, dict[str, str]]:
    """
    Reads the raw response bytes, verifies it is a valid ZIP archive,
    and returns (parsed_manifest_dict, {filepath: file_text_content}).
    """
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment; filename=" in response.headers.get("content-disposition", "")

    buf = io.BytesIO(response.content)
    assert zipfile.is_zipfile(buf), "Response body is not a valid ZIP file"

    files = {}
    with zipfile.ZipFile(buf, "r") as zf:
        # Check for corrupted zip CRCs or duplicate filenames
        assert zf.testzip() is None
        names = zf.namelist()
        assert len(names) == len(set(names)), f"Duplicate files in ZIP: {names}"

        for name in names:
            files[name] = zf.read(name).decode("utf-8")

    assert "manifest.json" in files, "manifest.json is missing from the ZIP"
    manifest = json.loads(files.pop("manifest.json"))
    return manifest, files


# ---------------------------------------------------------------------------
# 1. Happy Path & Multi-Container Discovery Tests
# ---------------------------------------------------------------------------

def test_collects_logs_across_multiple_namespaces_and_container_types(mock_k8s_v1):
    """
    Verifies standard, init, and ephemeral (e.g., Netshoot) containers across
    different namespaces are all discovered and written to the right paths.
    """
    pod1 = make_pod(
        namespace="kube-system",
        name="coredns-1",
        containers=["coredns"],
        init_containers=["init-sysctl"],
    )
    pod2 = make_pod(
        namespace="iomt-hub",
        name="patient-monitor",
        containers=["monitor-api", "sidecar-proxy"],
        ephemeral_containers=["netshoot-debug"],
    )
    mock_k8s_v1.list_pod_for_all_namespaces.return_value = client.V1PodList(items=[pod1, pod2])

    # Return unique log text based on which container was requested
    def fake_read_log(name, namespace, container, **kwargs):
        return f"log for {namespace}/{name}/{container}"

    mock_k8s_v1.read_namespaced_pod_log.side_effect = fake_read_log

    response = test_client.get("/api/logs/zip?throttle_delay_ms=0")
    manifest, files = unzip_response(response)

    assert manifest["total_logs_collected"] == 5
    assert manifest["errors"] == []
    assert set(files.keys()) == {
        "logs/kube-system/coredns-1/coredns.log",
        "logs/kube-system/coredns-1/init-sysctl.log",
        "logs/iomt-hub/patient-monitor/monitor-api.log",
        "logs/iomt-hub/patient-monitor/sidecar-proxy.log",
        "logs/iomt-hub/patient-monitor/netshoot-debug.log",
    }
    assert files["logs/iomt-hub/patient-monitor/netshoot-debug.log"] == (
        "log for iomt-hub/patient-monitor/netshoot-debug"
    )


def test_empty_log_output_when_k8s_returns_none(mock_k8s_v1):
    """
    K8s API returns None (not "") when a silent container has produced 0 bytes of stdout.
    Ensure we write an empty 0-byte file rather(than crashing zipfile.writestr).
    """
    pod = make_pod(namespace="default", name="silent-pod", containers=["silent-app"])
    mock_k8s_v1.list_pod_for_all_namespaces.return_value = client.V1PodList(items=[pod])
    mock_k8s_v1.read_namespaced_pod_log.return_value = None

    response = test_client.get("/api/logs/zip?throttle_delay_ms=0")
    manifest, files = unzip_response(response)

    assert manifest["total_logs_collected"] == 1
    assert files["logs/default/silent-pod/silent-app.log"] == ""


# ---------------------------------------------------------------------------
# 2. Crashed Containers & Previous Logs Tests
# ---------------------------------------------------------------------------

def test_fetches_previous_logs_only_when_restart_count_positive(mock_k8s_v1):
    """
    If a pod has 2 containers, one with restart_count=3 and one with restart_count=0,
    only the restarted container should request `previous=True`.
    """
    pod = make_pod(
        namespace="iomt",
        name="flaky-pod",
        containers=["stable", "crashing"],
        restarts={"stable": 0, "crashing": 3},
    )
    mock_k8s_v1.list_pod_for_all_namespaces.return_value = client.V1PodList(items=[pod])

    def fake_read_log(name, namespace, container, previous=False, **kwargs):
        return f"{container} (previous={previous})"

    mock_k8s_v1.read_namespaced_pod_log.side_effect = fake_read_log

    response = test_client.get("/api/logs/zip?throttle_delay_ms=0")
    manifest, files = unzip_response(response)

    assert set(files.keys()) == {
        "logs/iomt/flaky-pod/stable.log",
        "logs/iomt/flaky-pod/crashing.log",
        "logs/iomt/flaky-pod/crashing_previous.log",
    }
    assert files["logs/iomt/flaky-pod/crashing_previous.log"] == "crashing (previous=True)"


def test_crashloopbackoff_where_current_fails_but_previous_succeeds(mock_k8s_v1):
    """
    REAL-WORLD K8S SCENARIO:
    A container is currently in Waiting/CrashLoopBackOff state, so `previous=False`
    throws 400 Bad Request, while `previous=True` succeeds and holds the crash stacktrace!
    Both the error (for current) and the file (for previous) must be preserved.
    """
    pod = make_pod(
        namespace="iomt",
        name="crashloop-pod",
        containers=["backend"],
        restarts={"backend": 5},
    )
    mock_k8s_v1.list_pod_for_all_namespaces.return_value = client.V1PodList(items=[pod])

    def fake_read_log(name, namespace, container, previous=False, **kwargs):
        if not previous:
            raise ApiException(status=400, reason="ContainerCreating or CrashLoopBackOff")
        return "FATAL: NullPointerException before crash"

    mock_k8s_v1.read_namespaced_pod_log.side_effect = fake_read_log

    response = test_client.get("/api/logs/zip?throttle_delay_ms=0")
    manifest, files = unzip_response(response)

    # Current log failed and is recorded in errors:
    assert len(manifest["errors"]) == 1
    assert manifest["errors"][0]["status"] == 400
    assert "logs/iomt/crashloop-pod/backend.log" not in files

    # Previous log succeeded and was still saved!
    assert "logs/iomt/crashloop-pod/backend_previous.log" in files
    assert files["logs/iomt/crashloop-pod/backend_previous.log"] == "FATAL: NullPointerException before crash"


def test_rotated_out_previous_log_does_not_pollute_manifest_errors(mock_k8s_v1):
    """
    If `restart_count > 0` from a crash 2 weeks ago, kubelet may have already garbage-collected
    the previous log file (404/400). That shouldn't be flagged as a collection failure if current logs work.
    """
    pod = make_pod(namespace="iomt", name="old-restart", containers=["app"], restarts={"app": 1})
    mock_k8s_v1.list_pod_for_all_namespaces.return_value = client.V1PodList(items=[pod])

    def fake_read_log(name, namespace, container, previous=False, **kwargs):
        if previous:
            raise ApiException(status=400, reason="previous terminated container not found")
        return "current healthy log"

    mock_k8s_v1.read_namespaced_pod_log.side_effect = fake_read_log

    response = test_client.get("/api/logs/zip?throttle_delay_ms=0")
    manifest, files = unzip_response(response)

    assert manifest["errors"] == []
    assert list(files.keys()) == ["logs/iomt/old-restart/app.log"]


# ---------------------------------------------------------------------------
# 3. Partial Results & Failure Resilience Tests
# ---------------------------------------------------------------------------

def test_preserves_partial_results_when_one_pod_is_pending(mock_k8s_v1):
    """
    Requirement: If a diagnostic run fails midway, preserve partial results.
    If Pod 1 fails with 400 (Pending) and Pod 2 fails with a socket timeout, Pod 3 must still be collected.
    """
    pods = [
        make_pod(namespace="ns1", name="pending-pod", containers=["c1"]),
        make_pod(namespace="ns1", name="unreachable-node-pod", containers=["c2"]),
        make_pod(namespace="ns1", name="healthy-pod", containers=["c3"]),
    ]
    mock_k8s_v1.list_pod_for_all_namespaces.return_value = client.V1PodList(items=pods)

    def fake_read_log(name, namespace, container, **kwargs):
        if name == "pending-pod":
            raise ApiException(status=400, reason="ContainerCreating")
        if name == "unreachable-node-pod":
            raise TimeoutError("Kubelet connection timed out after 15s")
        return "Healthy container output"

    mock_k8s_v1.read_namespaced_pod_log.side_effect = fake_read_log

    response = test_client.get("/api/logs/zip?throttle_delay_ms=0")
    manifest, files = unzip_response(response)

    # Healthy pod succeeded
    assert manifest["total_logs_collected"] == 1
    assert files["logs/ns1/healthy-pod/c3.log"] == "Healthy container output"

    # Both failures are recorded accurately in manifest.json
    assert len(manifest["errors"]) == 2
    reasons = {err["pod"]: err["reason"] for err in manifest["errors"]}
    assert reasons["pending-pod"] == "ContainerCreating"
    assert "Kubelet connection timed out" in reasons["unreachable-node-pod"]


def test_cluster_unreachable_returns_503_instead_of_empty_zip(mock_k8s_v1):
    """
    If the cluster is disconnected (No route to host) or blocks listing pods,
    fail fast with 503 Service Unavailable instead of returning a fake 200 OK zip.
    """
    mock_k8s_v1.list_pod_for_all_namespaces.side_effect = Exception(
        "[Errno 113] No route to host"
    )

    response = test_client.get("/api/logs/zip?throttle_delay_ms=0")

    assert response.status_code == 503
    assert "No route to host" in response.json()["detail"]


def test_handles_malformed_k8s_pod_objects_without_crashing(mock_k8s_v1):
    """
    Defensive test against None metadata, None spec, or None status from K8s SDK.
    """
    broken_pods = [
        client.V1Pod(metadata=None, spec=None, status=None),
        client.V1Pod(metadata=client.V1ObjectMeta(name=None, namespace="default"), spec=None),
        client.V1Pod(metadata=client.V1ObjectMeta(name="no-spec", namespace="default"), spec=None),
        make_pod(namespace="default", name="valid-pod", containers=["app"]),
    ]
    mock_k8s_v1.list_pod_for_all_namespaces.return_value = client.V1PodList(items=broken_pods)
    mock_k8s_v1.read_namespaced_pod_log.return_value = "works"

    response = test_client.get("/api/logs/zip?throttle_delay_ms=0")
    manifest, files = unzip_response(response)

    assert manifest["total_logs_collected"] == 1
    assert "logs/default/valid-pod/app.log" in files


# ---------------------------------------------------------------------------
# 4. Query Parameter Forwarding & Validation Tests
# ---------------------------------------------------------------------------

def test_query_params_are_forwarded_to_k8s_sdk(mock_k8s_v1):
    """
    Verifies custom max_bytes_per_container, tail_lines, and include_previous=False
    actually reach the Kubernetes client call.
    """
    pod = make_pod(namespace="default", name="pod-1", containers=["app"], restarts={"app": 2})
    mock_k8s_v1.list_pod_for_all_namespaces.return_value = client.V1PodList(items=[pod])
    mock_k8s_v1.read_namespaced_pod_log.return_value = "line 1"

    response = test_client.get(
        "/api/logs/zip?max_bytes_per_container=1024&tail_lines=50&include_previous=false&throttle_delay_ms=0"
    )
    assert response.status_code == 200

    # Because include_previous=false, read_namespaced_pod_log should only be called ONCE (not twice)
    mock_k8s_v1.read_namespaced_pod_log.assert_called_once_with(
        name="pod-1",
        namespace="default",
        container="app",
        previous=False,
        limit_bytes=1024,
        tail_lines=50,
        timestamps=True,
        _request_timeout=15,
    )


@pytest.mark.parametrize(
    "bad_query",
    [
        "max_bytes_per_container=0",
        "max_bytes_per_container=-100",
        "tail_lines=0",
        "throttle_delay_ms=-1",
        "throttle_delay_ms=10000",
    ],
)
def test_invalid_query_parameters_return_422(mock_k8s_v1, bad_query):
    """Verifies Pydantic boundary constraints reject bad inputs before touching K8s."""
    response = test_client.get(f"/api/logs/zip?{bad_query}")
    assert response.status_code == 422

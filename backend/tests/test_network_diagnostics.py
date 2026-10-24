
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest
from fastapi.testclient import TestClient
from kubernetes.client.exceptions import ApiException
from pydantic import ValidationError
from fastapi import HTTPException
from unittest.mock import patch

from app.network_diagnostics.service import validate_capture_target
from app.network_diagnostics.service import check_netshoot_tool
from app.network_diagnostics.service import netshoot_is_running
from app.network_diagnostics.service import netshoot_is_attached
from app.network_diagnostics.service import get_netshoot_state
from app.network_diagnostics.service import build_netshoot_container
from app.network_diagnostics.service import attach_netshoot
from app.network_diagnostics.service import wait_for_netshoot
from app.network_diagnostics.service import attach_netshoot_and_wait
from app.network_diagnostics.service import ensure_netshoot_ready


from app.network_diagnostics.schemas import CaptureRequest

from app.main import app
from app.core.k8s_client import get_core_v1_api


@pytest.fixture
def mock_k8s():
    # Create a fake Kubernetes API client.
    fake_client = Mock()

    # Replace the real Kubernetes dependency with our fake client.
    app.dependency_overrides[get_core_v1_api] = lambda: fake_client

    yield fake_client

    # Restore the original dependency after each test.
    app.dependency_overrides.pop(get_core_v1_api, None)


def make_pod(name, status, ip):
    # Construct a simulated Kubernetes pod object.
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        status=SimpleNamespace(phase=status, pod_ip=ip),
    )


def test_list_pods_success(mock_k8s):
    mock_k8s.list_namespaced_pod.return_value = SimpleNamespace(
        items=[
            make_pod("netshoot", "Running", "100.64.64.176"),
            make_pod("http-test", "Running", "100.64.64.178"),
        ]
    )

    response = TestClient(app).get("/api/network/pods")

    assert response.status_code == 200
    assert response.json() == {
        "namespace": "iomt-dev-1",
        "pods": [
            {
                "name": "netshoot",
                "status": "Running",
                "ip": "100.64.64.176",
            },
            {
                "name": "http-test",
                "status": "Running",
                "ip": "100.64.64.178",
            },
        ],
    }

    mock_k8s.list_namespaced_pod.assert_called_once_with(
        namespace="iomt-dev-1",
        _request_timeout=10,
    )


def test_list_pods_empty(mock_k8s):
    mock_k8s.list_namespaced_pod.return_value = SimpleNamespace(items=[])

    response = TestClient(app).get("/api/network/pods")

    assert response.status_code == 200
    assert response.json() == {
        "namespace": "iomt-dev-1",
        "pods": [],
    }


def test_list_pods_forbidden(mock_k8s):
    mock_k8s.list_namespaced_pod.side_effect = ApiException(
        status=403,
        reason="Forbidden",
    )

    response = TestClient(app).get("/api/network/pods")

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Not authorized to list Kubernetes pods"
    )



def test_list_pods_unavailable(mock_k8s):
    mock_k8s.list_namespaced_pod.side_effect = ApiException(
        status=503,
        reason="Service Unavailable",
    )

    response = TestClient(app).get("/api/network/pods")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Unable to retrieve Kubernetes pods"
    )

def test_capture_request_default_duration():
    request = CaptureRequest(pod_name="http-test")

    assert request.pod_name == "http-test"
    assert request.duration_seconds == 10


@pytest.mark.parametrize("duration", [0, -5, 31, 120])
def test_capture_request_invalid_duration(duration):
    with pytest.raises(ValidationError):
        CaptureRequest(
            pod_name="http-test",
            duration_seconds=duration
        )


def test_capture_request_valid_duration():
    request = CaptureRequest(
        pod_name="http-test",
        duration_seconds=30
    )

    assert request.duration_seconds == 30

def test_capture_target_running(mock_k8s):
    fake_pod = SimpleNamespace(
        status = SimpleNamespace(
            phase = "Running",
            pod_ip = "10.0.0.5"
        )
    )

    mock_k8s.read_namespaced_pod.return_value = fake_pod
    result = validate_capture_target(
        mock_k8s,
        pod_name = "http-test",
        namespace = "iomt-dev-1"
    )

    assert result.name == "http-test"
    assert result.status == "Running"
    assert result.ip == "10.0.0.5"

    mock_k8s.read_namespaced_pod.assert_called_once_with(
        name = "http-test",
        namespace = "iomt-dev-1",
        _request_timeout = 10
    )

def test_capture_target_not_found(mock_k8s):
    mock_k8s.read_namespaced_pod.side_effect = ApiException(
        status = 404,
        reason = "not found"
    )

    with pytest.raises(HTTPException) as exc:
        validate_capture_target(
            mock_k8s,
            pod_name = "missing-pod",
            namespace = "iomt-dev-1"
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Target pod not found"

def test_capture_target_not_running(mock_k8s):
    fake_pod = SimpleNamespace(
        status = SimpleNamespace(
            phase = "Pending",
            pid_ip = None
        )
    )

    mock_k8s.read_namespaced_pod.return_value = fake_pod

    with pytest.raises(HTTPException) as exc:
        validate_capture_target(
            mock_k8s,
            pod_name = "http-test",
            namespace = "iomt-dev-1"
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Target pod isn't running"

def test_capture_validation_endpoint(mock_k8s):
    fake_pod = SimpleNamespace(
        status = SimpleNamespace(
            phase = "Running",  
            pod_ip = "10.0.0.5"
        )
    )

    mock_k8s.read_namespaced_pod.return_value = fake_pod

    response = TestClient(app).post(
        "/api/network/captures/validate",
        json = {
            "pod_name": "http-test",
            "duration_seconds": 10
        }
    )

    assert response.status_code == 200
    assert response.json() == {
        "name": "http-test",
        "status": "Running",
        "ip": "10.0.0.5"
    }

@pytest.mark.parametrize("request_body", [
    {"pod_name": "http-test", "duration_seconds": 120},
    {"pod_name": "http-test", "duration_seconds": 0},
    {"pod_name": "", "duration_seconds": 10},
    {"pod_name": "http-test", "duration_seconds": "10"},
])
def test_capture_validation_invalid_request(mock_k8s, request_body):
    response = TestClient(app).post(
        "/api/network/captures/validate",
        json=request_body
    )

    assert response.status_code == 422
    mock_k8s.read_namespaced_pod.assert_not_called()


def test_check_netshoot_tool(mock_k8s):
    fake_pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            phase="Running",
            pod_ip="10.0.0.5",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=SimpleNamespace()
                    )
                )
            ]
        )
    )

    mock_k8s.read_namespaced_pod.return_value = fake_pod

    with patch(
        "app.network_diagnostics.service.stream",
        return_value="tcpdump version 4.99"
    ) as mock_stream:

        result = check_netshoot_tool(
            mock_k8s,
            pod_name="http-test",
            namespace="iomt-dev-1"
        )

        assert result == "tcpdump version 4.99"

        mock_stream.assert_called_once_with(
            mock_k8s.connect_post_namespaced_pod_exec,
            "http-test",
            "iomt-dev-1",
            container="netshoot-capture",
            command=["tcpdump", "--version"],
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _request_timeout=10
        )

    
def test_check_netshoot_tool_forbidden(mock_k8s):
    fake_pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            phase="Running",
            pod_ip="10.0.0.5",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=SimpleNamespace()
                    )
                )
            ]
        )
    )

    mock_k8s.read_namespaced_pod.return_value = fake_pod

    with patch(
        "app.network_diagnostics.service.stream",
        side_effect=ApiException(
            status=403,
            reason="Forbidden"
        )
    ):
        with pytest.raises(HTTPException) as exc:
            check_netshoot_tool(
                mock_k8s,
                pod_name="http-test",
                namespace="iomt-dev-1"
            )

    assert exc.value.status_code == 403
    assert exc.value.detail == (
        "Not authorized to execute diagnostics"
    )


def test_netshoot_running():
    pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=SimpleNamespace()
                    )
                )
            ]
        )
    )

    assert netshoot_is_running(pod) is True
    assert netshoot_is_attached(pod) is True
    assert get_netshoot_state(pod) == "running"


def test_netshoot_not_attached():
    pod = SimpleNamespace(
        spec=SimpleNamespace(ephemeral_containers=[]),
        status=SimpleNamespace(ephemeral_container_statuses=[])
    )

    assert netshoot_is_running(pod) is False
    assert netshoot_is_attached(pod) is False
    assert get_netshoot_state(pod) == "missing"

def test_netshoot_terminated():
    pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=None,
                        terminated=SimpleNamespace(exit_code=0)
                    )
                )
            ]
        )
    )

    assert netshoot_is_running(pod) is False
    assert netshoot_is_attached(pod) is True
    assert get_netshoot_state(pod) == "terminated"

def test_netshoot_waiting():
    pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=None,
                        waiting=SimpleNamespace(
                            reason="ContainerCreating"
                        ),
                        terminated=None
                    )
                )
            ]
        )
    )

    assert netshoot_is_attached(pod) is True
    assert netshoot_is_running(pod) is False
    assert get_netshoot_state(pod) == "not_ready"

def test_check_netshoot_tool_missing(mock_k8s):
    fake_pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[]
        ),
        status=SimpleNamespace(
            phase="Running",
            pod_ip="10.0.0.5",
            ephemeral_container_statuses=[]
        )
    )

    mock_k8s.read_namespaced_pod.return_value = fake_pod

    with patch("app.network_diagnostics.service.stream") as mock_stream:
        with pytest.raises(HTTPException) as exc:
            check_netshoot_tool(
                mock_k8s,
                pod_name = "http-test",
                namespace = "iomt-dev-1"
            )

        assert exc.value.status_code == 409
        assert exc.value.detail == "Netshoot container is missing"

        mock_stream.assert_not_called()

def test_build_netshoot_container():
    fake_pod = SimpleNamespace(
        spec = SimpleNamespace(
            containers = [
                SimpleNamespace(name = "http-server")
            ],
            ephemeral_containers = []
        ),
        status = SimpleNamespace(
            ephemeral_container_statuses = []
        )
    )

    result = build_netshoot_container(fake_pod)

    assert result["name"] == "netshoot-capture"
    assert result["targetContainerName"] == "http-server"
    assert result["imagePullPolicy"] == "Never"
    assert result["command"] == [
        "/bin/sh",
        "-c",
        "while true; do sleep 3600; done"
    ]
    assert result["image"] == (
    "us-artifactory.apps.ge-healthcare.net/"
    "docker-axone-all/nicolaka/netshoot:v0.16"
    )


def test_build_netshoot_container_already_attached():
    fake_pod = SimpleNamespace(
        spec=SimpleNamespace(
            containers=[
                SimpleNamespace(name="http-server")
            ],
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=SimpleNamespace()
                    )
                )
            ]
        )
    )

    with pytest.raises(HTTPException) as exc:
        build_netshoot_container(fake_pod)

    assert exc.value.status_code == 409
    assert exc.value.detail == (
        "Netshoot container is already running"
    )

def test_attach_netshoot(mock_k8s):
    fake_pod = SimpleNamespace(
        spec = SimpleNamespace(
            containers = [
                SimpleNamespace(name = "http-server")
            ],
            ephemeral_containers = []
        ),
        status = SimpleNamespace(
            phase = "Running",
            pod_ip = "10.0.0.5",
            ephemeral_container_statuses = []
        )
    )

    mock_k8s.read_namespaced_pod.return_value = fake_pod

    result = attach_netshoot(
        mock_k8s,
        pod_name = "http-test",
        namespace = "iomt-dev-1"
    )

    assert result == "netshoot-capture"

    mock_k8s.patch_namespaced_pod_ephemeralcontainers.assert_called_once()

    call_args = (
        mock_k8s.patch_namespaced_pod_ephemeralcontainers.call_args.kwargs
    )

    assert call_args["name"] == "http-test"
    assert call_args["namespace"] == "iomt-dev-1"

    container = call_args["body"]["spec"]["ephemeralContainers"][0]

    assert container["name"] == "netshoot-capture"
    assert container["targetContainerName"] == "http-server"


def test_wait_for_netshoot_becomes_ready(mock_k8s):
    waiting_pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            phase="Running",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=None,
                        waiting=SimpleNamespace()
                    )
                )
            ]
        )
    )

    running_pod = SimpleNamespace(
        spec=waiting_pod.spec,
        status=SimpleNamespace(
            phase="Running",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=SimpleNamespace()
                    )
                )
            ]
        )
    )

    mock_k8s.read_namespaced_pod.side_effect = [
        waiting_pod,
        running_pod
    ]

    with patch("app.network_diagnostics.service.time.sleep") as mock_sleep:
        result = wait_for_netshoot(
            mock_k8s,
            pod_name="http-test",
            namespace="iomt-dev-1"
        )

    assert result == "netshoot-capture"
    assert mock_k8s.read_namespaced_pod.call_count == 2
    mock_sleep.assert_called_once_with(1.0)


def test_wait_for_netshoot_timeout(mock_k8s):
    waiting_pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            phase="Running",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=None,
                        waiting=SimpleNamespace(
                            reason="ContainerCreating"
                        ),
                        terminated=None
                    )
                )
            ]
        )
    )

    mock_k8s.read_namespaced_pod.return_value = waiting_pod

    with patch("app.network_diagnostics.service.time.sleep") as mock_sleep:
        with pytest.raises(HTTPException) as exc:
            wait_for_netshoot(
                mock_k8s,
                pod_name="http-test",
                namespace="iomt-dev-1",
                max_attempts=3,
                retry_interval=1.0
            )

    assert exc.value.status_code == 503
    assert exc.value.detail == "Netshoot did not become ready"

    assert mock_k8s.read_namespaced_pod.call_count == 3
    assert mock_sleep.call_count == 2



def test_attach_netshoot_and_wait(mock_k8s):
    missing_pod = SimpleNamespace(
        spec=SimpleNamespace(
            containers=[
                SimpleNamespace(name="http-server")
            ],
            ephemeral_containers=[]
        ),
        status=SimpleNamespace(
            phase="Running",
            ephemeral_container_statuses=[]
        )
    )

    waiting_pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            phase="Running",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=None,
                        waiting=SimpleNamespace()
                    )
                )
            ]
        )
    )

    running_pod = SimpleNamespace(
        spec=waiting_pod.spec,
        status=SimpleNamespace(
            phase="Running",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=SimpleNamespace()
                    )
                )
            ]
        )
    )

    mock_k8s.read_namespaced_pod.side_effect = [
        missing_pod,
        waiting_pod,
        running_pod
    ]

    with patch("app.network_diagnostics.service.time.sleep"):
        result = attach_netshoot_and_wait(
            mock_k8s,
            pod_name="http-test",
            namespace="iomt-dev-1"
        )

    assert result == "netshoot-capture"
    assert mock_k8s.read_namespaced_pod.call_count == 3

    mock_k8s.patch_namespaced_pod_ephemeralcontainers.assert_called_once()


def test_ensure_netshoot_already_running(mock_k8s):
    fake_pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            phase="Running",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=SimpleNamespace()
                    )
                )
            ]
        )
    )

    mock_k8s.read_namespaced_pod.return_value = fake_pod

    result = ensure_netshoot_ready(
        mock_k8s,
        pod_name="http-test",
        namespace="iomt-dev-1"
    )

    assert result == "netshoot-capture"

    mock_k8s.patch_namespaced_pod_ephemeralcontainers.assert_not_called()


def test_ensure_netshoot_waiting(mock_k8s):
    waiting_pod = SimpleNamespace(
        spec=SimpleNamespace(
            ephemeral_containers=[
                SimpleNamespace(name="netshoot-capture")
            ]
        ),
        status=SimpleNamespace(
            phase="Running",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=None,
                        waiting=SimpleNamespace()
                    )
                )
            ]
        )
    )

    running_pod = SimpleNamespace(
        spec=waiting_pod.spec,
        status=SimpleNamespace(
            phase="Running",
            ephemeral_container_statuses=[
                SimpleNamespace(
                    name="netshoot-capture",
                    state=SimpleNamespace(
                        running=SimpleNamespace()
                    )
                )
            ]
        )
    )

    mock_k8s.read_namespaced_pod.side_effect = [
        waiting_pod,
        waiting_pod,
        running_pod
    ]

    with patch("app.network_diagnostics.service.time.sleep") as mock_sleep:
        result = ensure_netshoot_ready(
            mock_k8s,
            pod_name="http-test",
            namespace="iomt-dev-1"
        )

    assert result == "netshoot-capture"
    assert mock_k8s.read_namespaced_pod.call_count == 3

    mock_sleep.assert_called_once_with(1.0)

    mock_k8s.patch_namespaced_pod_ephemeralcontainers.assert_not_called()


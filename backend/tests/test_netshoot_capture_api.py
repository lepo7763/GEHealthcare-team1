import pytest

from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.k8s_client import get_core_v1_api, get_batch_v1_api
from kubernetes.client.exceptions import ApiException

from app.network_diagnostics.job_service import CaptureSchedulingCleanupError


@pytest.fixture
def mock_clients(monkeypatch):
    """Replace real Kubernetes clients with mocks for each test."""

    core = Mock()
    batch = Mock()

    app.dependency_overrides[get_core_v1_api] = lambda: core
    app.dependency_overrides[get_batch_v1_api] = lambda: batch

    monkeypatch.setenv(
        "IOMT_NETSHOOT_ALLOWED_NAMESPACES",
        "iomt-dev-1",
    )

    yield core, batch

    app.dependency_overrides.pop(get_core_v1_api, None)
    app.dependency_overrides.pop(get_batch_v1_api, None)

def test_start_netshoot_capture_success(mock_clients):
    """A valid request schedules Jobs and returns HTTP 202."""

    core, batch = mock_clients

    scheduled_jobs = {
        "test-node": {
            "job_name": "netshoot-diagnostics-abc123",
            "targets": [
                {
                    "name": "http-test-1",
                    "namespace": "iomt-dev-1",
                    "uid": "uid-123",
                    "ip": "10.0.0.1",
                }
            ],
        }
    }

    with patch(
        "app.network_diagnostics.router.schedule_capture_jobs",
        return_value=scheduled_jobs,
    ) as mock_schedule:

        response = TestClient(app).post(
            "/api/network/captures",
            json={
                "namespaces": ["iomt-dev-1"],
                "duration_seconds": 120,
            },
        )

    assert response.status_code == 202

    data = response.json()

    assert data["duration_seconds"] == 120
    assert data["jobs_by_node"] == scheduled_jobs

    mock_schedule.assert_called_once_with(
        core_api=core,
        batch_api=batch,
        namespaces=["iomt-dev-1"],
        duration_seconds=120,
    )

def test_start_netshoot_capture_forbidden_namespace(mock_clients):
    """Reject namespaces outside the approved capture scope."""

    with patch(
        "app.network_diagnostics.router.schedule_capture_jobs"
    ) as mock_schedule:

        response = TestClient(app).post(
            "/api/network/captures",
            json={
                "namespaces": ["kube-system"],
                "duration_seconds": 30,
            },
        )

    assert response.status_code == 403
    mock_schedule.assert_not_called()

@pytest.mark.parametrize(
    "duration",
    [0, -1, 601, "30", True],
)
def test_start_netshoot_capture_invalid_duration(
    mock_clients,
    duration,
):
    """Reject invalid capture durations before scheduling."""

    with patch(
        "app.network_diagnostics.router.schedule_capture_jobs"
    ) as mock_schedule:

        response = TestClient(app).post(
            "/api/network/captures",
            json={
                "namespaces": ["iomt-dev-1"],
                "duration_seconds": duration,
            },
        )

    assert response.status_code == 422
    mock_schedule.assert_not_called()

@pytest.mark.parametrize(
    "kubernetes_status, expected_http_status",
    [
        (403, 403),
        (500, 503),
    ],
)
def test_start_netshoot_capture_kubernetes_error(
    mock_clients,
    kubernetes_status,
    expected_http_status,
):
    """Verify Kubernetes errors become appropriate HTTP responses."""

    with patch(
        "app.network_diagnostics.router.schedule_capture_jobs",
        side_effect=ApiException(
            status=kubernetes_status,
            reason="Kubernetes API error",
        ),
    ):
        response = TestClient(app).post(
            "/api/network/captures",
            json={
                "namespaces": ["iomt-dev-1"],
                "duration_seconds": 30,
            },
        )

    assert response.status_code == expected_http_status

def test_start_netshoot_capture_reports_cleanup_failure(mock_clients):
    """Return affected Job names when cleanup fails."""

    with patch(
        "app.network_diagnostics.router.schedule_capture_jobs",
        side_effect=CaptureSchedulingCleanupError(["job-A"]),
    ):
        response = TestClient(app).post(
            "/api/network/captures",
            json={
                "namespaces": ["iomt-dev-1"],
                "duration_seconds": 30,
            },
        )

    assert response.status_code == 503

    detail = response.json()["detail"]

    assert "job-A" in detail["job_names"]
    assert "cleanup" in detail["message"].lower()
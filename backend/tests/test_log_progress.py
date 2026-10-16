from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from kubernetes import client

from app.main import app
from app.core.k8s_client import get_core_v1_api
from app.log_collection.progress import (
    CONTAINER_LOGS_SERVICE_ID,
    ServiceProgress,
    tracker,
)

test_client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_tracker():
    """Keep the process-global tracker from leaking state between tests."""
    tracker.reset()
    yield
    tracker.reset()


@pytest.fixture
def mock_k8s():
    v1 = MagicMock(spec=client.CoreV1Api)
    app.dependency_overrides[get_core_v1_api] = lambda: v1
    yield v1
    app.dependency_overrides.clear()


def make_pod(namespace="default", name="pod", containers=("app",)):
    return client.V1Pod(
        metadata=client.V1ObjectMeta(namespace=namespace, name=name),
        spec=client.V1PodSpec(
            containers=[client.V1Container(name=c) for c in containers]
        ),
        status=client.V1PodStatus(container_statuses=[]),
    )


# ---------------------------------------------------------------------------
# Tracker unit behaviour
# ---------------------------------------------------------------------------


def test_progress_is_idle_initially():
    body = test_client.get("/api/logs/progress").json()
    assert body["status"] == "idle"
    assert body["services"] == []


def test_tracker_records_counters_and_finishes():
    tracker.begin([ServiceProgress(id=CONTAINER_LOGS_SERVICE_ID, label="Container Logs")])
    assert tracker.running is True

    tracker.set_service_totals(CONTAINER_LOGS_SERVICE_ID, pods_total=1, containers_total=2)
    tracker.record_container(CONTAINER_LOGS_SERVICE_ID, "ns/pod")
    tracker.record_container(CONTAINER_LOGS_SERVICE_ID, "ns/pod", had_error=True)
    tracker.record_pod_done(CONTAINER_LOGS_SERVICE_ID)

    service = tracker.snapshot()["services"][0]
    assert service["status"] == "collecting"
    assert service["pods_total"] == 1
    assert service["pods_done"] == 1
    assert service["containers_total"] == 2
    assert service["containers_done"] == 2
    assert service["errors"] == 1

    tracker.finish()
    assert tracker.running is False
    assert tracker.snapshot()["status"] == "done"


# ---------------------------------------------------------------------------
# End-to-end through the endpoints
# ---------------------------------------------------------------------------


def test_progress_reports_done_with_counts_after_collection(mock_k8s):
    mock_k8s.list_pod_for_all_namespaces.return_value = client.V1PodList(
        items=[
            make_pod(namespace="a", name="p1", containers=("c1",)),
            make_pod(namespace="b", name="p2", containers=("c2", "c3")),
        ]
    )
    mock_k8s.read_namespaced_pod_log.return_value = "line"

    assert test_client.get("/api/logs/zip?throttle_delay_ms=0").status_code == 200

    body = test_client.get("/api/logs/progress").json()
    assert body["status"] == "done"
    service = body["services"][0]
    assert service["id"] == CONTAINER_LOGS_SERVICE_ID
    assert service["status"] == "done"
    assert service["pods_total"] == 2
    assert service["pods_done"] == 2
    assert service["containers_total"] == 3
    assert service["containers_done"] == 3
    assert service["errors"] == 0


def test_progress_reports_error_when_cluster_unreachable(mock_k8s):
    mock_k8s.list_pod_for_all_namespaces.side_effect = RuntimeError("boom")

    response = test_client.get("/api/logs/zip")
    assert response.status_code == 503

    body = test_client.get("/api/logs/progress").json()
    assert body["status"] == "error"
    assert "boom" in body["message"]


def test_zip_returns_409_while_a_collection_is_running():
    tracker.begin(
        [ServiceProgress(id=CONTAINER_LOGS_SERVICE_ID, label="Container Log Collection")]
    )
    response = test_client.get("/api/logs/zip")
    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


from app.network_diagnostics.job_service import build_netshoot_job
from app.network_diagnostics.job_service import submit_netshoot_job
from app.network_diagnostics.job_service import get_netshoot_job_status
from app.network_diagnostics.job_service import discover_capture_targets
from app.network_diagnostics.job_service import schedule_capture_jobs
from app.network_diagnostics.job_service import (discover_targets_across_namespaces,)
from app.network_diagnostics.job_service import find_ready_sandbox_id

from types import SimpleNamespace
from unittest.mock import Mock

import json
import pytest


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

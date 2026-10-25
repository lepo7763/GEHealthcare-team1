import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.core.k8s_client import get_batch_v1_api, get_core_v1_api
from app.log_collection.progress import tracker
from app.main import app
from app.umf_rti.config import UmfRtiConfig
from app.umf_rti.schemas import UmfRtiParams
from app.umf_rti.service import (
    SDDS_REQUIRED_KEYS,
    UmfRtiPrerequisiteError,
    build_job,
    resolve_router_peer,
    write_artifacts,
)
from app.log_collection.schemas import LogCollectionManifest

test_client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_tracker():
    tracker.reset()
    yield
    tracker.reset()


@pytest.fixture
def clients():
    core = MagicMock(spec=client.CoreV1Api)
    batch = MagicMock(spec=client.BatchV1Api)
    app.dependency_overrides[get_core_v1_api] = lambda: core
    app.dependency_overrides[get_batch_v1_api] = lambda: batch
    yield core, batch
    app.dependency_overrides.clear()


def make_config(**overrides) -> UmfRtiConfig:
    values = dict(
        image="platform/rti:test",
        namespace="iomt-integration",
        image_pull_secrets=["pull-secret"],
        qos_configmap="umf-rti-qos",
        qos_key="CommissioningQoS.xml",
        sdds_secret="umf-rti-sdds",
        collector_secret="umf-rti-collector",
        collector_key="umf-rti-collector.jar",
        license_secret="umf-rti-license",
        license_key="rti_license.dat",
        router_namespace="pm",
        router_service="axone-router-1",
        wait_timeout_seconds=30,
        poll_interval_seconds=0.01,
    )
    values.update(overrides)
    return UmfRtiConfig(**values)


def make_service(domain_ports=None):
    domain_ports = domain_ports or {12: [10410, 10411, 10412], 32: [15410, 15411]}
    ports = []
    for domain, values in domain_ports.items():
        for port in values:
            ports.append(
                client.V1ServicePort(name=f"domain-{domain}-{port}", port=port)
            )
    return client.V1Service(
        metadata=client.V1ObjectMeta(name="axone-router-1", namespace="pm"),
        spec=client.V1ServiceSpec(ports=ports),
    )


def make_terminal_pod(name="umf-rti-pod", phase="Succeeded", waiting=None, exit_code=0):
    if waiting:
        state = client.V1ContainerState(
            waiting=client.V1ContainerStateWaiting(reason=waiting, message=waiting)
        )
    else:
        state = client.V1ContainerState(
            terminated=client.V1ContainerStateTerminated(exit_code=exit_code)
        )
    return client.V1Pod(
        metadata=client.V1ObjectMeta(name=name, labels={"job-name": "umf-rti-job"}),
        spec=client.V1PodSpec(containers=[], node_name="edge-node"),
        status=client.V1PodStatus(
            phase=phase,
            container_statuses=[
                client.V1ContainerStatus(
                    name="umf-rti-collector",
                    image="platform/rti:test",
                    image_id="",
                    ready=phase == "Succeeded",
                    restart_count=0,
                    state=state,
                )
            ],
        ),
    )


def make_umf_pod(phase="Running", waiting=None):
    return make_terminal_pod(name="umf-rti-pod", phase=phase, waiting=waiting)


def configure_prerequisites(core, collector_bytes=True):
    core.read_namespaced_config_map.return_value = client.V1ConfigMap(
        data={"CommissioningQoS.xml": "<dds/>"}
    )

    def secret(name, namespace):
        if name == "umf-rti-sdds":
            return client.V1Secret(data={key: "eA==" for key in SDDS_REQUIRED_KEYS})
        if name == "umf-rti-collector":
            return client.V1Secret(
                data={"umf-rti-collector.jar": "eA==" if collector_bytes else ""}
            )
        if name == "umf-rti-license":
            return client.V1Secret(data={"rti_license.dat": "eA=="})
        raise AssertionError(f"unexpected secret {name}")

    core.read_namespaced_secret.side_effect = secret
    core.read_namespaced_service.return_value = make_service()


def _ndjson(*records):
    return "\n".join(
        json.dumps(record, separators=(",", ":")) for record in records
    )


NDJSON = _ndjson(
    {
        "type": "collector",
        "collector_version": "1.0.0",
        "rti_version": "6.1.2.31",
        "sample_values_captured": False,
    },
    {
        "type": "participant",
        "guid": "p1",
        "name": "SvcAxRouter",
        "domain_id": 32,
    },
    {
        "type": "topic",
        "name": "umfcmd_req",
        "type_name": "umfcmd_req::S35c_sapphire",
        "observed": True,
    },
    {
        "type": "writer",
        "topic": "umfcmd_req",
        "type_name": "umfcmd_req::S35c_sapphire",
        "guid": "w1",
        "participant_guid": "p1",
        "qos": {"reliability": "RELIABLE_RELIABILITY_QOS"},
    },
    {
        "type": "reader",
        "topic": "umf_cfg_state",
        "type_name": "umf_cfg_state::S35c_sapphire",
        "guid": "r1",
        "participant_guid": "p1",
        "qos": {"durability": "TRANSIENT_LOCAL_DURABILITY_QOS"},
    },
    {
        "type": "summary",
        "collector_version": "1.0.0",
        "rti_version": "6.1.2.31",
        "counts": {
            "participants": 1,
            "topics": 1,
            "writers": 1,
            "readers": 1,
            "discovered_topic_handles": 13,
        },
    },
)


def unzip_response(response):
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    buf = io.BytesIO(response.content)
    assert zipfile.is_zipfile(buf)
    files = {}
    with zipfile.ZipFile(buf) as zf:
        assert zf.testzip() is None
        for name in zf.namelist():
            files[name] = zf.read(name).decode("utf-8")
    manifest = json.loads(files["manifest.json"])
    return manifest, files


def deleted_state_side_effects(core, batch, pod, log_text=""):
    """Configure a Job that succeeds and disappears after delete."""
    state = {"deleted": False}
    job = client.V1Job(
        metadata=client.V1ObjectMeta(name="umf-rti-job"),
        status=client.V1JobStatus(succeeded=1),
    )

    def read_job(name, namespace, **kwargs):
        if state["deleted"]:
            raise ApiException(status=404, reason="Not Found")
        return job

    def delete_job(name, namespace, **kwargs):
        state["deleted"] = True
        return client.V1Status(status="Success")

    def list_pods(namespace, **kwargs):
        if state["deleted"]:
            return client.V1PodList(items=[])
        return client.V1PodList(items=[pod])

    batch.read_namespaced_job_status.side_effect = read_job
    batch.delete_namespaced_job.side_effect = delete_job
    core.list_namespaced_pod.side_effect = list_pods
    core.read_namespaced_pod_log.return_value = log_text
    return state


# ---------------------------------------------------------------------------
# Job spec and peer resolution
# ---------------------------------------------------------------------------


def test_job_spec_uses_platform_image_and_no_host_network():
    config = make_config()
    params = UmfRtiParams(umf_domain_id=32, umf_duration_seconds=30)
    job = build_job(
        config, params, "udpv4://axone-router-1.pm.svc.cluster.local", "test-job"
    )
    pod_spec = job.spec.template.spec
    container = pod_spec.containers[0]

    assert container.image == "platform/rti:test"
    assert container.image_pull_policy == "IfNotPresent"
    assert pod_spec.host_network is False
    assert pod_spec.automount_service_account_token is False
    assert pod_spec.restart_policy == "Never"
    assert job.spec.backoff_limit == 0
    assert job.spec.active_deadline_seconds == 330
    assert job.spec.ttl_seconds_after_finished == 600

    volume_names = {volume.name for volume in pod_spec.volumes}
    assert volume_names == {
        "umf-rti-collector",
        "umf-rti-license",
        "umf-rti-qos",
        "umf-rti-sdds",
    }
    assert pod_spec.image_pull_secrets[0].name == "pull-secret"
    assert container.resources.requests["memory"] == "256Mi"
    assert container.resources.limits["cpu"] == "1"

    env = {item.name: item.value for item in container.env}
    assert env["NDDS_DISCOVERY_PEERS"] == "udpv4://axone-router-1.pm.svc.cluster.local"
    assert env["DDS_SECURE"] == "secure"
    assert env["SDDS_HOME"] == "/opt/axone-tools/sdds"
    assert env["RTI_LICENSE_FILE"] == "/opt/axone-tools/license/rti_license.dat"
    assert env["UMF_DOMAIN_ID"] == "32"
    assert env["UMF_DURATION_SECONDS"] == "30"
    assert container.security_context.allow_privilege_escalation is False
    assert container.security_context.run_as_user == 2017


def test_resolve_router_peer_uses_domain_service_port_without_suffix(clients):
    core, _ = clients
    config = make_config()
    core.read_namespaced_service.return_value = make_service()

    peer, port = resolve_router_peer(core, 12, config)
    assert peer == "udpv4://axone-router-1.pm.svc.cluster.local"
    assert ":" not in peer.replace("udpv4://", "")
    assert port == 10410

    peer, port = resolve_router_peer(core, 32, config)
    assert peer == "udpv4://axone-router-1.pm.svc.cluster.local"
    assert port == 15410


def test_resolve_router_peer_rejects_unexposed_domain(clients):
    core, _ = clients
    core.read_namespaced_service.return_value = make_service()
    with pytest.raises(UmfRtiPrerequisiteError) as exc:
        resolve_router_peer(core, 99, make_config())
    assert "Available domain ports" in str(exc.value)
    assert "32" in str(exc.value)


def test_missing_prerequisite_returns_actionable_503(clients):
    core, _ = clients
    core.read_namespaced_config_map.side_effect = ApiException(
        status=404, reason="Not Found"
    )

    response = test_client.get(
        "/api/logs/zip?services=umf-rti&umf_domain_id=32&umf_duration_seconds=30"
    )
    assert response.status_code == 503
    assert "umf-rti-setup.sh" in response.json()["detail"]
    core.list_pod_for_all_namespaces.assert_not_called()


# ---------------------------------------------------------------------------
# Successful capture
# ---------------------------------------------------------------------------


def test_umf_rti_only_success_writes_artifacts_and_deletes_job(clients):
    core, batch = clients
    configure_prerequisites(core)
    state = deleted_state_side_effects(
        core, batch, make_terminal_pod(phase="Succeeded"), NDJSON
    )

    response = test_client.get(
        "/api/logs/zip?services=umf-rti&umf_domain_id=32&umf_duration_seconds=30"
    )
    manifest, files = unzip_response(response)

    assert "umf-rti/umf-rti-discovery.ndjson" in files
    assert "umf-rti/umf-rti-summary.json" in files
    assert "umf-rti/README.txt" in files
    assert "umf-rti/umf-rti-collector.log" not in files
    summary = json.loads(files["umf-rti/umf-rti-summary.json"])
    assert summary["domain"] == 32
    assert summary["status"] == "succeeded"
    assert "warnings" not in summary
    assert "error" not in summary
    assert summary["router_peer"] == "udpv4://axone-router-1.pm.svc.cluster.local"
    assert summary["router_port"] == 15410
    assert summary["counts"]["participants"] == 1
    assert summary["counts"]["writers"] == 1

    ndjson = files["umf-rti/umf-rti-discovery.ndjson"]
    assert '"type":"participant"' in ndjson
    assert '"type":"writer"' in ndjson

    assert manifest["services"][0]["id"] == "umf-rti"
    assert manifest["services"][0]["status"] == "done"
    assert manifest["errors"] == []
    assert state["deleted"] is True
    batch.create_namespaced_job.assert_called_once()
    batch.delete_namespaced_job.assert_called_once()
    core.list_pod_for_all_namespaces.assert_not_called()


def test_umf_rti_failure_preserves_container_logs(clients):
    core, batch = clients
    configure_prerequisites(core)
    container_pod = client.V1Pod(
        metadata=client.V1ObjectMeta(namespace="pm", name="app-pod"),
        spec=client.V1PodSpec(containers=[client.V1Container(name="app")]),
        status=client.V1PodStatus(container_statuses=[]),
    )
    core.list_pod_for_all_namespaces.return_value = client.V1PodList(
        items=[container_pod]
    )
    failed_pod = make_umf_pod(phase="Pending", waiting="ImagePullBackOff")
    state = {"deleted": False}

    def read_job(name, namespace, **kwargs):
        if state["deleted"]:
            raise ApiException(status=404, reason="Not Found")
        return client.V1Job(
            metadata=client.V1ObjectMeta(name="umf-rti-job"),
            status=client.V1JobStatus(active=1),
        )

    def delete_job(name, namespace, **kwargs):
        state["deleted"] = True
        return client.V1Status(status="Success")

    def list_pods(namespace, **kwargs):
        if state["deleted"]:
            return client.V1PodList(items=[])
        return client.V1PodList(items=[failed_pod])

    batch.read_namespaced_job_status.side_effect = read_job
    batch.delete_namespaced_job.side_effect = delete_job
    core.list_namespaced_pod.side_effect = list_pods
    core.read_namespaced_pod_log.side_effect = (
        lambda name, namespace, container, **kwargs: (
            "app log line" if name == "app-pod" else ""
        )
    )

    response = test_client.get(
        "/api/logs/zip?services=container-logs&services=umf-rti"
        "&umf_domain_id=32&umf_duration_seconds=30&throttle_delay_ms=0"
    )
    manifest, files = unzip_response(response)

    assert "logs/pm/app-pod/app.log" in files
    assert files["logs/pm/app-pod/app.log"] == "app log line"
    assert "umf-rti/umf-rti-summary.json" in files
    summary = json.loads(files["umf-rti/umf-rti-summary.json"])
    assert summary["status"] == "failed"
    assert "ImagePullBackOff" in (summary.get("error") or "")
    assert "warnings" not in summary
    assert "error" in summary
    readme = files["umf-rti/README.txt"]
    assert "UMF RTI discovery capture" in readme
    assert "Limitations" not in readme
    assert "Warnings" not in readme
    service_ids = {service["id"]: service for service in manifest["services"]}
    assert service_ids["container-logs"]["status"] == "done"
    assert service_ids["umf-rti"]["status"] == "error"
    assert any(error["service"] == "umf-rti" for error in manifest["errors"])
    assert state["deleted"] is True


def test_umf_rti_timeout_is_recorded_and_job_deleted(clients):
    core, batch = clients
    configure_prerequisites(core)
    running_pod = make_umf_pod(phase="Running")
    state = {"deleted": False}

    def read_job(name, namespace, **kwargs):
        if state["deleted"]:
            raise ApiException(status=404, reason="Not Found")
        return client.V1Job(
            metadata=client.V1ObjectMeta(name="umf-rti-job"),
            status=client.V1JobStatus(active=1),
        )

    def delete_job(name, namespace, **kwargs):
        state["deleted"] = True
        return client.V1Status(status="Success")

    def list_pods(namespace, **kwargs):
        if state["deleted"]:
            return client.V1PodList(items=[])
        return client.V1PodList(items=[running_pod])

    batch.read_namespaced_job_status.side_effect = read_job
    batch.delete_namespaced_job.side_effect = delete_job
    core.list_namespaced_pod.side_effect = list_pods
    core.read_namespaced_pod_log.return_value = NDJSON

    clock = {"now": 0.0}

    def fake_monotonic():
        clock["now"] += 100.0
        return clock["now"]

    with patch("app.umf_rti.service.time.monotonic", side_effect=fake_monotonic):
        with patch("app.umf_rti.service.time.sleep", return_value=None):
            response = test_client.get(
                "/api/logs/zip?services=umf-rti&umf_domain_id=32"
                "&umf_duration_seconds=30&umf_max_bytes=1048576"
            )

    manifest, files = unzip_response(response)
    summary = json.loads(files["umf-rti/umf-rti-summary.json"])
    assert summary["status"] == "timeout"
    assert state["deleted"] is True
    assert manifest["services"][0]["status"] == "error"


def test_job_without_pod_fails_fast_with_event_message(clients):
    core, batch = clients
    configure_prerequisites(core)
    state = {"deleted": False}

    def read_job(name, namespace, **kwargs):
        if state["deleted"]:
            raise ApiException(status=404, reason="Not Found")
        return client.V1Job(
            metadata=client.V1ObjectMeta(name="umf-rti-job"),
            status=client.V1JobStatus(active=1),
        )

    def delete_job(name, namespace, **kwargs):
        state["deleted"] = True
        return client.V1Status(status="Success")

    batch.read_namespaced_job_status.side_effect = read_job
    batch.delete_namespaced_job.side_effect = delete_job
    core.list_namespaced_pod.return_value = client.V1PodList(items=[])
    core.list_namespaced_event.return_value = client.CoreV1EventList(
        items=[
            client.CoreV1Event(
                metadata=client.V1ObjectMeta(name="event-1"),
                involved_object=client.V1ObjectReference(kind="Job", name="job"),
                type="Warning",
                message="pods is forbidden: exceeded quota: iomt-integration-quota",
            )
        ]
    )

    clock = {"now": 0.0}

    def fake_monotonic():
        clock["now"] += 100.0
        return clock["now"]

    with patch("app.umf_rti.service.time.monotonic", side_effect=fake_monotonic):
        with patch("app.umf_rti.service.time.sleep", return_value=None):
            response = test_client.get(
                "/api/logs/zip?services=umf-rti&umf_domain_id=32"
                "&umf_duration_seconds=30"
            )

    manifest, files = unzip_response(response)
    summary = json.loads(files["umf-rti/umf-rti-summary.json"])
    assert summary["status"] == "failed"
    assert "did not create a Pod" in summary["error"]
    assert "exceeded quota" in summary["error"]
    assert state["deleted"] is True
    assert manifest["services"][0]["status"] == "error"
    core.list_namespaced_event.assert_called_once()


# ---------------------------------------------------------------------------
# Query validation and naming
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "services=unknown",
        "services=umf-rti&umf_duration_seconds=10",
        "services=umf-rti&umf_duration_seconds=601",
        "services=umf-rti&umf_domain_id=101",
        "services=umf-rti&umf_domain_id=-1",
        "services=",
    ],
)
def test_invalid_umf_rti_query_returns_422(clients, query):
    response = test_client.get(f"/api/logs/zip?{query}")
    assert response.status_code == 422


def test_user_facing_names_do_not_mention_rtiddsspy(clients):
    config = make_config()
    params = UmfRtiParams(umf_domain_id=32, umf_duration_seconds=30)
    job = build_job(
        config, params, "udpv4://axone-router-1.pm.svc.cluster.local", "test-job"
    )
    labels = " ".join(f"{key}={value}" for key, value in job.metadata.labels.items())
    assert "rtiddsspy" not in labels.lower()
    assert "headless dds capture" not in labels.lower()
    assert "umf-rti" in labels


def test_write_artifacts_keeps_output_package_positive(tmp_path):
    manifest = LogCollectionManifest(timestamp_utc="now", total_logs_collected=0)
    raw_log = "RTI security warning line\n" + NDJSON
    result = MagicMock()
    result.log_text = raw_log
    result.domain_id = 32
    result.duration_seconds = 30
    result.router_peer = "udpv4://axone-router-1.pm.svc.cluster.local"
    result.router_port = 15410
    result.image = "platform/rti:test"
    result.namespace = "iomt-integration"
    result.job_name = "job"
    result.pod_name = "pod"
    result.node_name = "node"
    result.status = "succeeded"
    result.exit_code = 0
    result.started_at_utc = "start"
    result.finished_at_utc = "end"
    result.log_bytes = len(raw_log)
    result.truncated = False
    result.error = None
    result.warnings = ["internal limitation note"]
    result.counts = {
        "participants": 1,
        "topics": 1,
        "writers": 1,
        "readers": 1,
        "discovered_topic_handles": 13,
    }
    result.collector_version = "1.0.0"
    result.rti_version = "6.1.2.31"
    result.job_deleted = True

    zip_path = tmp_path / "out.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        write_artifacts(zf, manifest, result, UmfRtiParams(), make_config())

    expected_files = [
        "umf-rti/umf-rti-discovery.ndjson",
        "umf-rti/umf-rti-summary.json",
        "umf-rti/README.txt",
    ]
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert names == set(expected_files)
        assert "umf-rti/umf-rti-collector.log" not in names

        ndjson = zf.read("umf-rti/umf-rti-discovery.ndjson").decode()
        assert "RTI security warning line" not in ndjson
        assert "warnings" not in ndjson

        summary = json.loads(zf.read("umf-rti/umf-rti-summary.json"))
        assert summary["counts"]["participants"] == 1
        assert "warnings" not in summary
        assert "error" not in summary

        readme = zf.read("umf-rti/README.txt").decode()
        for forbidden in (
            "Warnings",
            "Limitations",
            "What is NOT captured",
            "TopicBuiltinTopicData",
            "Domain 12",
            "dedicated identity",
            "probe endpoints",
            "port suffix",
            "RTI security warning line",
            "internal limitation note",
        ):
            assert forbidden not in readme
        assert "What is captured" in readme
        assert "Privacy" in readme

    assert manifest.collected_files == expected_files
    assert manifest.services[0].id == "umf-rti"
    assert manifest.services[0].status == "done"
    assert manifest.services[0].files == expected_files

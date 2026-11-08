"""Unit tests for the UMF-RTI service (XML builders + capture orchestration).

The pure builders are tested directly; the capture lifecycle is tested with a
mocked kubernetes client (the real thing is validated live on the cluster).
"""

import base64
import io
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import MagicMock

import pytest
from app.log_collection.schemas import LogCollectionManifest
from app.umf_rti.config import UmfRtiConfig
from app.umf_rti.schemas import UmfRtiParams
from app.umf_rti.service import (
    CAPTURE_QOS_PROFILE,
    RECORDING_DB_BASENAME,
    UmfRtiCaptureError,
    build_capture_command,
    build_job_manifest,
    build_override_xml,
    build_recording_cfg_xml,
    capture_umf_rti,
    write_failure_artifacts,
)
from kubernetes.client.exceptions import ApiException

config = UmfRtiConfig()
params = UmfRtiParams()  # domain 13, 60s


# --- override.xml (the Cap::universal QoS profile) ---------------------------


def test_override_xml_is_well_formed():
    ET.fromstring(build_override_xml(config))


def test_override_lists_all_initial_peers():
    xml = build_override_xml(config)
    peers = config.initial_peers()
    assert len(peers) == 4  # router pod + 3 WAN ports
    for peer in peers:
        assert f"<element>{peer}</element>" in xml


def test_override_accepts_unknown_peers():
    assert "<accept_unknown_peers>true</accept_unknown_peers>" in build_override_xml(
        config
    )


def test_override_raises_type_object_limit():
    # MANDATORY: without this the recorder silently drops umfnum/umfwav.
    xml = build_override_xml(config)
    assert (
        f"<type_object_max_serialized_length>{config.type_object_max_serialized_length}"
        f"</type_object_max_serialized_length>"
    ) in xml


def test_override_unbounds_reader_resource_limits():
    # max_samples / max_instances / max_samples_per_instance all unbounded.
    assert build_override_xml(config).count("LENGTH_UNLIMITED") >= 3


# --- rec.xml (the rtirecordingservice config) --------------------------------


def test_recording_cfg_is_well_formed():
    ET.fromstring(build_recording_cfg_xml(13, config))


def test_recording_cfg_uses_json_sqlite():
    assert "<storage_format>JSON_SQLITE</storage_format>" in build_recording_cfg_xml(
        13, config
    )


def test_recording_cfg_substitutes_domain():
    assert "<domain_id>13</domain_id>" in build_recording_cfg_xml(13, config)
    assert "<domain_id>32</domain_id>" in build_recording_cfg_xml(32, config)


def test_recording_cfg_sets_wildcard_partition():
    # MANDATORY: viewpod umfnum/umfwav writers are in a named partition.
    xml = build_recording_cfg_xml(13, config)
    assert f"<element>{config.partition}</element>" in xml
    # Element order is strict: subscriber_qos must precede topic_group.
    assert xml.index("<subscriber_qos>") < xml.index("<topic_group")


def test_recording_cfg_references_capture_profile():
    assert CAPTURE_QOS_PROFILE == "Cap::universal"
    assert f'base_name="{CAPTURE_QOS_PROFILE}"' in build_recording_cfg_xml(13, config)


# --- capture command (the pod's shell script) --------------------------------


def test_command_writes_both_xml_files():
    script = build_capture_command(params, config)
    assert "cat > /tmp/override.xml <<'OVERRIDE_EOF'" in script
    assert "cat > /tmp/rec.xml <<'REC_EOF'" in script
    # the actual XML is embedded, not just the heredoc wrapper
    assert "JSON_SQLITE" in script
    assert "<accept_unknown_peers>true</accept_unknown_peers>" in script


def test_command_sets_public_address_to_pod_ip():
    # Must be evaluated at runtime in the pod, hence $(hostname -i).
    script = build_capture_command(params, config)
    assert 'export DDS_RTWAN_SERVER_PUBLIC_ADDRESS="$(hostname -i)"' in script


def test_command_exports_all_three_wan_ports():
    # WithWAN QoS fails to parse if any of the three is undefined.
    script = build_capture_command(params, config)
    assert "export DDS_RTWAN_SERVER_PORT_LOGGER=32007" in script
    assert "export DDS_RTWAN_SERVER_PORT_SOURCEPOD=32013" in script
    assert "export DDS_RTWAN_SERVER_PORT_VIEWPOD=32015" in script


def test_command_loads_both_qos_profiles():
    script = build_capture_command(params, config)
    assert (
        'export NDDS_QOS_PROFILES="/opt/axone-tools/qos/'
        'MDH-tools-RTIAdminConsole-WithWAN.xml;/tmp/override.xml"'
    ) in script


def test_command_records_for_requested_duration():
    script = build_capture_command(params, config)
    assert (
        f"timeout {params.umf_duration_seconds} rtirecordingservice "
        "-cfgFile /tmp/rec.xml -cfgName cap" in script
    )


def test_command_restores_mangled_filename():
    script = build_capture_command(params, config)
    assert (
        f"mv {config.output_dir}/capture. {config.output_dir}/{RECORDING_DB_BASENAME}"
        in script
    )


def test_command_signals_done_then_idles_for_grace():
    script = build_capture_command(params, config)
    done = script.index(f"touch {config.output_dir}/.done")
    idle = script.index(f"sleep {config.collect_grace_seconds}")
    # .done must be written before (and the pod then holds for) the grace window.
    assert done < idle


def test_command_passes_custom_duration():
    script = build_capture_command(UmfRtiParams(umf_duration_seconds=120), config)
    assert "timeout 120 rtirecordingservice" in script


# --- Job manifest ------------------------------------------------------------


def test_job_manifest_identity_and_policies():
    job = build_job_manifest(params, config)
    assert job.metadata.name.startswith(config.job_prefix)
    assert job.metadata.namespace == config.namespace
    assert job.spec.backoff_limit == 0
    assert job.spec.ttl_seconds_after_finished is not None
    assert job.spec.template.spec.restart_policy == "Never"


def test_job_manifest_container_runs_the_script():
    job = build_job_manifest(params, config)
    container = job.spec.template.spec.containers[0]
    assert container.image == config.image
    assert container.image_pull_policy == "Never"
    assert container.command[:2] == ["/bin/sh", "-c"]
    assert "rtirecordingservice" in container.command[2]


def test_job_manifest_resources_fit_quota():
    container = build_job_manifest(params, config).spec.template.spec.containers[0]
    assert container.resources.requests == {"cpu": "100m", "memory": "256Mi"}
    assert container.resources.limits == {"cpu": "500m", "memory": "1Gi"}


def test_job_manifest_mounts_emptydir_at_output_dir():
    spec = build_job_manifest(params, config).spec.template.spec
    volume = spec.volumes[0]
    assert volume.empty_dir is not None
    mount = spec.containers[0].volume_mounts[0]
    assert mount.name == volume.name
    assert mount.mount_path == config.output_dir


# --- capture lifecycle (mocked cluster) --------------------------------------


def _mock_pod(name="umf-rti-capture-abcd1234", phase="Running", waiting_reason=None):
    pod = MagicMock()
    pod.metadata.name = name
    pod.status.phase = phase
    if waiting_reason is None:
        pod.status.container_statuses = []
    else:
        cs = MagicMock()
        cs.state.waiting.reason = waiting_reason
        cs.state.waiting.message = "detail"
        pod.status.container_statuses = [cs]
    return pod


def _mock_batch(job_name="umf-rti-capture-abcd1234"):
    batch = MagicMock()
    batch.create_namespaced_job.return_value.metadata.name = job_name
    return batch


def _recording_tar_b64(files):
    """A base64'd .tar.gz of {name: bytes}, like the pod's `tar | base64`."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=f"./{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return base64.b64encode(buf.getvalue()).decode()


def _sqlite_db_bytes(topic_payloads):
    """Build a JSON_SQLITE-shaped user-data DB: {topic: [payload_dict, ...]}."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    for table, payloads in topic_payloads.items():
        con.execute(
            f'CREATE TABLE "{table}" (SampleInfo_flag INTEGER, rti_json_sample TEXT)'
        )
        con.executemany(
            f'INSERT INTO "{table}" (rti_json_sample) VALUES (?)',
            [(json.dumps(p),) for p in payloads],
        )
    con.commit()
    con.close()
    with open(path, "rb") as f:
        data = f.read()
    os.remove(path)
    return data


def _fake_stream_factory(tar_b64):
    """Return the done marker for the probe, the tar archive for the copy."""

    def fake_stream(_method, _pod, _ns, command=None, **kwargs):
        script = command[-1] if command else ""
        if "tar" in script:
            return tar_b64
        return "__UMF_DONE__\n"

    return fake_stream


def test_capture_happy_path(monkeypatch):
    core = MagicMock()
    core.list_namespaced_pod.return_value.items = [_mock_pod()]
    core.read_namespaced_pod.return_value = _mock_pod()
    capture_db = _sqlite_db_bytes(
        {
            "umfnum@13": [{"n": i} for i in range(3)],
            "umfwav@13": [{"w": i} for i in range(5)],
        }
    )
    tar_b64 = _recording_tar_b64(
        {
            "capture.db": capture_db,
            "discovery.db": b"y" * 50,
            "metadata.db": b"z" * 20,
            ".done": b"",
            ".rc": b"124\n",
        }
    )
    monkeypatch.setattr("app.umf_rti.service.stream", _fake_stream_factory(tar_b64))
    cfg = UmfRtiConfig(poll_interval_seconds=0)
    batch = _mock_batch()

    result = capture_umf_rti(
        core,
        batch,
        UmfRtiParams(umf_domain_id=13, umf_duration_seconds=15),
        cfg,
    )

    assert result.domain_id == 13
    assert result.duration_seconds == 15
    # Only the .db files are collected; the sentinel is ignored.
    assert sorted(result.recording_files) == [
        "capture.db",
        "discovery.db",
        "metadata.db",
    ]
    assert result.user_data_file == "capture.db"
    assert result.topic_sample_counts == {"umfnum@13": 3, "umfwav@13": 5}
    assert result.total_samples == 8
    assert result.warnings == []  # clean rc, samples present -> no warning
    # The pulled files really landed in the temp dir.
    assert result.recording_dir and os.path.isdir(result.recording_dir)
    assert os.path.exists(os.path.join(result.recording_dir, "capture.db"))
    # recording_dir is excluded from the serialized summary.
    assert "recording_dir" not in result.model_dump()
    # The Job is cleaned up on success.
    batch.delete_namespaced_job.assert_called_once()

    shutil.rmtree(result.recording_dir, ignore_errors=True)
    _, kwargs = core.list_namespaced_pod.call_args
    assert kwargs["label_selector"] == "job-name=umf-rti-capture-abcd1234"


def test_capture_warns_on_recorder_error_rc(monkeypatch):
    core = MagicMock()
    core.list_namespaced_pod.return_value.items = [_mock_pod()]
    core.read_namespaced_pod.return_value = _mock_pod()
    tar_b64 = _recording_tar_b64(
        {
            "capture.db": b"x" * 10,
            ".done": b"",
            ".rc": b"1\n",  # recorder died early
            "recorder.log": b"boom",
        }
    )
    monkeypatch.setattr("app.umf_rti.service.stream", _fake_stream_factory(tar_b64))

    result = capture_umf_rti(
        core, _mock_batch(), params, UmfRtiConfig(poll_interval_seconds=0)
    )

    assert any("exited early" in w for w in result.warnings)
    shutil.rmtree(result.recording_dir, ignore_errors=True)


def test_capture_deletes_job_even_on_failure():
    core = MagicMock()
    core.list_namespaced_pod.return_value.items = []  # never starts -> raises
    batch = _mock_batch()
    cfg = UmfRtiConfig(startup_timeout_seconds=0, poll_interval_seconds=0)
    with pytest.raises(UmfRtiCaptureError):
        capture_umf_rti(core, batch, params, cfg)
    batch.delete_namespaced_job.assert_called_once()


def test_write_failure_artifacts_records_error():
    manifest = LogCollectionManifest(timestamp_utc="t", total_logs_collected=0)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        write_failure_artifacts(zf, manifest, "Job could not start", params, config)

    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf:
        assert "umf_rti/ERROR.txt" in zf.namelist()
        assert "Job could not start" in zf.read("umf_rti/ERROR.txt").decode()
    assert "umf_rti/ERROR.txt" in manifest.collected_files
    assert manifest.services[0].status == "error"
    assert manifest.services[0].error == "Job could not start"


def test_capture_raises_when_job_create_fails():
    batch = MagicMock()
    batch.create_namespaced_job.side_effect = ApiException(reason="Forbidden")
    with pytest.raises(UmfRtiCaptureError):
        capture_umf_rti(MagicMock(), batch, params, config)


def test_capture_raises_when_pod_never_starts():
    core = MagicMock()
    core.list_namespaced_pod.return_value.items = []  # nothing ever scheduled
    cfg = UmfRtiConfig(startup_timeout_seconds=0, poll_interval_seconds=0)
    with pytest.raises(UmfRtiCaptureError, match="did not reach Running"):
        capture_umf_rti(core, _mock_batch(), params, cfg)


def test_capture_surfaces_image_pull_error():
    core = MagicMock()
    core.list_namespaced_pod.return_value.items = [
        _mock_pod(phase="Pending", waiting_reason="ErrImageNeverPull")
    ]
    cfg = UmfRtiConfig(startup_timeout_seconds=5, poll_interval_seconds=0)
    with pytest.raises(UmfRtiCaptureError, match="ErrImageNeverPull"):
        capture_umf_rti(core, _mock_batch(), params, cfg)


def test_capture_warns_when_no_samples(monkeypatch):
    core = MagicMock()
    core.list_namespaced_pod.return_value.items = [_mock_pod()]
    core.read_namespaced_pod.return_value = _mock_pod()
    # A valid DB whose only topic table is empty -> nothing captured.
    tar_b64 = _recording_tar_b64(
        {
            "capture.db": _sqlite_db_bytes({"umfnum@13": []}),
            ".done": b"",
            ".rc": b"124\n",
        }
    )
    monkeypatch.setattr("app.umf_rti.service.stream", _fake_stream_factory(tar_b64))

    result = capture_umf_rti(
        core, _mock_batch(), params, UmfRtiConfig(poll_interval_seconds=0)
    )

    assert result.total_samples == 0
    assert any("idle" in w for w in result.warnings)
    shutil.rmtree(result.recording_dir, ignore_errors=True)


# --- write_artifacts (zip assembly) ------------------------------------------


def _populated_recording_dir():
    """A temp recording dir like capture_umf_rti produces, with a real DB."""
    d = tempfile.mkdtemp(prefix="umf-rti-test-")
    with open(os.path.join(d, "capture.db"), "wb") as f:
        f.write(_sqlite_db_bytes({"umfnum@13": [{"n": 1}, {"n": 2}]}))
    for name in ("discovery.db", "metadata.db"):
        with open(os.path.join(d, name), "wb") as f:
            f.write(b"\x00")
    with open(os.path.join(d, "recorder.log"), "w") as f:
        f.write("recorder output")
    return d


def test_write_artifacts_bundles_recording_json_and_summary():
    recording_dir = _populated_recording_dir()
    from app.umf_rti.schemas import UmfRtiCaptureResult

    result = UmfRtiCaptureResult(
        domain_id=13,
        duration_seconds=15,
        recording_dir=recording_dir,
        recording_files=["capture.db", "discovery.db", "metadata.db"],
        user_data_file="capture.db",
        topic_sample_counts={"umfnum@13": 2},
        total_samples=2,
    )
    manifest = LogCollectionManifest(timestamp_utc="t", total_logs_collected=0)
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w") as zf:
            from app.umf_rti.service import write_artifacts

            write_artifacts(zf, manifest, result, params, config)

        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf:
            names = zf.namelist()
            assert "umf_rti/recording/capture.db" in names
            assert "umf_rti/recording/discovery.db" in names
            assert "umf_rti/recording/metadata.db" in names
            assert "umf_rti/recorder.log" in names
            assert "umf_rti/json/umfnum@13.json" in names
            assert "umf_rti/summary.json" in names
            # per-topic JSON is readable and matches the payloads
            samples = json.loads(zf.read("umf_rti/json/umfnum@13.json"))
            assert samples == [{"n": 1}, {"n": 2}]
            # summary.json is valid and excludes the local temp path
            summary = json.loads(zf.read("umf_rti/summary.json"))
            assert summary["total_samples"] == 2
            assert "recording_dir" not in summary
        # manifest records the service as done with the files it added
        assert manifest.services[0].status == "done"
        assert "umf_rti/json/umfnum@13.json" in manifest.collected_files
    finally:
        shutil.rmtree(recording_dir, ignore_errors=True)


# --- domain restriction (only the cert-authorized 7/12/13) -------------------


def test_params_accepts_authorized_domains():
    for domain in (7, 12, 13):
        assert UmfRtiParams(umf_domain_id=domain).umf_domain_id == domain


def test_params_rejects_unauthorized_domains():
    import pydantic

    for domain in (0, 32, 34, 232):
        with pytest.raises(pydantic.ValidationError):
            UmfRtiParams(umf_domain_id=domain)

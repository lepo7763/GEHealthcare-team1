"""Core dump collection: parsing, filtering, Job manifest, exec streaming,
packaging and endpoints. The real transfer is validated live on the cluster;
here the Kubernetes client and the collector pod are faked.
"""

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.core import job_exec as job_exec_mod
from app.core.job_exec import JobExecError, exec_to_sink
from app.core_dumps.collector import (
    CollectorSession,
    CoreDumpCollectionError,
    build_collector_job,
)
from app.core_dumps.config import CoreDumpConfig
from app.core_dumps.parsing import (
    is_safe_relative_path,
    parse_core_file,
    parse_listing,
    select_files,
)
from app.core_dumps.schemas import CoreDumpParams, HostCoreConfig
from app.core_dumps.service import SUMMARY_PATH, collect_core_dumps_into
from app.log_collection.progress import CORE_DUMPS_SERVICE_ID, ServiceProgress, tracker
from app.log_collection.schemas import LogCollectionManifest
from app.main import app
from fastapi.testclient import TestClient
from websocket import ABNF

T0 = 1794521196  # 2026-11-12T22:06:36Z
HANDLER_NAME = f"core.xGate.pid35.sig6.usr2017.grp2017.time{T0}.gz"


# --- filename parsing ---------------------------------------------------------


def test_parses_handler_filename():
    f = parse_core_file(HANDLER_NAME, 282627, T0 + 26)
    assert (f.process, f.pid, f.signal, f.signal_name) == ("xGate", 35, 6, "SIGABRT")
    assert (f.uid, f.gid) == (2017, 2017)
    assert f.time_utc == datetime.fromtimestamp(T0, tz=timezone.utc)
    assert f.source == "kernel-handler"


@pytest.mark.parametrize(
    "name, process",
    [
        ("core.java.lang.Thr.pid9.sig11.usr0.grp0.time100.gz", "java.lang.Thr"),
        ("core.my_proc_name.pid9.sig11.usr0.grp0.time100", "my_proc_name"),  # no .gz
        ("core.an-reg-task-0.pid7.sig6.usr2017.grp2017.time100.gz", "an-reg-task-0"),
    ],
)
def test_parses_awkward_process_names(name, process):
    f = parse_core_file(name, 1, 100)
    assert f.process == process
    assert f.signal_name == ("SIGSEGV" if ".sig11." in name else "SIGABRT")


def test_unparseable_name_falls_back_to_mtime():
    f = parse_core_file("core.weird", 5, T0)
    assert f.process is None and f.signal is None
    assert f.time_utc == f.mtime_utc


def test_unknown_signal_number_still_named():
    assert parse_core_file("core.x.pid1.sig99.usr0.grp0.time1", 1, 1).signal_name == "SIG99"


def test_pvc_file_source():
    f = parse_core_file(
        "pvc-0cd0094b-99ba_compute_axone-compute-idam-keycloak-coredump-pvc/core.1", 1, 1
    )
    assert f.source == "pvc:compute/axone-compute-idam-keycloak-coredump-pvc"


@pytest.mark.parametrize(
    "path, ok",
    [
        ("core.a", True),
        ("pvc-x/core.a", True),
        ("/etc/shadow", False),
        ("../etc/shadow", False),
        ("pvc-x/../../etc/shadow", False),
        ("a//b", False),
        ("", False),
        ("a\nb", False),
    ],
)
def test_safe_relative_path(path, ok):
    assert is_safe_relative_path(path) is ok


# --- listing parsing ------------------------------------------------------------

PV_DIR = "pvc-59f86ae2-ab20_compute_axone-compute-management-coredump-pvc"
EMPTY_PV = "pvc-6acefa9c-7859_pm_axone-router-coredump-pvc"
LISTING = f"""F 282627 {T0 + 26} {HANDLER_NAME}
F 10 {T0 - 100} core.systemd-journal.pid1.sig6.usr0.grp0.time{T0 - 100}.gz
F notanumber 1 core.bad
F 5 5 /etc/passwd
garbage line
D {PV_DIR}
F 77 {T0 + 500} {PV_DIR}/dump file with spaces
D {EMPTY_PV}
P | /bin/bash /axone/bin/coredump_handler.sh %e %p %s %u %g %t
L 1
S 301264192 145119176
"""


def test_parse_listing_files_and_host_config():
    files, cfg = parse_listing(LISTING)
    assert [f.path for f in files] == [
        f"{PV_DIR}/dump file with spaces",  # newest first (mtime fallback)
        HANDLER_NAME,
        f"core.systemd-journal.pid1.sig6.usr0.grp0.time{T0 - 100}.gz",
    ]
    assert cfg.core_pattern.startswith("| /bin/bash /axone/bin/coredump_handler.sh")
    assert cfg.core_pipe_limit == "1"
    assert cfg.disk_total_bytes == 301264192 * 1024
    assert cfg.disk_available_bytes == 145119176 * 1024
    assert cfg.coredump_pvc_dirs == {PV_DIR: 1, EMPTY_PV: 0}


def test_parse_empty_listing():
    files, cfg = parse_listing("P \nL \n")
    assert files == [] and cfg.core_pattern is None and cfg.core_pipe_limit is None


# --- selection --------------------------------------------------------------------


def _files(*specs):
    """specs: (process, epoch, size)"""
    return [
        parse_core_file(f"core.{p}.pid1.sig6.usr0.grp0.time{t}.gz", size, t)
        for p, t, size in specs
    ]


def test_select_since_and_process_filters():
    files = _files(("a", 100, 1), ("b", 200, 1), ("a", 300, 1))
    since = datetime.fromtimestamp(150, tz=timezone.utc).replace(tzinfo=None)  # naive = UTC
    selected = select_files(files, CoreDumpParams(since=since, processes=["a"]))
    assert [f.time_utc.timestamp() for f in selected] == [300]


def test_select_has_no_size_cap():
    gb = 1024 * 1024 * 1024
    files = _files(("a", 100, 5 * gb), ("a", 200, 10 * gb), ("a", 300, gb))
    selected = select_files(files, CoreDumpParams())
    assert [int(f.time_utc.timestamp()) for f in selected] == [300, 200, 100]


# --- Job manifest -------------------------------------------------------------------


def test_job_is_locked_down():
    config = CoreDumpConfig(node_name="node-1")
    job = build_collector_job(config)
    pod = job.spec.template.spec
    c = pod.containers[0]
    assert job.metadata.namespace == "iomt-integration"
    assert job.metadata.name.startswith("core-dump-collector-")
    assert job.spec.active_deadline_seconds == config.job_deadline_seconds
    assert job.spec.ttl_seconds_after_finished and job.spec.backoff_limit == 0
    assert pod.node_name == "node-1" and pod.automount_service_account_token is False
    assert pod.volumes[0].host_path.path == "/var/log/files"
    assert c.volume_mounts[0].read_only is True
    sc = c.security_context
    assert sc.privileged is None and sc.allow_privilege_escalation is False
    assert sc.read_only_root_filesystem is True
    assert sc.capabilities.drop == ["ALL"] and sc.capabilities.add == ["DAC_READ_SEARCH"]
    # The namespace quota rejects pods without requests and limits.
    assert set(c.resources.requests) == {"cpu", "memory"}
    assert set(c.resources.limits) == {"cpu", "memory"}


# --- exec streaming ---------------------------------------------------------------


class _FakeSock:
    def __init__(self, frames):
        self.frames = list(frames)

    def settimeout(self, _):
        pass

    def recv_data_frame(self, _):
        if not self.frames:
            return ABNF.OPCODE_CLOSE, SimpleNamespace(data=b"")
        channel, payload = self.frames.pop(0)
        return ABNF.OPCODE_BINARY, SimpleNamespace(data=bytes([channel]) + payload)


def _fake_ws(frames):
    return SimpleNamespace(sock=_FakeSock(frames), close=lambda: None)


SUCCESS = json.dumps({"metadata": {}, "status": "Success"}).encode()


def test_exec_streams_stdout_to_sink(monkeypatch):
    monkeypatch.setattr(
        job_exec_mod,
        "stream",
        lambda *a, **k: _fake_ws([(1, b"abc"), (2, b"warn"), (1, b"def"), (3, SUCCESS)]),
    )
    sink, seen = io.BytesIO(), []
    exec_to_sink(MagicMock(), "pod", "ns", "c", ["cat"], sink, 10, on_bytes=seen.append)
    assert sink.getvalue() == b"abcdef" and seen == [3, 3]


def test_exec_failure_status_raises_with_stderr(monkeypatch):
    failure = json.dumps({"status": "Failure", "message": "command terminated with non-zero exit code"})
    monkeypatch.setattr(
        job_exec_mod,
        "stream",
        lambda *a, **k: _fake_ws([(2, b"cat: no such file"), (3, failure.encode())]),
    )
    with pytest.raises(JobExecError, match="non-zero exit.*no such file"):
        exec_to_sink(MagicMock(), "pod", "ns", "c", ["cat"], io.BytesIO(), 10)


def test_exec_output_limit(monkeypatch):
    monkeypatch.setattr(
        job_exec_mod, "stream", lambda *a, **k: _fake_ws([(1, b"x" * 10), (3, SUCCESS)])
    )
    with pytest.raises(JobExecError, match="exceeded"):
        exec_to_sink(MagicMock(), "pod", "ns", "c", ["cat"], io.BytesIO(), 10, limit_bytes=5)


# --- session lifecycle ---------------------------------------------------------------


def _pod(phase="Pending", waiting=None):
    cs = SimpleNamespace(state=SimpleNamespace(waiting=waiting))
    return SimpleNamespace(
        metadata=SimpleNamespace(name="core-dump-collector-x-abc"),
        spec=SimpleNamespace(node_name="node-1"),
        status=SimpleNamespace(phase=phase, container_statuses=[cs], conditions=[]),
    )


def _k8s(pods):
    core, batch = MagicMock(), MagicMock()
    batch.create_namespaced_job.return_value = SimpleNamespace(
        metadata=SimpleNamespace(name="core-dump-collector-x")
    )
    core.list_namespaced_pod.side_effect = [SimpleNamespace(items=[p]) for p in pods]
    return core, batch


def test_session_waits_for_running_and_always_deletes_job():
    core, batch = _k8s([_pod("Pending"), _pod("Running")])
    with CollectorSession(core, batch, CoreDumpConfig(), sleep=lambda _: None) as s:
        assert s.pod_name == "core-dump-collector-x-abc" and s.node_name == "node-1"
        batch.delete_namespaced_job.assert_not_called()
    batch.delete_namespaced_job.assert_called_once()


def test_session_fails_fast_on_image_pull_and_deletes_job():
    waiting = SimpleNamespace(reason="ErrImageNeverPull", message="not on node")
    core, batch = _k8s([_pod("Pending", waiting)])
    with pytest.raises(CoreDumpCollectionError, match="ErrImageNeverPull"):
        with CollectorSession(core, batch, CoreDumpConfig(), sleep=lambda _: None):
            pass
    batch.delete_namespaced_job.assert_called_once()


# --- packaging ---------------------------------------------------------------------


class FakeSession:
    """Stands in for CollectorSession: serves files from a dict."""

    def __init__(self, contents, corrupt=(), fail_enter=None):
        self.contents = contents
        self.corrupt = set(corrupt)
        self.fail_enter = fail_enter
        self.pod_name = "core-dump-collector-x-abc"
        self.node_name = "node-1"
        self.exited = False

    def __call__(self, core, batch, config):
        return self

    def __enter__(self):
        if self.fail_enter:
            raise self.fail_enter
        return self

    def __exit__(self, *exc):
        self.exited = True

    def list_files(self):
        lines = [f"F {len(d)} {T0} {p}" for p, d in self.contents.items()]
        return parse_listing("\n".join(lines) + "\nP |handler\nL 1\n")

    def remote_sha256(self, path):
        return hashlib.sha256(self.contents[path]).hexdigest()

    def fetch(self, path, sink, on_bytes=None):
        data = self.contents[path]
        if path in self.corrupt:
            data = data[:-1] + b"!"
        sink.write(data)
        if on_bytes:
            on_bytes(len(data))
        return hashlib.sha256(data).hexdigest(), len(data)


@pytest.fixture
def progress():
    tracker.try_begin([ServiceProgress(id=CORE_DUMPS_SERVICE_ID, label="Core Dumps", unit="MB")])
    yield
    tracker.reset()


def _collect(session, params=None):
    buf = io.BytesIO()
    manifest = LogCollectionManifest(timestamp_utc="t", total_logs_collected=0)
    with zipfile.ZipFile(buf, "w") as zf:
        collect_core_dumps_into(
            zf, manifest, MagicMock(), MagicMock(), params or CoreDumpParams(),
            session_factory=session,
        )
    buf.seek(0)
    return zipfile.ZipFile(buf), manifest


A = "core.a.pid1.sig11.usr0.grp0.time100.gz"
B = "core.b.pid2.sig6.usr0.grp0.time200"


def test_collects_files_verified_and_stored(progress):
    session = FakeSession({A: b"\x1f\x8b gz bytes", B: b"raw core"})
    zf, manifest = _collect(session)
    assert zf.read(f"core-dumps/{A}") == b"\x1f\x8b gz bytes"
    assert zf.getinfo(f"core-dumps/{A}").compress_type == zipfile.ZIP_STORED
    assert zf.getinfo(f"core-dumps/{B}").compress_type == zipfile.ZIP_DEFLATED
    summary = json.loads(zf.read(SUMMARY_PATH))
    assert summary["available_count"] == 2 and summary["host_config"]["core_pipe_limit"] == "1"
    assert {r["status"] for r in summary["collected"]} == {"collected"}
    assert manifest.services[0].status == "done" and manifest.errors == []
    assert SUMMARY_PATH in manifest.collected_files
    assert session.exited


def test_checksum_mismatch_skips_file_but_keeps_others(progress):
    session = FakeSession({A: b"aaaa", B: b"bbbb"}, corrupt={A})
    zf, manifest = _collect(session)
    assert f"core-dumps/{A}" not in zf.namelist()
    assert zf.read(f"core-dumps/{B}") == b"bbbb"
    summary = json.loads(zf.read(SUMMARY_PATH))
    bad = next(r for r in summary["collected"] if r["file"]["path"] == A)
    assert bad["status"] == "error" and "Checksum mismatch" in bad["error"]
    assert manifest.services[0].status == "done"
    assert "1 core file(s)" in manifest.services[0].error
    assert manifest.errors[0].container == A


def test_filters_reach_the_package(progress):
    zf, _ = _collect(FakeSession({A: b"a", B: b"b"}), CoreDumpParams(processes=["b"]))
    assert [n for n in zf.namelist() if n != SUMMARY_PATH] == [f"core-dumps/{B}"]


def test_collector_failure_is_recorded_not_raised(progress):
    session = FakeSession({}, fail_enter=CoreDumpCollectionError("quota exceeded"))
    zf, manifest = _collect(session)
    assert zf.namelist() == [SUMMARY_PATH]
    assert manifest.services[0].status == "error"
    assert manifest.services[0].error == "quota exceeded"
    assert tracker.snapshot()["services"][0]["status"] == "error"


def test_no_cores_is_a_clean_success(progress):
    zf, manifest = _collect(FakeSession({}))
    assert zf.namelist() == [SUMMARY_PATH]
    assert manifest.services[0].status == "done" and manifest.services[0].error is None


# --- endpoints ----------------------------------------------------------------------

api = TestClient(app)


def _no_k8s():
    app.dependency_overrides.clear()
    from app.core.k8s_client import get_batch_v1_api, get_core_v1_api

    app.dependency_overrides[get_core_v1_api] = lambda: MagicMock()
    app.dependency_overrides[get_batch_v1_api] = lambda: MagicMock()


@pytest.fixture
def no_k8s():
    _no_k8s()
    yield
    app.dependency_overrides.clear()


def test_list_endpoint_returns_files(no_k8s, monkeypatch):
    import app.core_dumps.router as router_mod
    from app.core_dumps.schemas import CoreDumpListResponse

    monkeypatch.setattr(
        router_mod,
        "list_core_dumps",
        lambda core, batch: CoreDumpListResponse(
            files=[parse_core_file(A, 3, 100)], total_bytes=3,
            host_config=HostCoreConfig(core_pipe_limit="1"), host_dir="/var/log/files",
        ),
    )
    resp = api.get("/api/core-dumps")
    assert resp.status_code == 200
    body = resp.json()
    assert body["files"][0]["process"] == "a" and body["files"][0]["signal_name"] == "SIGSEGV"


def test_list_endpoint_503_when_collector_fails(no_k8s, monkeypatch):
    import app.core_dumps.router as router_mod

    def boom(core, batch):
        raise CoreDumpCollectionError("Collector pod cannot start: ErrImagePull")

    monkeypatch.setattr(router_mod, "list_core_dumps", boom)
    resp = api.get("/api/core-dumps")
    assert resp.status_code == 503 and "ErrImagePull" in resp.json()["detail"]


def test_zip_endpoint_passes_core_dump_filters(no_k8s, monkeypatch):
    import app.log_collection.router as logs_router

    seen = {}

    def fake_collect(**kwargs):
        seen.update(kwargs)
        f = io.BytesIO(b"PK")
        return f

    monkeypatch.setattr(logs_router, "collect_diagnostics", fake_collect)
    resp = api.get(
        "/api/logs/zip?services=core-dumps&core_since=2026-11-01T00:00:00Z"
        "&core_process=xGate&core_process=systemd-journal"
    )
    assert resp.status_code == 200
    assert seen["services"] == ["core-dumps"]
    p = seen["core_dump_params"]
    assert p.processes == ["xGate", "systemd-journal"]
    assert p.since == datetime(2026, 11, 1, tzinfo=timezone.utc)


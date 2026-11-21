"""Prometheus TSDB export: listing, time selection, packaging and endpoints.

The Kubernetes client and collector pod are faked; the listing shell script is
run for real against a fake data directory.
"""

import hashlib
import io
import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from app.core_dumps.collector import build_collector_job
from app.log_collection.progress import PROMETHEUS_SERVICE_ID, ServiceProgress, tracker
from app.log_collection.schemas import LogCollectionManifest
from app.main import app
from app.prometheus.collector import PrometheusCollectionError
from app.prometheus.config import PrometheusConfig
from app.prometheus.parsing import LISTING_SCRIPT, coverage, parse_listing, select
from app.prometheus.schemas import PrometheusParams
from app.prometheus.service import SUMMARY_PATH, collect_prometheus_into
from fastapi.testclient import TestClient

H = 3600 * 1000
T0 = 1794441600000  # 2026-11-12T00:00:00Z in ms
ULID_A = "01JCA0000000000000000000AA"  # 00:00-02:00
ULID_B = "01JCB0000000000000000000BB"  # 02:00-04:00
DATA = "pvc-1234_monitoring_prometheus-db/prometheus-db"


def _utc(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _meta(ulid, start, end):
    return json.dumps(
        {"ulid": ulid, "minTime": start, "maxTime": end, "stats": {"numSamples": 7}}
    )


LISTING = "\n".join(
    [
        f"M ./{DATA}/{ULID_A} {_meta(ULID_A, T0, T0 + 2 * H)}",
        f"F 100 ./{DATA}/{ULID_A}/meta.json",
        f"F 2000 ./{DATA}/{ULID_A}/chunks/000001",
        f"M ./{DATA}/{ULID_B} {_meta(ULID_B, T0 + 2 * H, T0 + 4 * H)}",
        f"F 3000 ./{DATA}/{ULID_B}/index",
        # In-flight compaction output and garbage meta are ignored.
        f"M ./{DATA}/{ULID_B}.tmp-for-creation {_meta(ULID_B, 0, 1)}",
        f"F 9 ./{DATA}/{ULID_B}.tmp-for-creation/index",
        f"M ./{DATA}/01JCC0000000000000000000CC not-json",
        f"H ./{DATA}",
        f"F 500 ./{DATA}/wal/00000003",
        f"F 50 ./{DATA}/chunks_head/000001",
        "F 1 ../escape",
    ]
)


# --- listing ----------------------------------------------------------------------


def test_parse_listing_blocks_and_head():
    (d,) = parse_listing(LISTING)
    assert d.path == DATA
    assert [b.ulid for b in d.blocks] == [ULID_A, ULID_B]
    a = d.blocks[0]
    assert (a.min_time, a.max_time) == (_utc(T0), _utc(T0 + 2 * H))
    assert a.size_bytes == 2100 and a.num_samples == 7
    assert [f.path for f in a.files] == [f"{DATA}/{ULID_A}/meta.json", f"{DATA}/{ULID_A}/chunks/000001"]
    assert d.head.size_bytes == 550 and d.head.min_time == _utc(T0 + 4 * H)


def test_listing_script_runs_against_a_real_tree(tmp_path):
    if not shutil.which("sh") or not shutil.which("stat"):
        pytest.skip("needs sh and stat")
    root = tmp_path / "pvc-1_monitoring_prom" / "prometheus-db"
    block = root / ULID_A
    (block / "chunks").mkdir(parents=True)
    (block / "meta.json").write_text(json.dumps(json.loads(_meta(ULID_A, T0, T0 + 2 * H)), indent=2))
    (block / "index").write_bytes(b"i" * 10)
    (block / "chunks" / "000001").write_bytes(b"c" * 20)
    (root / "wal").mkdir()
    (root / "wal" / "00000001").write_bytes(b"w" * 5)
    (root / "queries.active").write_bytes(b"q")
    out = subprocess.run(
        ["sh", "-c", f'cd "$1" && {LISTING_SCRIPT}', "sh", str(tmp_path), "5"],
        capture_output=True, text=True, check=True,
    ).stdout
    (d,) = parse_listing(out)
    assert d.path == "pvc-1_monitoring_prom/prometheus-db"
    assert d.blocks[0].ulid == ULID_A and d.blocks[0].size_bytes == len((block / "meta.json").read_bytes()) + 30
    assert [f.path for f in d.head.files] == [f"{d.path}/wal/00000001"]


def test_data_dir_at_the_mount_root():
    (d,) = parse_listing(
        f"M ./{ULID_A} {_meta(ULID_A, T0, T0 + H)}\nF 1 ./{ULID_A}/index\nH .\nF 2 ./wal/00000001\n"
    )
    assert d.path == "." and d.blocks[0].files[0].path == f"{ULID_A}/index"
    assert d.head.files[0].path == "wal/00000001"


# --- selection -------------------------------------------------------------------


def _pick(since=None, until=None):
    blocks, heads = select(
        parse_listing(LISTING),
        PrometheusParams(since=since and _utc(since), until=until and _utc(until)),
    )
    return [b.ulid for b in blocks], bool(heads)


def test_everything_when_unbounded():
    assert _pick() == ([ULID_A, ULID_B], True)


def test_since_drops_older_blocks_and_keeps_head():
    assert _pick(since=T0 + 3 * H) == ([ULID_B], True)
    # maxTime is exclusive: a block ending exactly at `since` is not needed.
    assert _pick(since=T0 + 2 * H) == ([ULID_B], True)


def test_past_window_excludes_head():
    assert _pick(since=T0 + H, until=T0 + H + 1) == ([ULID_A], False)
    assert _pick(since=T0 + H, until=T0 + 3 * H) == ([ULID_A, ULID_B], False)


def test_window_after_last_block_is_head_only():
    assert _pick(since=T0 + 5 * H) == ([], True)


def test_coverage_rounds_out_to_blocks():
    dirs = parse_listing(LISTING)
    blocks, heads = select(dirs, PrometheusParams(since=_utc(T0 + H), until=_utc(T0 + H + 1)))
    assert coverage(blocks, heads) == (_utc(T0), _utc(T0 + 2 * H))
    blocks, heads = select(dirs, PrometheusParams())
    assert coverage(blocks, heads) == (_utc(T0), None)


# --- Job -------------------------------------------------------------------------


def test_job_reuses_locked_down_collector():
    job = build_collector_job(PrometheusConfig(host_dir="/data/prom"))
    pod = job.spec.template.spec
    assert job.metadata.name.startswith("prometheus-collector-")
    assert pod.volumes[0].host_path.path == "/data/prom"
    assert pod.containers[0].volume_mounts[0].read_only is True
    assert pod.automount_service_account_token is False


# --- packaging -------------------------------------------------------------------


class FakeSession:
    """Serves the listing; each file's content is its size in bytes of "x".

    `listings` (optional) are returned by successive list_data_dirs() calls, to
    simulate Prometheus changing the data dir mid-collection."""

    def __init__(self, listing, corrupt=(), fail_enter=None, listings=None, gone=()):
        self.listing = listing
        self.listings = list(listings or [])
        self.gone = set(gone)
        self.sizes = {
            f.path: f.size_bytes
            for d in parse_listing("\n".join([listing, *self.listings]))
            for unit in [*d.blocks, *([d.head] if d.head else [])]
            for f in unit.files
        }
        self.fetches = []
        self.corrupt = set(corrupt)
        self.fail_enter = fail_enter
        self.pod_name = "prometheus-collector-x-abc"
        self.node_name = "node-1"
        self.hashed = []

    def __call__(self, core, batch, config):
        return self

    def __enter__(self):
        if self.fail_enter:
            raise self.fail_enter
        return self

    def __exit__(self, *exc):
        pass

    def list_data_dirs(self):
        if self.listings and getattr(self, "_listed", False):
            self.listing = self.listings.pop(0)
        self._listed = True
        return parse_listing(self.listing)

    def _data(self, path):
        return b"x" * self.sizes[path]

    def remote_sha256(self, path):
        self.hashed.append(path)
        return hashlib.sha256(self._data(path)).hexdigest()

    def fetch(self, path, sink, on_bytes=None):
        self.fetches.append(path)
        if path in self.gone:
            raise PrometheusCollectionError(f"cat: can't open './{path}': No such file or directory")
        data = self._data(path) + (b"!" if path in self.corrupt else b"")
        sink.write(data)
        if on_bytes:
            on_bytes(len(data))
        return hashlib.sha256(data).hexdigest(), len(data)


@pytest.fixture
def progress():
    tracker.try_begin([ServiceProgress(id=PROMETHEUS_SERVICE_ID, label="Prometheus", unit="MB")])
    yield
    tracker.reset()


def _collect(session, params=None):
    buf = io.BytesIO()
    manifest = LogCollectionManifest(timestamp_utc="t", total_logs_collected=0)
    with zipfile.ZipFile(buf, "w") as zf:
        collect_prometheus_into(
            zf, manifest, MagicMock(), MagicMock(), params or PrometheusParams(),
            config=PrometheusConfig(), session_factory=session,
        )
    buf.seek(0)
    return zipfile.ZipFile(buf), manifest


def test_packages_selected_blocks_and_head(progress):
    session = FakeSession(LISTING)
    zf, manifest = _collect(session, PrometheusParams(since=_utc(T0 + 3 * H)))
    names = set(zf.namelist())
    assert f"prometheus/{DATA}/{ULID_B}/index" in names
    assert f"prometheus/{DATA}/wal/00000003" in names
    assert not any(ULID_A in n for n in names)
    assert zf.getinfo(f"prometheus/{DATA}/wal/00000003").compress_type == zipfile.ZIP_STORED
    # Block files are checksummed; live head files can't be.
    assert session.hashed == [f"{DATA}/{ULID_B}/index"]
    summary = json.loads(zf.read(SUMMARY_PATH))
    assert summary["selected_bytes"] == 3550 and summary["available_bytes"] == 5650
    assert [b["ulid"] for b in summary["data_dirs"][0]["blocks"]] == [ULID_B]
    assert manifest.services[0].status == "done" and manifest.errors == []


def test_checksum_mismatch_skips_file_but_keeps_others(progress):
    bad = f"{DATA}/{ULID_A}/chunks/000001"
    session = FakeSession(LISTING, corrupt={bad})
    zf, manifest = _collect(session)
    assert f"prometheus/{bad}" not in zf.namelist()
    assert f"prometheus/{DATA}/{ULID_B}/index" in zf.namelist()
    # The whole block is left out (a block missing a chunk file won't load),
    # after retrying the damaged file.
    assert not any(ULID_A in n for n in zf.namelist())
    assert session.fetches.count(bad) == 3
    assert manifest.errors[0].container == f"{DATA}/{ULID_A}"


def test_no_prometheus_data_is_an_error(progress):
    zf, manifest = _collect(FakeSession(""))
    assert manifest.services[0].status == "error"
    assert "PROMETHEUS_HOST_DIR" in manifest.services[0].error
    assert zf.namelist() == [SUMMARY_PATH]


def test_collector_failure_is_recorded_not_raised(progress):
    _, manifest = _collect(FakeSession("", fail_enter=PrometheusCollectionError("quota")))
    assert manifest.services[0].error == "quota"
    assert tracker.snapshot()["services"][0]["status"] == "error"


# --- endpoints -------------------------------------------------------------------

api = TestClient(app)


@pytest.fixture
def no_k8s():
    from app.core.k8s_client import get_batch_v1_api, get_core_v1_api

    app.dependency_overrides[get_core_v1_api] = lambda: MagicMock()
    app.dependency_overrides[get_batch_v1_api] = lambda: MagicMock()
    yield
    app.dependency_overrides.clear()


def test_zip_endpoint_passes_prometheus_window(no_k8s, monkeypatch):
    import app.log_collection.router as logs_router

    seen = {}
    monkeypatch.setattr(
        logs_router, "collect_diagnostics", lambda **kw: seen.update(kw) or io.BytesIO(b"PK")
    )
    resp = api.get(
        "/api/logs/zip?services=prometheus"
        "&prom_since=2026-11-01T00:00:00Z&prom_until=2026-11-02T00:00:00Z"
    )
    assert resp.status_code == 200 and seen["services"] == ["prometheus"]
    p = seen["prometheus_params"]
    assert p.since == datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert p.until - p.since == timedelta(days=1)


# --- packages kept on disk ---------------------------------------------------------


def test_package_is_built_on_disk_and_downloaded(no_k8s, monkeypatch, tmp_path):
    import app.log_collection.router as logs_router

    monkeypatch.setenv("IOMT_WORK_DIR", str(tmp_path))

    def fake_collect(out=None, **kw):
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("manifest.json", "{}")
            zf.writestr("prometheus/prometheus.json", "{}")
        return out

    monkeypatch.setattr(logs_router, "collect_diagnostics", fake_collect)
    first = api.post("/api/logs/packages?services=prometheus").json()
    body = api.post("/api/logs/packages?services=prometheus").json()
    # Only the latest package is kept.
    assert len(list((tmp_path / "packages").iterdir())) == 1
    assert api.get(first["url"]).status_code == 404

    resp = api.get(body["url"])
    assert resp.status_code == 200 and body["url"] == f"/api/logs/packages/{body['id']}"
    assert int(resp.headers["content-length"]) == body["size_bytes"]
    assert body["filename"] in resp.headers["content-disposition"]
    assert zipfile.ZipFile(io.BytesIO(resp.content)).read("prometheus/prometheus.json") == b"{}"


def test_failed_package_is_not_left_on_disk(no_k8s, monkeypatch, tmp_path):
    import app.log_collection.router as logs_router

    monkeypatch.setenv("IOMT_WORK_DIR", str(tmp_path))

    def boom(out=None, **kw):
        raise ValueError("Unsupported diagnostic service: x")

    monkeypatch.setattr(logs_router, "collect_diagnostics", boom)
    assert api.post("/api/logs/packages?services=prometheus").status_code == 422
    assert list((tmp_path / "packages").iterdir()) == []


def test_damaged_transfer_is_retried(progress):
    bad = f"{DATA}/{ULID_A}/chunks/000001"

    class FlakyOnce(FakeSession):
        def fetch(self, path, sink, on_bytes=None):
            if path == bad and bad not in self.fetches:
                self.fetches.append(path)
                sink.write(b"x")  # stream cut short
                return hashlib.sha256(b"x").hexdigest(), 1
            return super().fetch(path, sink, on_bytes)

    zf, manifest = _collect(FlakyOnce(LISTING))
    assert len(zf.read(f"prometheus/{bad}")) == 2000
    assert manifest.errors == [] and manifest.services[0].error is None


ULID_C = "01JCC0000000000000000000CC"  # 04:00-06:00, cut from the head mid-collection
COMPACTED = "\n".join(
    [
        f"M ./{DATA}/{ULID_A} {_meta(ULID_A, T0, T0 + 2 * H)}",
        f"F 100 ./{DATA}/{ULID_A}/meta.json",
        f"F 2000 ./{DATA}/{ULID_A}/chunks/000001",
        f"M ./{DATA}/{ULID_B} {_meta(ULID_B, T0 + 2 * H, T0 + 4 * H)}",
        f"F 3000 ./{DATA}/{ULID_B}/index",
        f"M ./{DATA}/{ULID_C} {_meta(ULID_C, T0 + 4 * H, T0 + 6 * H)}",
        f"F 70 ./{DATA}/{ULID_C}/index",
        f"H ./{DATA}",
        f"F 40 ./{DATA}/wal/00000004",
    ]
)


def test_head_compacted_mid_collection_picks_up_new_block_and_new_wal(progress):
    # The first listing's WAL segment is gone by the time it's copied; the
    # re-listing shows the block it became and the new segment.
    session = FakeSession(
        LISTING, listings=[LISTING, COMPACTED], gone={f"{DATA}/wal/00000003"}
    )
    zf, manifest = _collect(session)
    assert f"{DATA}/wal/00000003" in session.fetches  # tried, vanished, re-listed
    names = set(zf.namelist())
    assert f"prometheus/{DATA}/{ULID_C}/index" in names
    assert f"prometheus/{DATA}/wal/00000004" in names
    assert f"prometheus/{DATA}/wal/00000003" not in names
    assert manifest.errors == [] and manifest.services[0].status == "done"
    summary = json.loads(zf.read(SUMMARY_PATH))
    assert [b["ulid"] for b in summary["data_dirs"][0]["blocks"]] == [ULID_A, ULID_B, ULID_C]


def test_block_merged_mid_collection_is_not_copied_twice(progress):
    merged = "01JCD0000000000000000000DD"
    relisted = LISTING.replace(f"M ./{DATA}/{ULID_B}", f"M ./{DATA}/IGNORED") + "\n" + "\n".join(
        [
            f"M ./{DATA}/{merged} "
            + json.dumps({"minTime": T0, "maxTime": T0 + 4 * H,
                          "compaction": {"sources": [ULID_A, ULID_B]}}),
            f"F 10 ./{DATA}/{merged}/index",
        ]
    )
    zf, _ = _collect(FakeSession(LISTING, listings=[relisted]))
    assert not any(merged in n for n in zf.namelist())

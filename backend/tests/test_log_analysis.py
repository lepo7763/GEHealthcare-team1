import io
import json
import zipfile
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from kubernetes import client

from app.main import app
from app.core.k8s_client import get_core_v1_api
from app.log_analysis.service import classify_line, normalize_error

test_client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_zip(files: dict[str, str]) -> bytes:
    """Builds an in-memory zip shaped like the one GET /api/logs/zip returns."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


def upload(data: bytes, filename="logs.zip"):
    return test_client.post(
        "/api/analysis/zip", files={"file": (filename, data, "application/zip")}
    )


# ---------------------------------------------------------------------------
# 1. Line classification (the core rule everything else depends on)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "2026-10-03T21:10:23.197Z ERROR Failed to connect to database",
        "2026-10-03T21:10:23.197Z [FATAL] out of memory",
        'level=error msg="leaderelection lost for k3s-etcd"',
        '{"level":"error","msg":"apply request took too long"}',
        "E1003 21:10:23.197077   12600 finisher.go:175] Unhandled Error",
        "java.lang.NullPointerException: calibration data was null",
        "Traceback (most recent call last):",
    ],
)
def test_error_lines_are_detected_across_log_styles(line):
    assert classify_line(line) == "error"


@pytest.mark.parametrize(
    "line",
    [
        "2026-10-03T21:10:23.197Z WARN disk usage at 85%",
        '{"level":"warn","msg":"apply request took too long","took":"1.47s"}',
        "W1003 21:13:50.346400    6877 reflector.go:561] watch closed",
    ],
)
def test_warning_lines_are_detected(line):
    assert classify_line(line) == "warning"


@pytest.mark.parametrize(
    "line",
    [
        "2026-10-03T21:10:23.197Z INFO Service started successfully",
        "Processed 120 requests, 0 errors",  # lowercase "errors" is not a failure
        "error rate is 0.1%",
        "",
    ],
)
def test_normal_lines_are_not_flagged(line):
    assert classify_line(line) is None


def test_normalize_groups_errors_that_differ_only_by_ids_and_numbers():
    a = normalize_error(
        "2026-10-03T21:10:23Z ERROR timeout after 1500ms calling 10.0.0.5:8080 "
        "for device d4e5f6a7-1234-5678-9abc-def012345678"
    )
    b = normalize_error(
        "2026-10-03T22:44:01Z ERROR timeout after 900ms calling 10.0.0.7:8080 "
        "for device a1b2c3d4-aaaa-bbbb-cccc-123456789abc"
    )
    assert a == b
    assert a == "ERROR timeout after <DURATION> calling <IP> for device <UUID>"


def test_normalize_groups_klog_lines_with_different_durations():
    """Real k3s output from the lab MiniEdge: same failure, different PID/time/duration."""
    a = normalize_error(
        'E1003 21:10:23.197077   12600 finisher.go:175] "Unhandled Error" '
        'err="time-elapsed: 1m46.687493817s, err: context deadline exceeded"'
    )
    b = normalize_error(
        'E1003 21:02:15.400100   11800 finisher.go:175] "Unhandled Error" '
        'err="time-elapsed: 15.2s, err: context deadline exceeded"'
    )
    assert a == b
    assert "k3s" in normalize_error('level=fatal msg="leaderelection lost for k3s-etcd"')


def test_pattern_example_is_a_line_that_matched_that_pattern():
    data = make_zip(
        {
            "logs/ns/pod/app.log": (
                "ERROR first problem\n"
                "FATAL second problem\n"
            )
        }
    )

    report = upload(data).json()

    examples = {p["example"] for p in report["top_errors"]}
    assert examples == {"ERROR first problem", "FATAL second problem"}


# ---------------------------------------------------------------------------
# 2. Endpoint: happy path
# ---------------------------------------------------------------------------


def test_report_counts_and_ranks_noisiest_container_first():
    data = make_zip(
        {
            "manifest.json": json.dumps(
                {"timestamp_utc": "2026-10-16T15:00:00+00:00", "errors": []}
            ),
            "logs/compute/apigateway/kong.log": (
                "2026-10-16T14:00:00Z INFO started\n"
                "2026-10-16T14:00:01Z ERROR upstream timed out\n"
                "2026-10-16T14:00:02Z ERROR upstream timed out\n"
                "2026-10-16T14:00:03Z WARN retrying\n"
            ),
            "logs/kube-system/coredns/coredns.log": "2026-10-16T14:00:00Z INFO ready\n",
        }
    )

    response = upload(data)

    assert response.status_code == 200
    report = response.json()
    assert report["collected_at"] == "2026-10-16T15:00:00+00:00"
    assert report["files_analyzed"] == 2
    assert report["total_lines"] == 5
    assert report["error_lines"] == 2
    assert report["warning_lines"] == 1

    top = report["containers"][0]
    assert (top["namespace"], top["pod"], top["container"]) == (
        "compute",
        "apigateway",
        "kong",
    )
    assert top["first_error"] == "ERROR upstream timed out"

    assert report["top_errors"][0]["count"] == 2
    assert report["top_errors"][0]["containers"] == ["compute/apigateway/kong"]


def test_previous_logs_mark_container_as_crashed():
    data = make_zip(
        {
            "logs/iomt/monitor/api.log": "INFO back up\n",
            "logs/iomt/monitor/api_previous.log": "FATAL: OutOfMemory before crash\n",
        }
    )

    report = upload(data).json()

    assert report["crashed_containers"] == ["iomt/monitor/api"]
    previous = [c for c in report["containers"] if c["is_previous"]]
    assert len(previous) == 1 and previous[0]["container"] == "api"


def test_collection_errors_from_manifest_are_passed_through():
    """Containers the collector could not reach are still worth showing to the engineer."""
    failed = {
        "namespace": "iomt",
        "pod": "pending",
        "container": "c1",
        "reason": "ContainerCreating",
        "status": 400,
    }
    data = make_zip(
        {
            "manifest.json": json.dumps({"timestamp_utc": "t", "errors": [failed]}),
            "logs/iomt/ok/c2.log": "INFO fine\n",
        }
    )

    report = upload(data).json()

    assert report["collection_errors"] == [failed]


# ---------------------------------------------------------------------------
# 3. Endpoint: bad input and edge cases
# ---------------------------------------------------------------------------


def test_non_zip_upload_returns_400():
    response = upload(b"this is not a zip", filename="notes.txt")

    assert response.status_code == 400
    assert "not a valid zip" in response.json()["detail"]


def test_zip_without_container_logs_returns_400():
    response = upload(make_zip({"README.txt": "hello"}))

    assert response.status_code == 400
    assert "No container logs found" in response.json()["detail"]


def test_unexpected_files_are_skipped_not_fatal():
    data = make_zip(
        {
            "logs/ns/pod/app.log": "ERROR boom\n",
            "logs/too/deep/path/app.log": "ERROR ignored\n",
            "notes.txt": "hi",
        }
    )

    report = upload(data).json()

    assert report["files_analyzed"] == 1
    assert len(report["skipped_files"]) == 2


def test_invalid_utf8_bytes_do_not_crash_analysis():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("logs/ns/pod/app.log", b"ERROR bad byte \xff\xfe here\n")

    report = upload(buf.getvalue()).json()

    assert report["error_lines"] == 1


def test_missing_file_field_returns_422():
    response = test_client.post("/api/analysis/zip")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. Integration: the zip from Nimit's collector feeds straight into analysis
# ---------------------------------------------------------------------------


def test_zip_from_log_collection_endpoint_can_be_analyzed():
    """
    Contract check between GET /api/logs/zip (log_collection) and POST /api/analysis/zip.
    If the collector ever changes its folder layout, this test breaks first.
    """
    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(namespace="iomt", name="hub-api"),
        spec=client.V1PodSpec(containers=[client.V1Container(name="api")]),
        status=client.V1PodStatus(
            container_statuses=[
                client.V1ContainerStatus(
                    name="api",
                    image="busybox",
                    image_id="docker://123",
                    ready=True,
                    restart_count=2,
                )
            ]
        ),
    )
    mock_api = MagicMock(spec=client.CoreV1Api)
    mock_api.list_pod_for_all_namespaces.return_value = client.V1PodList(items=[pod])

    def fake_read_log(name, namespace, container, previous=False, **kwargs):
        if previous:
            return "2026-10-16T14:00:00Z FATAL lost connection to etcd\n"
        return "2026-10-16T14:05:00Z INFO recovered\n2026-10-16T14:05:01Z WARN slow\n"

    mock_api.read_namespaced_pod_log.side_effect = fake_read_log
    app.dependency_overrides[get_core_v1_api] = lambda: mock_api
    try:
        collected = test_client.get("/api/logs/zip?throttle_delay_ms=0")
    finally:
        app.dependency_overrides.clear()
    assert collected.status_code == 200

    report = upload(collected.content).json()

    assert report["files_analyzed"] == 2
    assert report["crashed_containers"] == ["iomt/hub-api/api"]
    assert report["error_lines"] == 1
    assert report["warning_lines"] == 1
    assert report["collected_at"] is not None


# ---------------------------------------------------------------------------
# 5. Suggested actions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, title",
    [
        ('level=fatal msg="leaderelection lost for k3s-etcd"', "Lost etcd leadership"),
        ("ERROR write /var/lib: no space left on device", "Disk full"),
        ("FATAL: OutOfMemory before crash", "Out of memory"),
        ("ERROR dial tcp 10.0.0.5:8080: connection refused", "Can't reach a dependency"),
        ("ERROR upstream timed out after 60000ms", "Request timed out"),
        ("java.lang.NullPointerException: calibration data was null", "Application error"),
    ],
)
def test_known_errors_get_a_suggested_action(line, title):
    from app.log_analysis.recommendations import recommend_action

    assert recommend_action(line).title == title


def test_specific_cause_wins_over_generic_timeout():
    """etcd leader loss lines also say 'deadline exceeded'; the specific rule must win."""
    from app.log_analysis.recommendations import recommend_action

    line = "leaderelection lost for k3s-etcd: context deadline exceeded"
    assert recommend_action(line).title == "Lost etcd leadership"


def test_unknown_error_has_no_suggestion():
    report = upload(make_zip({"logs/ns/pod/app.log": "ERROR something nobody has seen\n"})).json()

    assert report["top_errors"][0]["recommendation"] is None


def test_report_includes_suggestion_for_each_known_pattern():
    report = upload(
        make_zip({"logs/ns/pod/app.log": "ERROR upstream timed out after 900ms\n"})
    ).json()

    assert report["top_errors"][0]["recommendation"]["title"] == "Request timed out"


# ---------------------------------------------------------------------------
# 6. Privacy (PHI/PII) scan
# ---------------------------------------------------------------------------


def scan(data: bytes):
    return test_client.post(
        "/api/analysis/privacy", files={"file": ("logs.zip", data, "application/zip")}
    )


def test_privacy_scan_finds_each_kind_of_identifier():
    data = make_zip(
        {
            "logs/portrait/api/web.log": (
                "INFO lookup mrn=00482913 dob=1957-03-14\n"
                'INFO {"patient_name": "Jane Doe"}\n'
                "INFO notify clinician jane.doe@hospital.org at 608-555-0142\n"
                "INFO ssn 123-45-6789\n"
            )
        }
    )

    report = scan(data).json()

    found = {c["category"]: c["count"] for c in report["categories"]}
    assert found == {"mrn": 1, "dob": 1, "name": 1, "email": 1, "phone": 1, "ssn": 1}
    assert report["total_findings"] == 6


def test_privacy_report_never_contains_the_raw_values():
    raw = ["00482913", "1957-03-14", "Jane Doe", "jane.doe@hospital.org", "608-555-0142", "123-45-6789"]
    data = make_zip(
        {
            "logs/portrait/api/web.log": (
                "mrn=00482913 dob=1957-03-14 patient_name=Jane Doe "
                "jane.doe@hospital.org 608-555-0142 123-45-6789\n"
            )
        }
    )

    body = scan(data).text

    for value in raw:
        assert value not in body
    assert "mrn=0***" in body
    assert "j***@hospital.org" in body


def test_privacy_examples_point_to_container_and_line():
    data = make_zip({"logs/ns/pod/app.log": "INFO start\nINFO mrn=12345\n"})

    example = scan(data).json()["categories"][0]["examples"][0]

    assert example["container"] == "ns/pod/app"
    assert example["line_number"] == 2


def test_normal_cluster_logs_have_no_privacy_findings():
    """Timestamps, IPs, durations and klog headers must not look like PHI."""
    data = make_zip(
        {
            "logs/kube-system/k3s/k3s.log": (
                'E1003 21:10:23.197077   12600 finisher.go:175] "Unhandled Error"\n'
                "2026-10-03T21:12:31.120Z ERROR timed out connecting to 10.42.0.17:9200 after 60000ms\n"
                "INFO took 1m46.687493817s\n"
            )
        }
    )

    report = scan(data).json()

    assert report["total_findings"] == 0


def test_privacy_scan_rejects_non_zip():
    response = scan(b"not a zip")

    assert response.status_code == 400

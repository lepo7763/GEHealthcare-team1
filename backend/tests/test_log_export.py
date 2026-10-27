import io
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.log_export import service
from app.main import app


test_client = TestClient(app)
DEVICE_UUID = "d4e5f6a7-1234-5678-9abc-def012345678"
BASE_QUERY = {
    "scope": "device",
    "format": "csv",
    "deviceuuid": DEVICE_UUID,
    "startTimestamp": "2024-01-15T09:00:00.000",
    "endTimestamp": "2024-01-15T09:45:00.000",
}


@pytest.fixture
def upstream(monkeypatch):
    """Keep requests inside the test process while exercising the full API route."""
    response = MagicMock()
    response.read.return_value = b"timeStampAndOffset,description\r\n09:12,Started\r\n"
    response.__enter__.return_value = response
    transport = MagicMock(return_value=response)
    monkeypatch.setattr(service, "urlopen", transport)
    monkeypatch.setenv(
        "AXONE_LOG_EXPORT_URL",
        "http://axone-log-export-tcp.diagnostics.svc.cluster.local:9200",
    )
    return transport, response


@pytest.mark.parametrize(
    "scope,output_format,category,path",
    [
        ("device", "json", None, "/getLogsByDevice"),
        ("device", "csv", None, "/getSpecificDeviceLogsInCSV"),
        ("device", "json", 0, "/getLogsByDeviceAndEvent"),
        ("device", "csv", 3, "/getLogsByDeviceAndEventInCsv"),
        ("all", "json", None, "/getLogsByDate"),
        ("all", "csv", None, "/getAllDeviceLogsInCSV"),
        ("all", "json", 1, "/getLogsByDateAndEvent"),
        ("all", "csv", 0, "/getLogsByDateAndEventInCsv"),
    ],
)
def test_routes_all_export_shapes_to_documented_endpoints(
    upstream, scope, output_format, category, path
):
    transport, upstream_response = upstream
    payload = (
        b'[{"description":"Service started","eventCategory":"General"}]'
        if output_format == "json"
        else b"description,eventCategory\r\nService started,General\r\n"
    )
    upstream_response.read.return_value = payload
    query = {**BASE_QUERY, "scope": scope, "format": output_format}
    if scope == "all":
        query.pop("deviceuuid")
    if category is not None:
        query["eventCategory"] = category

    response = test_client.get("/api/logs/export", params=query)

    assert response.status_code == 200, response.text
    assert response.content == payload
    expected_media_type = "application/json" if output_format == "json" else "text/csv"
    assert response.headers["content-type"].split(";")[0] == expected_media_type
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="')
    assert disposition.endswith(f'.{output_format}"')
    transport.assert_called_once()
    request = transport.call_args.args[0]
    parsed = urlsplit(request.full_url)
    assert parsed.scheme == "http"
    assert parsed.netloc == "axone-log-export-tcp.diagnostics.svc.cluster.local:9200"
    assert parsed.path == path
    expected_params = {
        "startTimestamp": [BASE_QUERY["startTimestamp"]],
        "endTimestamp": [BASE_QUERY["endTimestamp"]],
    }
    if scope == "device":
        expected_params["deviceuuid"] = [DEVICE_UUID]
    if category is not None:
        expected_params["eventCategory"] = [str(category)]
    assert parse_qs(parsed.query) == expected_params
    assert request.get_header("Accept") == expected_media_type
    assert transport.call_args.kwargs["timeout"] > 0


def test_defaults_to_device_csv_and_default_cluster_service(upstream, monkeypatch):
    transport, _ = upstream
    monkeypatch.delenv("AXONE_LOG_EXPORT_URL")
    query = {key: value for key, value in BASE_QUERY.items() if key not in {"scope", "format"}}

    response = test_client.get("/api/logs/export", params=query)

    assert response.status_code == 200
    parsed = urlsplit(transport.call_args.args[0].full_url)
    assert parsed.netloc == "axone-log-export-tcp:9200"
    assert parsed.path == "/getSpecificDeviceLogsInCSV"


def test_serializes_local_timestamps_to_milliseconds_without_timezone(upstream):
    transport, _ = upstream
    query = {
        **BASE_QUERY,
        "startTimestamp": "2024-01-15T09:00:00",
        "endTimestamp": "2024-01-15T09:45:00.12",
    }

    response = test_client.get("/api/logs/export", params=query)

    assert response.status_code == 200
    params = parse_qs(urlsplit(transport.call_args.args[0].full_url).query)
    assert params["startTimestamp"] == ["2024-01-15T09:00:00.000"]
    assert params["endTimestamp"] == ["2024-01-15T09:45:00.120"]


@pytest.mark.parametrize(
    "changes",
    [
        {"deviceuuid": "not-a-device-uuid"},
        {"deviceuuid": ""},
        {"startTimestamp": "2024-02-30T09:00:00.000"},
        {"startTimestamp": "2024-01-15"},
        {"startTimestamp": "2024-01-15T09:00:00Z"},
        {"startTimestamp": "2024-01-15T09:00:00+01:00"},
        {"endTimestamp": "2024-01-15T09:45:00Z"},
        {"endTimestamp": "2024-01-15T09:45:00-05:00"},
        {"endTimestamp": "2024-01-15T09:00:00.000"},
        {"endTimestamp": "2024-01-15T08:59:59.999"},
        {"endTimestamp": "2024-01-22T09:00:00.001"},
        {"scope": "all", "endTimestamp": "2024-01-15T10:00:00.000"},
        {"scope": "all", "endTimestamp": "2024-01-16T09:15:00.000"},
    ],
)
def test_invalid_export_parameters_are_rejected_before_upstream_request(upstream, changes):
    transport, _ = upstream

    response = test_client.get("/api/logs/export", params={**BASE_QUERY, **changes})

    assert response.status_code == 400
    assert response.json()["detail"]
    transport.assert_not_called()


def test_device_scope_requires_device_uuid(upstream):
    transport, _ = upstream
    query = {key: value for key, value in BASE_QUERY.items() if key != "deviceuuid"}

    response = test_client.get("/api/logs/export", params=query)

    assert response.status_code == 400
    assert "device" in response.json()["detail"].lower()
    transport.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "unknown"},
        {"format": "xml"},
        {"eventCategory": "Security"},
        {"eventCategory": "1.5"},
    ],
)
def test_invalid_selector_and_category_types_are_rejected(upstream, changes):
    transport, _ = upstream

    response = test_client.get("/api/logs/export", params={**BASE_QUERY, **changes})

    assert response.status_code in {400, 422}
    transport.assert_not_called()


def test_device_export_accepts_exactly_seven_days(upstream):
    response = test_client.get(
        "/api/logs/export",
        params={**BASE_QUERY, "endTimestamp": "2024-01-22T09:00:00.000"},
    )

    assert response.status_code == 200


def test_all_device_export_accepts_range_within_one_hour(upstream):
    query = {
        **BASE_QUERY,
        "scope": "all",
        "endTimestamp": "2024-01-15T09:59:59.999",
    }
    query.pop("deviceuuid")

    response = test_client.get("/api/logs/export", params=query)

    assert response.status_code == 200


def test_upstream_validation_errors_are_visible_to_the_user(upstream):
    transport, _ = upstream
    transport.side_effect = HTTPError(
        "http://axone-log-export-tcp:9200/getLogsByDeviceAndEvent",
        400,
        "Bad Request",
        {},
        io.BytesIO(b'["Unrecognized eventCategory", "Invalid timestamp Format"]'),
    )

    response = test_client.get("/api/logs/export", params={**BASE_QUERY, "eventCategory": 99})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Unrecognized eventCategory" in detail
    assert "Invalid timestamp Format" in detail


@pytest.mark.parametrize(
    "failure,expected_status",
    [
        (
            HTTPError(
                "http://axone-log-export-tcp:9200/getLogsByDate",
                500,
                "Internal Server Error",
                {},
                io.BytesIO(b"Database connection details should stay upstream"),
            ),
            502,
        ),
        (URLError("Name or service not known"), 503),
        (TimeoutError("timed out"), 504),
        (URLError(TimeoutError("timed out")), 504),
    ],
)
def test_upstream_failures_return_actionable_errors(upstream, failure, expected_status):
    transport, _ = upstream
    transport.side_effect = failure

    response = test_client.get("/api/logs/export", params=BASE_QUERY)

    assert response.status_code == expected_status
    assert response.json()["detail"]
    assert "Database connection details" not in response.text

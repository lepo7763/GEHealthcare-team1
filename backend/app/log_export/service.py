import json
import os
import re
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID


DEFAULT_EXPORT_URL = "http://axone-log-export-tcp:9200"
REQUEST_TIMEOUT_SECONDS = 60
LOCAL_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?")
ENDPOINTS = {
    ("device", "json", False): "/getLogsByDevice",
    ("device", "csv", False): "/getSpecificDeviceLogsInCSV",
    ("device", "json", True): "/getLogsByDeviceAndEvent",
    ("device", "csv", True): "/getLogsByDeviceAndEventInCsv",
    ("all", "json", False): "/getLogsByDate",
    ("all", "csv", False): "/getAllDeviceLogsInCSV",
    ("all", "json", True): "/getLogsByDateAndEvent",
    ("all", "csv", True): "/getLogsByDateAndEventInCsv",
}


class ExportError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Keep requests at the configured service, including when it returns a redirect.
urlopen = build_opener(_NoRedirect()).open


def _parse_timestamp(value: str, label: str) -> datetime:
    if not LOCAL_TIMESTAMP.fullmatch(value):
        raise ExportError(
            400,
            f"{label} must be a local date and time in YYYY-MM-DDTHH:mm:ss.SSS format, without a time zone.",
        )
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ExportError(400, f"{label} is not a valid date and time.") from exc


def validate_export(
    scope: str,
    format: str,
    start_timestamp: str,
    end_timestamp: str,
    device_uuid: str | None = None,
    event_category: int | None = None,
) -> dict[str, str | int]:
    """Validate the guide's query rules and produce Axone query parameters."""
    if scope not in {"device", "all"} or format not in {"csv", "json"}:
        raise ExportError(400, "Choose a valid device scope and export format.")

    start = _parse_timestamp(start_timestamp, "Start timestamp")
    end = _parse_timestamp(end_timestamp, "End timestamp")
    if end <= start:
        raise ExportError(400, "End time must be after start time.")

    if scope == "device":
        if end - start > timedelta(days=7):
            raise ExportError(400, "One-device exports cannot exceed 7 days.")
    else:
        if end - start > timedelta(hours=1):
            raise ExportError(400, "All-device exports cannot exceed 1 hour.")
        if start.hour != end.hour:
            raise ExportError(400, "All-device exports require start and end times within the same hour.")

    params: dict[str, str | int] = {
        "startTimestamp": start.isoformat(timespec="milliseconds"),
        "endTimestamp": end.isoformat(timespec="milliseconds"),
    }
    if scope == "device":
        try:
            params["deviceuuid"] = str(UUID(device_uuid or ""))
        except ValueError as exc:
            raise ExportError(400, "Enter a valid device UUID for a one-device export.") from exc
    if event_category is not None:
        params["eventCategory"] = event_category
    return params


def _configured_url() -> str:
    base_url = os.environ.get("AXONE_LOG_EXPORT_URL", DEFAULT_EXPORT_URL).rstrip("/")
    try:
        parsed = urlsplit(base_url)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.port != 0
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise ExportError(503, "The Axone log export service URL is not configured correctly.")
    return base_url


def _upstream_error_message(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read())
    except (ValueError, OSError):
        return "The log service rejected the export parameters. Check the time range, device UUID, and event code."
    if isinstance(payload, list) and all(isinstance(message, str) for message in payload) and payload:
        return "; ".join(payload)
    return "The log service rejected the export parameters. Check the time range, device UUID, and event code."


def fetch_export(
    scope: str,
    format: str,
    start_timestamp: str,
    end_timestamp: str,
    device_uuid: str | None = None,
    event_category: int | None = None,
) -> bytes:
    params = validate_export(scope, format, start_timestamp, end_timestamp, device_uuid, event_category)
    endpoint = ENDPOINTS[(scope, format, event_category is not None)]
    url = f"{_configured_url()}{endpoint}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "text/csv" if format == "csv" else "application/json"})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read()
    except HTTPError as exc:
        try:
            if exc.code == 400:
                raise ExportError(400, _upstream_error_message(exc)) from exc
            raise ExportError(502, "The Axone log service could not complete the export. Try again later.") from exc
        finally:
            exc.close()
    except TimeoutError as exc:
        raise ExportError(504, "The Axone log export timed out. Try a shorter time range.") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise ExportError(504, "The Axone log export timed out. Try a shorter time range.") from exc
        raise ExportError(
            503,
            "Could not reach the Axone log service. The backend must have access to the Kubernetes cluster network.",
        ) from exc
    except OSError as exc:
        raise ExportError(503, "The connection to the Axone log service was interrupted. Try again.") from exc

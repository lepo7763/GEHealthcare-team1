from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(title="IoMT Analysis Tool", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    # The raw isoformat() output ends in the "+00:00" UTC offset
    # (e.g. 2026-10-08T18:45:01.123456+00:00). We normalize that offset to a
    # trailing "Z" so the timestamp reads as a compact ISO 8601 UTC instant
    # (e.g. 2026-10-08T18:45:01.123456Z). The "Z" form is the one this API
    # guarantees and the one our tests assert against.
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"status": "ok", "timestamp": timestamp}

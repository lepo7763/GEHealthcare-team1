from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(title="IoMT Analysis Tool", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    # Normalize trailing +00:00 offset to "Z" for compact ISO 8601 UTC instant
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"status": "ok", "timestamp": timestamp}

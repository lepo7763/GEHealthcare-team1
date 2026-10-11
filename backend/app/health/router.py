from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter(prefix="/api/health", tags=["Health"])

@router.get("")
def health_check():
    # Normalize trailing +00:00 offset to "Z" for compact ISO 8601 UTC instant
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"status": "ok", "timestamp": timestamp}
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_status_is_ok():
    response = client.get("/api/health")
    assert response.json()["status"] == "ok"


def test_health_timestamp_is_valid_iso_8601():
    timestamp = client.get("/api/health").json()["timestamp"]
    # datetime.fromisoformat raises ValueError if the string is not valid
    assert datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

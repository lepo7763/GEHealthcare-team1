"""Endpoint tests for the UMF-RTI router (domain labels for the UI dropdown)."""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_list_domains_returns_labels():
    resp = client.get("/api/umf-rti/domains")
    assert resp.status_code == 200
    by_domain = {d["domain"]: d["label"] for d in resp.json()}
    # Only the cert-authorized domains are offered — no 32/34.
    assert set(by_domain) == {7, 12, 13}
    assert by_domain[13]  # non-empty label
    # 13 is listed first so it's the default option in the dropdown.
    assert resp.json()[0]["domain"] == 13

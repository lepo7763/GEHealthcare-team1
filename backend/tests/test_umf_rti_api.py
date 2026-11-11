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


# --- Query-string parsing of UmfRtiParams --------------------------------------
# /api/logs/zip takes UmfRtiParams via Depends(), so every value arrives as a
# string. A tiny app with the same dependency checks that parsing without
# starting a real collection.

import pytest
from app.umf_rti.schemas import UmfRtiParams
from fastapi import Depends, FastAPI

_params_app = FastAPI()


@_params_app.get("/params")
def _echo_params(params: UmfRtiParams = Depends()):
    return params


_params_client = TestClient(_params_app)


@pytest.mark.parametrize("domain", [7, 12, 13])
def test_allowed_domain_from_query_string_is_accepted(domain):
    # Regression: Literal[7, 12, 13] rejected the string "13" with a 422.
    resp = _params_client.get(f"/params?umf_domain_id={domain}&umf_duration_seconds=10")
    assert resp.status_code == 200
    assert resp.json() == {"umf_domain_id": domain, "umf_duration_seconds": 10}


def test_defaults_when_query_omits_umf_params():
    resp = _params_client.get("/params")
    assert resp.json() == {"umf_domain_id": 13, "umf_duration_seconds": 60}


@pytest.mark.parametrize(
    "query",
    [
        "umf_domain_id=32",
        "umf_domain_id=0",
        "umf_domain_id=abc",
        "umf_duration_seconds=9",
        "umf_duration_seconds=601",
    ],
)
def test_disallowed_umf_params_return_422(query):
    assert _params_client.get(f"/params?{query}").status_code == 422

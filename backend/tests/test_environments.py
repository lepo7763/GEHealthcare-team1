import socket
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from kubernetes import config
from kubernetes.client.exceptions import ApiException

from app.main import app

test_client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SERVICE = "app.environments.service"


def _auth_api(allowed=True, reason=None):
    """Builds a fake AuthorizationV1Api returning a SelfSubjectAccessReview result."""
    api = MagicMock()
    result = MagicMock()
    result.status.allowed = allowed
    result.status.reason = reason
    api.create_self_subject_access_review.return_value = result
    return api


def _patch_kubeconfig():
    """Patches kubeconfig loading so only the mocked auth API is exercised."""
    return (
        patch(f"{SERVICE}.config.load_kube_config"),
        patch(f"{SERVICE}.config.list_kube_config_contexts", return_value=([], None)),
    )


def _patch_auth_api(api):
    return patch(f"{SERVICE}.client.AuthorizationV1Api", return_value=api)


def _post(host="192.168.0.3", port=6443):
    payload = {"host": host}
    if port is not None:
        payload["port"] = port
    return test_client.post("/api/environments/check", json=payload)


# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------


def test_reachable_platform_reports_success():
    load, contexts = _patch_kubeconfig()
    with patch(f"{SERVICE}.socket.create_connection"), load, contexts, _patch_auth_api(
        _auth_api(True)
    ):
        response = _post()

    assert response.status_code == 200
    body = response.json()
    assert body["reachability"]["ok"] is True
    assert body["reachability"]["status"] == "reachable"
    assert body["reachability"]["latency_ms"] is not None
    assert body["ok"] is True


def test_connection_refused_means_kubernetes_not_running():
    load, contexts = _patch_kubeconfig()
    with patch(
        f"{SERVICE}.socket.create_connection", side_effect=ConnectionRefusedError()
    ), load, contexts, _patch_auth_api(_auth_api(True)):
        response = _post()

    body = response.json()
    assert response.status_code == 200
    assert body["reachability"]["ok"] is False
    assert body["reachability"]["status"] == "connection_refused"
    assert "Kubernetes does not appear to be running" in body["reachability"]["message"]
    assert body["ok"] is False


def test_timeout_reports_unreachable():
    load, contexts = _patch_kubeconfig()
    with patch(
        f"{SERVICE}.socket.create_connection", side_effect=TimeoutError()
    ), load, contexts, _patch_auth_api(_auth_api(True)):
        body = _post().json()

    assert body["reachability"]["status"] == "timeout"
    assert body["reachability"]["ok"] is False


def test_bad_hostname_reports_dns_error():
    load, contexts = _patch_kubeconfig()
    with patch(
        f"{SERVICE}.socket.create_connection",
        side_effect=socket.gaierror("Name or service not known"),
    ), load, contexts, _patch_auth_api(_auth_api(True)):
        body = _post(host="nope.invalid").json()

    assert body["reachability"]["status"] == "dns_error"
    assert "Could not resolve host" in body["reachability"]["message"]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_authenticated_credentials_pass():
    load, contexts = _patch_kubeconfig()
    with patch(f"{SERVICE}.socket.create_connection"), load, contexts, _patch_auth_api(
        _auth_api(True)
    ):
        body = _post().json()

    assert body["authentication"]["ok"] is True
    assert body["authentication"]["status"] == "authenticated"
    assert body["authentication"]["allowed"] is True


def test_authenticated_but_denied_still_passes():
    load, contexts = _patch_kubeconfig()
    with patch(f"{SERVICE}.socket.create_connection"), load, contexts, _patch_auth_api(
        _auth_api(allowed=False, reason="limited")
    ):
        body = _post().json()

    # The bar is "just authenticate", so a 200 with allowed=False still proceeds.
    assert body["authentication"]["ok"] is True
    assert body["authentication"]["allowed"] is False
    assert body["ok"] is True


def test_missing_kubeconfig_fails_authentication():
    with patch(f"{SERVICE}.socket.create_connection"), patch(
        f"{SERVICE}.config.load_kube_config",
        side_effect=config.ConfigException("Invalid kube-config file"),
    ):
        body = _post().json()

    assert body["authentication"]["ok"] is False
    assert body["authentication"]["status"] == "no_kubeconfig"
    assert body["ok"] is False


def test_unauthorized_credentials_fail():
    api = MagicMock()
    api.create_self_subject_access_review.side_effect = ApiException(
        status=401, reason="Unauthorized"
    )
    load, contexts = _patch_kubeconfig()
    with patch(f"{SERVICE}.socket.create_connection"), load, contexts, _patch_auth_api(
        api
    ):
        body = _post().json()

    assert body["authentication"]["ok"] is False
    assert body["authentication"]["status"] == "unauthorized"
    assert body["ok"] is False


def test_forbidden_credentials_fail():
    api = MagicMock()
    api.create_self_subject_access_review.side_effect = ApiException(
        status=403, reason="Forbidden"
    )
    load, contexts = _patch_kubeconfig()
    with patch(f"{SERVICE}.socket.create_connection"), load, contexts, _patch_auth_api(
        api
    ):
        body = _post().json()

    assert body["authentication"]["status"] == "forbidden"
    assert body["authentication"]["ok"] is False


def test_unreachable_kubeconfig_cluster_fails():
    api = MagicMock()
    api.create_self_subject_access_review.side_effect = RuntimeError("connection reset")
    load, contexts = _patch_kubeconfig()
    with patch(f"{SERVICE}.socket.create_connection"), load, contexts, _patch_auth_api(
        api
    ):
        body = _post().json()

    assert body["authentication"]["status"] == "cluster_unreachable"
    assert body["authentication"]["ok"] is False


# ---------------------------------------------------------------------------
# Response surfaces kubeconfig identity (so IP/kubeconfig mismatch is visible)
# ---------------------------------------------------------------------------


def test_response_reports_kubeconfig_context_and_server():
    configuration = MagicMock()
    configuration.host = "https://10.0.0.9:6443"
    contexts_value = (
        [
            {
                "name": "portrait-mobile-prod",
                "context": {"cluster": "miniedge", "user": "diagnostic-ops"},
            }
        ],
        {
            "name": "portrait-mobile-prod",
            "context": {"cluster": "miniedge", "user": "diagnostic-ops"},
        },
    )
    with patch(f"{SERVICE}.socket.create_connection"), patch(
        f"{SERVICE}.config.load_kube_config"
    ), patch(
        f"{SERVICE}.config.list_kube_config_contexts", return_value=contexts_value
    ), patch(
        f"{SERVICE}.client.Configuration", return_value=configuration
    ), patch(
        f"{SERVICE}.client.ApiClient"
    ), _patch_auth_api(
        _auth_api(True)
    ):
        body = _post().json()

    auth = body["authentication"]
    assert auth["context"] == "portrait-mobile-prod"
    assert auth["server"] == "https://10.0.0.9:6443"
    assert auth["user"] == "diagnostic-ops"


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def test_missing_host_returns_422():
    assert test_client.post("/api/environments/check", json={}).status_code == 422


def test_blank_host_returns_422():
    assert _post(host="   ").status_code == 422


def test_invalid_port_returns_422():
    assert _post(port=0).status_code == 422
    assert _post(port=70000).status_code == 422

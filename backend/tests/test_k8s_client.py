from unittest.mock import patch

import pytest
from fastapi import HTTPException
from kubernetes import config

from app.core import k8s_client


def test_load_config_uses_local_kubeconfig(monkeypatch):
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)

    with patch.object(k8s_client.config, "load_kube_config") as local:
        with patch.object(k8s_client.config, "load_incluster_config") as incluster:
            k8s_client._load_config()

    local.assert_called_once_with()
    incluster.assert_not_called()


def test_load_config_uses_incluster_config(monkeypatch):
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.43.0.1")

    with patch.object(k8s_client.config, "load_kube_config") as local:
        with patch.object(k8s_client.config, "load_incluster_config") as incluster:
            k8s_client._load_config()

    incluster.assert_called_once_with()
    local.assert_not_called()


def test_local_config_failure_returns_503(monkeypatch):
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)

    with patch.object(
        k8s_client.config,
        "load_kube_config",
        side_effect=config.ConfigException("Missing kubeconfig"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            k8s_client._load_config()

    assert exc_info.value.status_code == 503


def test_incluster_config_failure_returns_503(monkeypatch):
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.43.0.1")

    with patch.object(
        k8s_client.config,
        "load_incluster_config",
        side_effect=config.ConfigException("Missing ServiceAccount token"),
    ):
        with patch.object(k8s_client.config, "load_kube_config") as local:
            with pytest.raises(HTTPException) as exc_info:
                k8s_client._load_config()

    assert exc_info.value.status_code == 503
    local.assert_not_called()
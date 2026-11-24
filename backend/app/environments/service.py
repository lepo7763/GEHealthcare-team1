import socket
import time
from typing import Any, Dict, Optional, Tuple, cast

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from .schemas import (
    AuthenticationResult,
    DiscoveredComponent,
    DiscoverResponse,
    ReachabilityResult,
)

DEFAULT_K8S_PORT = 6443
# Keep the two phases bounded so the whole check finishes in roughly 5 seconds,
# even when the platform or the cluster is unreachable.
REACHABILITY_TIMEOUT_SECONDS = 2.5
AUTH_TIMEOUT_SECONDS = 2.5

# The two checks below deliberately target *different* things, and this is the
# main oddity of the Environments step:
#
#   1. Reachability probes the IP/hostname the operator typed into the form.
#   2. Authentication loads whatever `~/.kube/config` happens to point at.
#
# There is no guarantee these are the same cluster. Someone can type the IP of
# Cluster A while their kubeconfig still targets Cluster B (or a stale context),
# so "reachable" and "authenticated" can each pass while referring to two
# different machines. We keep both checks independent on purpose and the API
# response surfaces the kubeconfig's actual server/context/user so a mismatch is
# visible to the operator rather than silently accepted.


def check_reachability(
    host: str,
    port: int = DEFAULT_K8S_PORT,
    timeout: float = REACHABILITY_TIMEOUT_SECONDS,
) -> ReachabilityResult:
    """Opens a TCP connection to `host:port` to see if a Kubernetes API responds."""
    start = time.perf_counter()
    try:
        # We only care about establishing the connection, so we close immediately.
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except socket.gaierror as e:
        return ReachabilityResult(
            ok=False,
            status="dns_error",
            message=f"Could not resolve host '{host}': {e}",
        )
    except ConnectionRefusedError:
        return ReachabilityResult(
            ok=False,
            status="connection_refused",
            message=(
                f"Nothing is listening on {host}:{port}. Kubernetes does not "
                "appear to be running on this machine."
            ),
        )
    except TimeoutError:
        return ReachabilityResult(
            ok=False,
            status="timeout",
            message=(
                f"Connection to {host}:{port} timed out. The host may be "
                "unreachable or blocked by a firewall."
            ),
        )
    except OSError as e:
        return ReachabilityResult(
            ok=False,
            status="unreachable",
            message=f"Could not reach {host}:{port}: {e}",
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    return ReachabilityResult(
        ok=True,
        status="reachable",
        message=f"Kubernetes API server is reachable at {host}:{port}.",
        latency_ms=latency_ms,
    )


def _describe_current_context() -> Tuple[Optional[str], Optional[str]]:
    """Best-effort read of the active kubeconfig context name and user."""
    try:
        contexts, active = config.list_kube_config_contexts()
    except Exception:
        return None, None

    if not contexts:
        return None, None

    # list_kube_config_contexts() is untyped, so help the type checker out:
    # each context is a dict like {"name": ..., "context": {...}}.
    active_context = cast(Dict[str, Any], active or contexts[0])
    context = cast(Dict[str, Any], active_context.get("context") or {})
    return active_context.get("name"), context.get("user")


def _authentication_failure(
    status: str,
    message: str,
    context: Optional[str],
    server: Optional[str],
    user: Optional[str],
    api_status: Optional[int] = None,
) -> AuthenticationResult:
    return AuthenticationResult(
        ok=False,
        status=status,
        message=message,
        reason=f"HTTP {api_status}" if api_status else None,
        context=context,
        server=server,
        user=user,
    )


def check_authentication(timeout: float = AUTH_TIMEOUT_SECONDS) -> AuthenticationResult:
    """
    Loads ~/.kube/config and confirms the credentials actually authenticate.

    Uses a SelfSubjectAccessReview: the request only returns 200 if the caller is
    an authenticated user, so a 401/403 means we cannot continue.
    """
    configuration = client.Configuration()
    try:
        config.load_kube_config(client_configuration=configuration)
    except config.ConfigException as e:
        return AuthenticationResult(
            ok=False,
            status="no_kubeconfig",
            message=f"No valid ~/.kube/config found on this machine: {e}",
        )
    except Exception as e:
        return AuthenticationResult(
            ok=False,
            status="kubeconfig_error",
            message=f"Could not load ~/.kube/config: {e}",
        )

    # Without this, urllib3's default retry policy re-attempts a failed
    # connection several times, turning a 2.5s timeout into ~10s of waiting.
    configuration.retries = 0
    context, user = _describe_current_context()
    server = configuration.host

    try:
        api_client = client.ApiClient(configuration=configuration)
        auth_api = client.AuthorizationV1Api(api_client=api_client)
        review = client.V1SelfSubjectAccessReview(
            spec=client.V1SelfSubjectAccessReviewSpec(
                non_resource_attributes=client.V1NonResourceAttributes(
                    path="/version", verb="get"
                )
            )
        )
        result = auth_api.create_self_subject_access_review(
            review, _request_timeout=timeout
        )
    except ApiException as e:
        if e.status == 401:
            return _authentication_failure(
                "unauthorized",
                "Credentials in ~/.kube/config were rejected (401 Unauthorized) — "
                "the token may be invalid or expired.",
                context,
                server,
                user,
                api_status=e.status,
            )
        if e.status == 403:
            return _authentication_failure(
                "forbidden",
                "Not authenticated or lacking basic permissions (403 Forbidden).",
                context,
                server,
                user,
                api_status=e.status,
            )
        reason = e.reason or str(e)
        return _authentication_failure(
            "api_error",
            f"Cluster API error: {reason}",
            context,
            server,
            user,
            api_status=e.status,
        )
    except Exception as e:
        where = f" ({server})" if server else ""
        return _authentication_failure(
            "cluster_unreachable",
            f"Could not reach the cluster in ~/.kube/config{where}: {e}",
            context,
            server,
            user,
        )

    status = result.status
    allowed = status.allowed if status else None
    reason = status.reason if status else None

    if allowed:
        message = "Credentials in ~/.kube/config authenticated successfully."
    else:
        message = (
            "Credentials authenticated, but the permission probe was denied — "
            "you may have limited access."
        )
        if reason:
            message += f" Reason: {reason}"

    return AuthenticationResult(
        ok=True,
        status="authenticated",
        message=message,
        allowed=allowed,
        reason=reason,
        context=context,
        server=server,
        user=user,
    )


# --- Component discovery -----------------------------------------------------

_KIND_KEYWORDS = (
    ("viewer", "viewer"),
    ("hub", "hub"),
    ("miniedge", "backend"),
)


def _classify(name: str) -> str:
    lowered = name.lower()
    for keyword, kind in _KIND_KEYWORDS:
        if keyword in lowered:
            return kind
    return "service"


def _list_components(
    configuration: client.Configuration, timeout: float
) -> list[DiscoveredComponent]:
    components: list[DiscoveredComponent] = []
    core = client.CoreV1Api(api_client=client.ApiClient(configuration=configuration))
    for node in core.list_node(_request_timeout=timeout).items:
        addresses = {a.type: a.address for a in (node.status.addresses or [])}
        ready = any(
            c.type == "Ready" and c.status == "True"
            for c in (node.status.conditions or [])
        )
        components.append(
            DiscoveredComponent(
                name=node.metadata.name,
                kind="node",
                address=addresses.get("InternalIP"),
                online=ready,
                detail="Kubernetes node",
            )
        )
    return components


def discover_components(
    host: str,
    port: int = DEFAULT_K8S_PORT,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: float = AUTH_TIMEOUT_SECONDS,
) -> DiscoverResponse:
    """
    Probes the platform and lists its Kubernetes nodes (pod names are not collected).

    If a username/password is supplied they are used for basic auth against
    `host:port`; otherwise the local ~/.kube/config is used. Credentials are
    never logged or echoed back in the response.
    """
    reachability = check_reachability(host, port)
    if not reachability.ok:
        return DiscoverResponse(
            ok=False, host=host, port=port, message=reachability.message,
            reachability=reachability,
        )

    def fail(message: str) -> DiscoverResponse:
        return DiscoverResponse(
            ok=False, host=host, port=port, message=message, reachability=reachability
        )

    def kubeconfig_configuration() -> client.Configuration:
        configuration = client.Configuration()
        config.load_kube_config(client_configuration=configuration)
        return configuration

    note = ""
    components: list[DiscoveredComponent] = []
    try:
        if username and password:
            configuration = client.Configuration()
            configuration.host = f"https://{host}:{port}"
            configuration.username = username
            configuration.password = password
            configuration.verify_ssl = False
            configuration.retries = 0
            try:
                components = _list_components(configuration, timeout)
            except ApiException as e:
                if e.status not in (401, 403):
                    raise
                # Most clusters disable username/password auth, so fall back.
                try:
                    configuration = kubeconfig_configuration()
                except Exception:
                    return fail(
                        f"The cluster rejected the username/password (HTTP {e.status}); "
                        "Kubernetes usually does not accept basic auth. Add a valid "
                        "~/.kube/config on this machine and try again."
                    )
                configuration.retries = 0
                components = _list_components(configuration, timeout)
                note = " (username/password were rejected; used ~/.kube/config instead)"
        else:
            try:
                configuration = kubeconfig_configuration()
            except Exception as e:
                return fail(
                    f"No credentials supplied and ~/.kube/config could not be loaded: {e}"
                )
            configuration.retries = 0
            components = _list_components(configuration, timeout)
    except ApiException as e:
        return fail(
            f"Cluster rejected the request (HTTP {e.status}). "
            "Check the credentials in ~/.kube/config."
        )
    except Exception as e:
        return fail(f"Could not query the cluster: {e}")

    return DiscoverResponse(
        ok=True, host=host, port=port,
        message=f"Discovered {len(components)} components{note}.",
        reachability=reachability, components=components,
    )

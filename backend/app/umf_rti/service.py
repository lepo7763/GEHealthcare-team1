"""Create, watch and clean up the short-lived UMF RTI capture Job."""

from __future__ import annotations

import json
import logging
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.log_collection.progress import UMF_RTI_SERVICE_ID, tracker
from app.log_collection.schemas import CollectedService, LogCollectionManifest, LogErrorEntry

from .config import UmfRtiConfig
from .schemas import UmfRtiCaptureResult, UmfRtiParams

logger = logging.getLogger(__name__)

UMF_RTI_FILES = (
    "umf-rti/umf-rti-discovery.ndjson",
    "umf-rti/umf-rti-summary.json",
    "umf-rti/README.txt",
)

SDDS_REQUIRED_KEYS = (
    "Commissioning_CA.cert.pem",
    "Commissioning_Governance.p7s",
    "Commissioning_Permission.p7s",
    "MDHEndPoint.cert.pem",
    "MDHEndPoint.key.pem",
)

# Waiting reasons that cannot recover without an operator changing something.
FAST_FAIL_WAITING_REASONS = frozenset(
    {
        "ImagePullBackOff",
        "ErrImagePull",
        "InvalidImageName",
        "CreateContainerConfigError",
        "CreateContainerError",
        "RunContainerError",
        "CrashLoopBackOff",
        "Unschedulable",
    }
)


class UmfRtiPrerequisiteError(Exception):
    """A required platform resource is missing or the caller lacks access."""


class UmfRtiCaptureError(Exception):
    """The capture Job could not be created or observed."""


@dataclass
class ParsedUmfRtiLog:
    json_lines: List[str] = field(default_factory=list)
    raw_lines: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(
        default_factory=lambda: {
            "participants": 0,
            "topics": 0,
            "writers": 0,
            "readers": 0,
            "discovered_topic_handles": 0,
        }
    )
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    collector_version: Optional[str] = None
    rti_version: Optional[str] = None


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reason(exception: ApiException) -> str:
    return exception.reason or f"HTTP {exception.status}"


def _access_error(action: str, namespace: str, exception: ApiException) -> str:
    """Actionable message when the cluster rejects the kubeconfig identity."""
    if exception.status == 401:
        return (
            "The Kubernetes credentials in ~/.kube/config were rejected "
            "(401 Unauthorized)."
        )
    return (
        f"The Kubernetes identity in ~/.kube/config is not allowed to {action} "
        f"in {namespace}. Check it with: "
        f"kubectl auth can-i {action} -n {namespace}"
    )


def _read_config_map(core: client.CoreV1Api, name: str, namespace: str) -> client.V1ConfigMap:
    try:
        return core.read_namespaced_config_map(name=name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            raise UmfRtiPrerequisiteError(
                f"ConfigMap {namespace}/{name} was not found. "
                "Run kubernetes/umf-rti-setup.sh to create the UMF RTI prerequisites."
            ) from e
        raise UmfRtiPrerequisiteError(
            f"Could not read ConfigMap {namespace}/{name}: {_reason(e)}"
        ) from e


def _read_secret(core: client.CoreV1Api, name: str, namespace: str) -> client.V1Secret:
    try:
        return core.read_namespaced_secret(name=name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            raise UmfRtiPrerequisiteError(
                f"Secret {namespace}/{name} was not found. "
                "Run kubernetes/umf-rti-setup.sh to create the UMF RTI prerequisites."
            ) from e
        raise UmfRtiPrerequisiteError(
            f"Could not read Secret {namespace}/{name}: {_reason(e)}"
        ) from e


def check_prerequisites(core: client.CoreV1Api, config: UmfRtiConfig) -> None:
    """Fail with an actionable message before creating a Job that cannot start."""
    missing: List[str] = []

    qos = _read_config_map(core, config.qos_configmap, config.namespace)
    qos_xml = (qos.data or {}).get(config.qos_key)
    if not qos_xml:
        missing.append(
            f"ConfigMap {config.namespace}/{config.qos_configmap} is missing key {config.qos_key}"
        )

    sdds = _read_secret(core, config.sdds_secret, config.namespace)
    sdds_keys = set((sdds.data or {}).keys())
    missing_sdds = [key for key in SDDS_REQUIRED_KEYS if key not in sdds_keys]
    if missing_sdds:
        missing.append(
            f"Secret {config.namespace}/{config.sdds_secret} is missing {', '.join(missing_sdds)}"
        )

    collector = _read_secret(core, config.collector_secret, config.namespace)
    collector_value = (collector.data or {}).get(config.collector_key)
    if not collector_value:
        missing.append(
            f"Secret {config.namespace}/{config.collector_secret} is missing key {config.collector_key}"
        )

    license_secret = _read_secret(core, config.license_secret, config.namespace)
    if not (license_secret.data or {}).get(config.license_key):
        missing.append(
            f"Secret {config.namespace}/{config.license_secret} is missing key {config.license_key}"
        )

    if missing:
        raise UmfRtiPrerequisiteError(
            "UMF RTI prerequisites are not ready: "
            + "; ".join(missing)
            + ". Run kubernetes/umf-rti-setup.sh to create/repair them."
        )


def resolve_router_peer(
    core: client.CoreV1Api, domain_id: int, config: UmfRtiConfig
) -> Tuple[str, int]:
    """Return (NDDS_DISCOVERY_PEERS value, expected domain port).

    RTI derives the discovery port from the domain, so the peer URI deliberately
    has no ``:port`` suffix.  In this RTI build a suffix such as
    ``udpv4://axone-router-1.pm.svc.cluster.local:15410`` is passed to
    getaddrinfo as part of the hostname and silently fails.  The service port is
    still validated and reported in the summary.
    """
    if config.discovery_peers_override:
        return config.discovery_peers_override, 0

    try:
        service = core.read_namespaced_service(
            name=config.router_service, namespace=config.router_namespace
        )
    except ApiException as e:
        if e.status == 404:
            raise UmfRtiPrerequisiteError(
                f"Router Service {config.router_namespace}/{config.router_service} was not found. "
                f"Set IOMT_UMF_RTI_DISCOVERY_PEERS to an explicit peer URI if the router "
                f"is not called {config.router_service}."
            ) from e
        raise UmfRtiPrerequisiteError(
            f"Could not read router Service {config.router_namespace}/{config.router_service}: "
            f"{_reason(e)}"
        ) from e

    ports = [
        port.port
        for port in (service.spec.ports or [])
        if port.name and port.name.startswith(f"domain-{domain_id}-") and port.port is not None
    ]
    if not ports:
        available = sorted(
            {
                port.name.split("-")[1]
                for port in (service.spec.ports or [])
                if port.name and port.name.startswith("domain-")
            }
        )
        raise UmfRtiPrerequisiteError(
            f"Router Service {config.router_namespace}/{config.router_service} does not expose "
            f"domain {domain_id}. Available domain ports: {', '.join(available) or 'none'}. "
            "Use a domain that the platform actually exposes (32 is the live UMF domain in this lab)."
        )

    peer = (
        f"udpv4://{config.router_service}.{config.router_namespace}.svc.cluster.local"
    )
    return peer, min(ports)


def _job_labels(domain_id: int) -> Dict[str, str]:
    return {
        "iomt-analysis-tool/service": "umf-rti",
        "iomt-analysis-tool/domain": str(domain_id),
    }


def _collector_script() -> str:
    return "\n".join(
        [
            "set -eu",
            'APP_JAR="$(ls /opt/axone-umfcompatibilitycheck/bin/axone-umfcompatibilitycheck-*.jar 2>/dev/null | head -n 1 || true)"',
            'CP="/opt/umf-rti/umf-rti-collector.jar:/opt/axone-umfcompatibilitycheck/lib/nddsjava.jar"',
            'if [ -n "$APP_JAR" ]; then CP="$CP:$APP_JAR"; fi',
            "exec java -cp \"$CP\" \\",
            "  -Djava.library.path=/opt/axone-umfcompatibilitycheck/lib \\",
            "  com.gehc.iomt.umfrti.UmfRtiCollector \\",
            '  --domain "$UMF_DOMAIN_ID" \\',
            '  --duration "$UMF_DURATION_SECONDS" \\',
            "  --qos-file /opt/axone-tools/qos/CommissioningQoS.xml \\",
            "  --qos-profile AxoneNetQoSLibrary::umfgeneral_qos \\",
            '  --max-records "$UMF_MAX_RECORDS"',
        ]
    )


def build_job(
    config: UmfRtiConfig, params: UmfRtiParams, peer: str, job_name: str
) -> client.V1Job:
    """Build the Job spec.  Kept separate so it can be unit-tested."""
    labels = _job_labels(params.umf_domain_id)
    active_deadline = (
        params.umf_duration_seconds + config.job_active_deadline_grace_seconds
    )

    env = [
        client.V1EnvVar(name="SDDS_HOME", value=config.sdds_mount_path),
        client.V1EnvVar(
            name="NDDS_QOS_PROFILES",
            value=f"{config.qos_mount_path}/{config.qos_key}",
        ),
        client.V1EnvVar(name="DDS_SECURE", value="secure"),
        client.V1EnvVar(name="DDS_INTERFACES", value=config.dds_interfaces),
        client.V1EnvVar(name="DDS_INTERFACES_MONITORING", value=config.dds_interfaces),
        client.V1EnvVar(name="NDDS_DISCOVERY_PEERS", value=peer),
        client.V1EnvVar(
            name="RTI_LICENSE_FILE",
            value=f"{config.license_mount_path}/{config.license_key}",
        ),
        client.V1EnvVar(name="HOME", value="/tmp"),
        client.V1EnvVar(name="UMF_DOMAIN_ID", value=str(params.umf_domain_id)),
        client.V1EnvVar(
            name="UMF_DURATION_SECONDS", value=str(params.umf_duration_seconds)
        ),
        client.V1EnvVar(
            name="UMF_MAX_RECORDS", value=str(config.collector_max_records)
        ),
    ]

    volumes = [
        client.V1Volume(
            name="umf-rti-collector",
            secret=client.V1SecretVolumeSource(
                secret_name=config.collector_secret,
                default_mode=0o444,
                items=[
                    client.V1KeyToPath(
                        key=config.collector_key, path="umf-rti-collector.jar"
                    )
                ],
            ),
        ),
        client.V1Volume(
            name="umf-rti-license",
            secret=client.V1SecretVolumeSource(
                secret_name=config.license_secret,
                default_mode=0o444,
                items=[
                    client.V1KeyToPath(key=config.license_key, path=config.license_key)
                ],
            ),
        ),
        client.V1Volume(
            name="umf-rti-qos",
            config_map=client.V1ConfigMapVolumeSource(
                name=config.qos_configmap,
                default_mode=0o444,
                items=[
                    client.V1KeyToPath(key=config.qos_key, path=config.qos_key)
                ],
            ),
        ),
        client.V1Volume(
            name="umf-rti-sdds",
            secret=client.V1SecretVolumeSource(
                secret_name=config.sdds_secret, default_mode=0o444
            ),
        ),
    ]

    volume_mounts = [
        client.V1VolumeMount(
            name="umf-rti-collector",
            mount_path=config.collector_mount_path,
            read_only=True,
        ),
        client.V1VolumeMount(
            name="umf-rti-license",
            mount_path=config.license_mount_path,
            read_only=True,
        ),
        client.V1VolumeMount(
            name="umf-rti-qos", mount_path=config.qos_mount_path, read_only=True
        ),
        client.V1VolumeMount(
            name="umf-rti-sdds", mount_path=config.sdds_mount_path, read_only=True
        ),
    ]

    container = client.V1Container(
        name=config.collector_container_name,
        image=config.image,
        image_pull_policy="IfNotPresent",
        command=["/bin/sh", "-c", _collector_script()],
        env=env,
        volume_mounts=volume_mounts,
        resources=client.V1ResourceRequirements(
            requests={"cpu": config.cpu_request, "memory": config.memory_request},
            limits={"cpu": config.cpu_limit, "memory": config.memory_limit},
        ),
        security_context=client.V1SecurityContext(
            allow_privilege_escalation=False,
            privileged=False,
            run_as_non_root=True,
            run_as_user=2017,
            run_as_group=2017,
            capabilities=client.V1Capabilities(drop=["ALL"]),
        ),
        termination_message_policy="FallbackToLogsOnError",
    )

    pod_spec = client.V1PodSpec(
        containers=[container],
        restart_policy="Never",
        host_network=False,
        dns_policy="ClusterFirst",
        automount_service_account_token=False,
        security_context=client.V1PodSecurityContext(
            run_as_non_root=True,
            run_as_user=2017,
            run_as_group=2017,
            fs_group=2017,
        ),
        image_pull_secrets=[
            client.V1LocalObjectReference(name=name)
            for name in config.image_pull_secrets
        ],
        volumes=volumes,
    )

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels),
        spec=pod_spec,
    )

    return client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name, labels=labels),
        spec=client.V1JobSpec(
            template=template,
            backoff_limit=0,
            active_deadline_seconds=active_deadline,
            ttl_seconds_after_finished=config.job_ttl_seconds,
        ),
    )


def _new_job_name(domain_id: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"umf-rti-{domain_id}-{stamp}-{uuid.uuid4().hex[:6]}"


def _pod_waiting_reason(pod: client.V1Pod) -> Optional[str]:
    status = pod.status
    if not status:
        return None
    for container_status in (status.init_container_statuses or []) + (
        status.container_statuses or []
    ):
        waiting = getattr(getattr(container_status, "state", None), "waiting", None)
        if waiting and waiting.reason:
            return waiting.reason
    if status.reason:
        return status.reason
    return None


def _pod_exit_code(pod: client.V1Pod) -> Optional[int]:
    status = pod.status
    if not status:
        return None
    for container_status in (status.init_container_statuses or []) + (
        status.container_statuses or []
    ):
        terminated = getattr(getattr(container_status, "state", None), "terminated", None)
        if terminated is not None and terminated.exit_code is not None:
            return int(terminated.exit_code)
    return None


def _pod_pending_message(pod: client.V1Pod) -> Optional[str]:
    status = pod.status
    if not status:
        return None
    messages = []
    for container_status in (status.init_container_statuses or []) + (
        status.container_statuses or []
    ):
        waiting = getattr(getattr(container_status, "state", None), "waiting", None)
        if waiting and waiting.message:
            messages.append(waiting.message)
    if status.message:
        messages.append(status.message)
    return "; ".join(messages) if messages else None


def _job_failure_message(job_status: client.V1JobStatus) -> Optional[str]:
    for condition in job_status.conditions or []:
        if condition.type == "Failed":
            return condition.message or condition.reason or "Job failed"
    if job_status.failed:
        return (
            f"Job failed (failed={job_status.failed}, "
            f"active={job_status.active or 0})."
        )
    return None


def _pod_termination_message(pod: client.V1Pod) -> Optional[str]:
    status = pod.status
    if not status:
        return None
    for container_status in (status.init_container_statuses or []) + (
        status.container_statuses or []
    ):
        terminated = getattr(getattr(container_status, "state", None), "terminated", None)
        if terminated is not None:
            reason = terminated.reason or "unknown reason"
            return (
                f"container {container_status.name} terminated with exit code "
                f"{terminated.exit_code} ({reason})"
            )
    return status.message


def _job_warning_events(
    core: client.CoreV1Api, namespace: str, job_name: str
) -> Optional[str]:
    """Best-effort explanation for a Job that never created a Pod."""
    try:
        events = core.list_namespaced_event(
            namespace=namespace,
            field_selector=(
                f"involvedObject.name={job_name},involvedObject.kind=Job"
            ),
            _request_timeout=10,
        )
    except Exception:
        return None
    messages = []
    for event in events.items or []:
        if event.type == "Warning" and event.message:
            messages.append(event.message)
    if not messages:
        return None
    return " ".join(messages[:3])


def _find_pod(
    core: client.CoreV1Api, namespace: str, job_name: str
) -> Optional[client.V1Pod]:
    try:
        pods = core.list_namespaced_pod(
            namespace=namespace,
            label_selector=f"job-name={job_name}",
            _request_timeout=10,
        ).items
    except ApiException as e:
        # "No Pods" is normal while the Job starts, but a rejected credential
        # would look identical and surface later as a misleading timeout.
        if e.status in (401, 403):
            raise
        return None
    return pods[0] if pods else None


def _delete_job(
    batch: client.BatchV1Api, namespace: str, job_name: str
) -> bool:
    try:
        batch.delete_namespaced_job(
            name=job_name,
            namespace=namespace,
            propagation_policy="Foreground",
            grace_period_seconds=0,
        )
        return True
    except ApiException as e:
        return e.status == 404
    except Exception:
        return False


def _wait_for_cleanup(
    core: client.CoreV1Api, batch: client.BatchV1Api, namespace: str, job_name: str,
    timeout_seconds: float = 15.0,
) -> None:
    """Best-effort wait so the acceptance check sees no leftover Job/Pod."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job_gone = False
        try:
            batch.read_namespaced_job_status(name=job_name, namespace=namespace)
        except ApiException as e:
            job_gone = e.status == 404
        pod = _find_pod(core, namespace, job_name)
        if job_gone and pod is None:
            return
        time.sleep(0.5)


def _parse_ndjson(log_text: str) -> ParsedUmfRtiLog:
    parsed = ParsedUmfRtiLog()
    seen_participants: set[str] = set()
    seen_writers: set[str] = set()
    seen_readers: set[str] = set()
    seen_topics: set[str] = set()

    for raw_line in (log_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith("{"):
            parsed.raw_lines.append(raw_line)
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            parsed.raw_lines.append(raw_line)
            continue
        if not isinstance(record, dict):
            parsed.raw_lines.append(raw_line)
            continue
        parsed.json_lines.append(line)
        record_type = record.get("type")
        if record_type == "participant":
            guid = record.get("guid")
            if guid and guid not in seen_participants:
                seen_participants.add(guid)
                parsed.counts["participants"] += 1
        elif record_type == "writer":
            guid = record.get("guid")
            if guid and guid not in seen_writers:
                seen_writers.add(guid)
                parsed.counts["writers"] += 1
        elif record_type == "reader":
            guid = record.get("guid")
            if guid and guid not in seen_readers:
                seen_readers.add(guid)
                parsed.counts["readers"] += 1
        elif record_type == "topic":
            key = f"{record.get('name')}\u0000{record.get('type_name')}"
            if key not in seen_topics:
                seen_topics.add(key)
                parsed.counts["topics"] += 1
        elif record_type == "summary":
            parsed.summary = record
            counts = record.get("counts")
            if isinstance(counts, dict):
                for key in ("participants", "topics", "writers", "readers"):
                    value = counts.get(key)
                    if isinstance(value, int):
                        parsed.counts[key] = value
                handles = counts.get("discovered_topic_handles")
                if isinstance(handles, int):
                    parsed.counts["discovered_topic_handles"] = handles
            parsed.collector_version = record.get("collector_version") or parsed.collector_version
            parsed.rti_version = record.get("rti_version") or parsed.rti_version
            for warning in record.get("warnings") or []:
                if isinstance(warning, str) and warning not in parsed.warnings:
                    parsed.warnings.append(warning)
        elif record_type == "collector":
            parsed.collector_version = record.get("collector_version") or parsed.collector_version
            parsed.rti_version = record.get("rti_version") or parsed.rti_version
        elif record_type == "error":
            message = record.get("message") or "Collector reported an error"
            hint = record.get("hint")
            parsed.error = f"{message} {hint}".strip() if hint else message
        else:
            parsed.warnings.append(
                f"Collector emitted an unknown record type: {record_type!r}"
            )

    if parsed.summary:
        summary_counts = parsed.summary.get("counts")
        if isinstance(summary_counts, dict):
            handles = summary_counts.get("discovered_topic_handles")
            if isinstance(handles, int):
                parsed.counts["discovered_topic_handles"] = handles

    if parsed.raw_lines:
        preview = "; ".join(line[:300] for line in parsed.raw_lines[:5])
        parsed.warnings.append(
            f"Collector stderr/non-JSON output was captured in the backend pod log: {preview}"
        )
    if parsed.summary is None and parsed.json_lines:
        parsed.warnings.append("Collector log did not contain a final summary record (possibly truncated).")
    return parsed


def capture_umf_rti(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    params: UmfRtiParams,
    config: UmfRtiConfig,
) -> UmfRtiCaptureResult:
    """Create the Job, wait for it, read the log, and always delete the Job."""
    peer, router_port = resolve_router_peer(core, params.umf_domain_id, config)
    job_name = _new_job_name(params.umf_domain_id)
    job = build_job(config, params, peer, job_name)
    started_at = _utcnow()
    started_monotonic = time.monotonic()

    tracker.set_service_total(
        UMF_RTI_SERVICE_ID, params.umf_duration_seconds, unit="seconds"
    )
    tracker.set_service_completed(
        UMF_RTI_SERVICE_ID,
        0,
        current=f"Starting UMF RTI (domain {params.umf_domain_id})",
    )

    try:
        batch.create_namespaced_job(namespace=config.namespace, body=job)
    except ApiException as e:
        if e.status == 404:
            raise UmfRtiPrerequisiteError(
                f"Namespace {config.namespace} was not found."
            ) from e
        if e.status in (401, 403):
            raise UmfRtiCaptureError(
                _access_error("create jobs", config.namespace, e)
            ) from e
        raise UmfRtiCaptureError(
            f"Could not create UMF RTI Job {job_name}: {_reason(e)}"
        ) from e
    except Exception as e:
        raise UmfRtiCaptureError(
            f"Could not create UMF RTI Job {job_name}: {e}"
        ) from e

    status = "unknown"
    error: Optional[str] = None
    pod_name: Optional[str] = None
    node_name: Optional[str] = None
    exit_code: Optional[int] = None
    log_text = ""
    warnings: List[str] = []
    parsed = ParsedUmfRtiLog()
    delete_ok = False

    try:
        deadline = (
            started_monotonic
            + params.umf_duration_seconds
            + config.wait_timeout_seconds
        )
        job_created_monotonic = time.monotonic()
        while True:
            job_status: Optional[client.V1JobStatus] = None
            try:
                job_status = batch.read_namespaced_job_status(
                    name=job_name, namespace=config.namespace, _request_timeout=10
                ).status
            except ApiException as e:
                if e.status == 404:
                    error = f"UMF RTI Job {job_name} disappeared before completion."
                    status = "failed"
                    break
                warnings.append(f"Could not read Job status: {_reason(e)}")

            try:
                pod = _find_pod(core, config.namespace, job_name)
            except ApiException as e:
                error = _access_error("list pods", config.namespace, e)
                status = "failed"
                break
            waiting_reason = None
            if pod is not None:
                pod_name = pod.metadata.name if pod.metadata else pod_name
                node_name = pod.spec.node_name if pod.spec else node_name
                waiting_reason = _pod_waiting_reason(pod)
                if waiting_reason in FAST_FAIL_WAITING_REASONS:
                    message = _pod_pending_message(pod) or waiting_reason
                    error = f"UMF RTI pod cannot start ({waiting_reason}): {message}"
                    status = "failed"
                    break
                if pod.status and pod.status.phase == "Failed":
                    exit_code = _pod_exit_code(pod)
                    error = (
                        _pod_termination_message(pod)
                        or pod.status.message
                        or f"UMF RTI pod finished in phase Failed ({pod.status.reason or 'unknown'})."
                    )
                    status = "failed"
                    break
                if pod.status and pod.status.phase == "Succeeded":
                    # The Job controller usually updates status immediately after
                    # the pod, but accept the pod phase if it is already terminal.
                    status = "succeeded"
                    exit_code = _pod_exit_code(pod)
                    break

            if pod is None and (
                time.monotonic() - job_created_monotonic
                >= config.pod_creation_timeout_seconds
            ):
                explanation = _job_warning_events(core, config.namespace, job_name)
                error = (
                    f"UMF RTI Job did not create a Pod within "
                    f"{config.pod_creation_timeout_seconds} seconds."
                )
                if explanation:
                    error += f" {explanation}"
                else:
                    error += (
                        " Check the iomt-integration quota, RBAC, and image pull "
                        "secret (kubectl describe job -n "
                        f"{config.namespace} {job_name})."
                    )
                status = "failed"
                break

            if job_status is not None:
                if job_status.succeeded:
                    status = "succeeded"
                    if pod is not None:
                        exit_code = _pod_exit_code(pod)
                    break
                if job_status.failed:
                    status = "failed"
                    if pod is not None:
                        exit_code = _pod_exit_code(pod)
                    error = _job_failure_message(job_status) or "UMF RTI Job failed."
                    break

            elapsed = min(
                params.umf_duration_seconds,
                int(time.monotonic() - started_monotonic),
            )
            tracker.set_service_completed(
                UMF_RTI_SERVICE_ID,
                elapsed,
                current=f"Capturing UMF RTI (domain {params.umf_domain_id})",
            )
            if time.monotonic() >= deadline:
                status = "timeout"
                error = (
                    "UMF RTI capture did not finish within "
                    f"{params.umf_duration_seconds + config.wait_timeout_seconds} seconds."
                )
                break
            time.sleep(max(0.05, config.poll_interval_seconds))

        if pod_name:
            try:
                log_text = (
                    core.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=config.namespace,
                        container=config.collector_container_name,
                        limit_bytes=params.umf_max_bytes,
                        timestamps=False,
                        _request_timeout=30,
                    )
                    or ""
                )
            except ApiException as e:
                warnings.append(
                    f"Could not read UMF RTI pod log for {pod_name}: {_reason(e)}"
                )
            except Exception as e:
                warnings.append(f"Could not read UMF RTI pod log for {pod_name}: {e}")

        if log_text:
            parsed = _parse_ndjson(log_text)
            warnings.extend(w for w in parsed.warnings if w not in warnings)
            if parsed.error:
                if not error:
                    error = parsed.error
                elif parsed.error not in error:
                    error = f"{error}; collector: {parsed.error}"
                if status == "succeeded":
                    status = "failed"
            if parsed.summary:
                exit_code = parsed.summary.get("exit_code")  # collector does not set it
            if parsed.counts:
                pass
            if not parsed.json_lines and not error:
                error = "UMF RTI collector produced no JSON records."
                status = "failed"
        elif status == "succeeded":
            error = "UMF RTI collector produced no log output."
            status = "failed"
    finally:
        delete_ok = _delete_job(batch, config.namespace, job_name)
        if delete_ok:
            try:
                _wait_for_cleanup(core, batch, config.namespace, job_name)
            except Exception:
                pass
        else:
            warnings.append(
                f"Could not delete UMF RTI Job {job_name}; TTL {config.job_ttl_seconds}s will clean it up."
            )

    finished_at = _utcnow()
    log_bytes = len(log_text.encode("utf-8"))
    truncated = bool(params.umf_max_bytes and log_bytes >= params.umf_max_bytes)

    if status == "succeeded" and error:
        status = "failed"
    if status == "succeeded" and exit_code is None:
        # A successful collector exits 0 even when the pod status has already
        # been removed by the Job/pod cleanup.
        exit_code = 0
    if status == "unknown":
        status = "failed"
        error = error or "UMF RTI capture ended without a terminal Job state."

    if error:
        tracker.fail_service(UMF_RTI_SERVICE_ID, error)
    else:
        tracker.set_service_completed(
            UMF_RTI_SERVICE_ID,
            params.umf_duration_seconds,
        )
        tracker.set_service_current(UMF_RTI_SERVICE_ID, None)

    return UmfRtiCaptureResult(
        domain_id=params.umf_domain_id,
        duration_seconds=params.umf_duration_seconds,
        router_peer=peer,
        router_port=router_port,
        namespace=config.namespace,
        job_name=job_name,
        pod_name=pod_name,
        node_name=node_name,
        image=config.image,
        status=status,
        exit_code=exit_code,
        started_at_utc=started_at,
        finished_at_utc=finished_at,
        log_text=log_text,
        log_bytes=log_bytes,
        truncated=truncated,
        error=error,
        warnings=warnings,
        counts=parsed.counts,
        collector_version=parsed.collector_version,
        rti_version=parsed.rti_version,
        job_deleted=delete_ok,
    )


def _readme(result: UmfRtiCaptureResult) -> str:
    return f"""UMF RTI discovery capture
=========================

Domain:            {result.domain_id}
Duration:          {result.duration_seconds} seconds
Router peer:       {result.router_peer}
Router port:       {result.router_port}
Image:             {result.image}
Namespace:         {result.namespace}
Job:               {result.job_name}
Pod:               {result.pod_name or '(not created)'}
Node:              {result.node_name or '(unknown)'}
Status:            {result.status}
Started (UTC):     {result.started_at_utc}
Finished (UTC):    {result.finished_at_utc}
Collector:         {result.collector_version or '(unknown)'}
RTI version:       {result.rti_version or '(unknown)'}
Log bytes:         {result.log_bytes}
Log truncated:     {result.truncated}
Counts:            {json.dumps(result.counts, sort_keys=True)}

Files in this package
---------------------
umf-rti/umf-rti-discovery.ndjson
  One JSON object per line: collector metadata, participants, topics,
  writers, readers, and a final summary.  Each writer/reader record includes
  topic name, type name, GUID, participant GUID/name, liveness, and QoS.

umf-rti/umf-rti-summary.json
  Machine-readable capture summary (domain, duration, peer, counts).

umf-rti/README.txt
  This overview.

What is captured
----------------
- Live DDS participants discovered on the selected domain.
- UMF topics observed from matched writers/readers, including umf_cfg,
  umfcmd_req, umfcmd_resp, and umf_cfg_state.
- Remote writers/readers, their topic/type names, GUIDs, participant names,
  liveness at capture time, and QoS (reliability, durability, deadline,
  liveliness, history/ownership/presentation/partition where available).

Privacy
-------
The package contains discovery and QoS metadata only. No sample values or
patient data are included.
"""


def write_artifacts(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    result: UmfRtiCaptureResult,
    params: UmfRtiParams,
    config: UmfRtiConfig,
) -> None:
    """Write UMF RTI files into the diagnostic zip and update the manifest.

    Internal warnings and raw collector stderr stay in the backend pod log.
    The package is deliberately limited to the discovery records, a clean
    summary, and the overview README.
    """
    parsed = _parse_ndjson(result.log_text)
    counts = dict(result.counts or parsed.counts)

    internal_warnings = list(result.warnings)
    for warning in parsed.warnings:
        if warning not in internal_warnings:
            internal_warnings.append(warning)
    for warning in internal_warnings:
        logger.info("UMF RTI internal note: %s", warning)

    ndjson_text = "\n".join(parsed.json_lines)
    if ndjson_text:
        ndjson_text += "\n"
    summary = {
        "domain": result.domain_id,
        "duration_seconds": result.duration_seconds,
        "router_peer": result.router_peer,
        "router_port": result.router_port,
        "image": result.image,
        "namespace": result.namespace,
        "job": result.job_name,
        "pod": result.pod_name,
        "node": result.node_name,
        "status": result.status,
        "exit_code": result.exit_code,
        "started_at_utc": result.started_at_utc,
        "finished_at_utc": result.finished_at_utc,
        "log_bytes": result.log_bytes,
        "truncated": result.truncated,
        "counts": counts,
        "collector_version": result.collector_version or parsed.collector_version,
        "rti_version": result.rti_version or parsed.rti_version,
        "job_deleted": result.job_deleted,
        "sample_values_captured": False,
    }
    if result.error:
        summary["error"] = result.error

    files = list(UMF_RTI_FILES)
    zf.writestr(files[0], ndjson_text)
    zf.writestr(files[1], json.dumps(summary, indent=2, sort_keys=False))
    zf.writestr(files[2], _readme(result))
    manifest.collected_files.extend(files)

    service_status = "done" if result.status == "succeeded" and not result.error else "error"
    manifest.services.append(
        CollectedService(
            id=UMF_RTI_SERVICE_ID,
            label="UMF RTI",
            status=service_status,
            files=files,
            error=result.error,
        )
    )
    if result.error:
        manifest.errors.append(
            LogErrorEntry(
                namespace=result.namespace,
                pod=result.pod_name or result.job_name,
                container=config.collector_container_name,
                reason=result.error,
                service=UMF_RTI_SERVICE_ID,
            )
        )


def write_failure_artifacts(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    error: str,
    params: UmfRtiParams,
    config: UmfRtiConfig,
) -> None:
    """Write a minimal UMF RTI section when no Job could run at all."""
    summary = {
        "domain": params.umf_domain_id,
        "duration_seconds": params.umf_duration_seconds,
        "status": "failed",
        "error": error,
        "job": None,
        "pod": None,
        "counts": {
            "participants": 0,
            "topics": 0,
            "writers": 0,
            "readers": 0,
            "discovered_topic_handles": 0,
        },
        "sample_values_captured": False,
    }
    files = [
        "umf-rti/umf-rti-discovery.ndjson",
        "umf-rti/umf-rti-summary.json",
        "umf-rti/README.txt",
    ]
    zf.writestr(files[0], "")
    zf.writestr(files[1], json.dumps(summary, indent=2))
    zf.writestr(
        files[2],
        "UMF RTI discovery capture\n"
        "=========================\n\n"
        f"Domain: {params.umf_domain_id}\n"
        f"Status: failed\n\n"
        f"{error}\n\n"
        "No collection Job was created or no log could be read. "
        "See manifest.json for the recorded error.\n",
    )
    manifest.collected_files.extend(files)
    manifest.services.append(
        CollectedService(
            id=UMF_RTI_SERVICE_ID,
            label="UMF RTI",
            status="error",
            files=files,
            error=error,
        )
    )
    manifest.errors.append(
        LogErrorEntry(
            namespace=config.namespace,
            pod="(umf-rti-job)",
            container=config.collector_container_name,
            reason=error,
            service=UMF_RTI_SERVICE_ID,
        )
    )

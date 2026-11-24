import json
import subprocess
import logging

from kubernetes import client
from app.network_diagnostics.runtime_discovery import (
    find_ready_sandbox_id,
    extract_sandbox_pid,
    resolve_pod_pid,
)
from kubernetes.client.exceptions import ApiException


DIAGNOSTICS_NAMESPACE = "iomt-integration"
NETSHOOT_IMAGE = "iomt-netshoot-worker:dev"
CRI_SOCKET_PATH = "/run/k3s/containerd/containerd.sock"

logger = logging.getLogger(__name__)


class CaptureSchedulingCleanupError(RuntimeError):
    """Raised when Job scheduling and subsequent cleanup both fail."""

    def __init__(self, job_names: list[str]):
        self.job_names = job_names
        super().__init__(
            "Unable to request cleanup for Jobs: "
            + ", ".join(job_names)
        )

def build_netshoot_job(
    node_name: str,
    targets: list[dict] | None = None,
    duration_seconds: int = 60
) -> client.V1Job:
    """
    Build a temporary Netshoot Job for a specific node.
    This function does not submit the Job to Kubernetes.
    """

    if not node_name:
        raise ValueError("Node name is required")

    if type(duration_seconds) is not int or not 1 <= duration_seconds <= 600:
        raise ValueError("Capture duration must be 1-600 seconds")

    labels = {"app": "netshoot-diagnostics"}

    container = client.V1Container(
        name="netshoot",
        image=NETSHOOT_IMAGE,
        image_pull_policy="IfNotPresent",
        resources=client.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "128Mi"},
            limits={"cpu": "1000m", "memory": "256Mi"},
        ),
        env=[
            client.V1EnvVar(
                name="CAPTURE_TARGETS_JSON",
                value=json.dumps(targets if targets is not None else []),
            ),
            client.V1EnvVar(
                name="CAPTURE_DURATION_SECONDS",
                value=str(duration_seconds),
            ),
            client.V1EnvVar(
                name="CAPTURE_OUTPUT_DIR",
                value="/captures",
            ),
            client.V1EnvVar(
                name = "CAPTURE_COLLECT_GRACE_SECONDS",
                value = "360"
            )
        ],
        security_context=client.V1SecurityContext(
        privileged=True,
        run_as_user=0,
        ),
        volume_mounts=[
            client.V1VolumeMount(
                name="containerd-socket",
                mount_path=CRI_SOCKET_PATH,
            ),
            client.V1VolumeMount(
                name="capture-data",
                mount_path="/captures",
            ),
        ],
    )

    pod_spec = client.V1PodSpec(
        node_name=node_name,
        restart_policy="Never",
        containers=[container],
        host_pid=True,
        automount_service_account_token=False,
        volumes=[
            client.V1Volume(
                name="containerd-socket",
                host_path=client.V1HostPathVolumeSource(
                    path=CRI_SOCKET_PATH,
                    type="Socket",
                ),
            ),
            client.V1Volume(
                name="capture-data",
                empty_dir=client.V1EmptyDirVolumeSource(),
            ),
        ],
    )

    return client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            generate_name="netshoot-diagnostics-",
            namespace=DIAGNOSTICS_NAMESPACE,
            labels=labels,
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            active_deadline_seconds=duration_seconds + 600,
            ttl_seconds_after_finished=600,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=pod_spec,
            ),
        ),
    )



def submit_netshoot_job(
    batch_api: client.BatchV1Api,
    node_name: str,
    targets: list[dict] | None = None,
    duration_seconds: int = 60,
) -> str:
    """Create one Netshoot Job with the requested capture duration."""

    job = build_netshoot_job(
        node_name=node_name,
        targets=targets,
        duration_seconds=duration_seconds,
    )

    created_job = batch_api.create_namespaced_job(
        namespace=DIAGNOSTICS_NAMESPACE,
        body=job,
        _request_timeout=10,
    )

    return created_job.metadata.name


def get_netshoot_job_status(
    batch_api: client.BatchV1Api,
    job_name: str,
) -> dict:
    """
    Retrieve the execution status of a Netshoot Job.
    """

    job = batch_api.read_namespaced_job_status(
        name=job_name,
        namespace=DIAGNOSTICS_NAMESPACE,
        _request_timeout=10,
    )

    status = job.status

    conditions = {
        condition.type: condition.status
        for condition in (status.conditions or [])
    }

    if conditions.get("Complete") == "True":
        state = "complete"

    elif conditions.get("Failed") == "True":
        state = "failed"

    elif (status.active or 0) > 0:
        state = "active"

    else:
        state = "pending"

    return {
        "job_name": job_name,
        "state": state,
        "active": status.active or 0,
        "succeeded": status.succeeded or 0,
        "failed": status.failed or 0,
    }


def discover_capture_targets(
    core_api: client.CoreV1Api,
    namespace: str,
) -> dict:
    """Discover eligible Pods in a specific namespace."""

    response = core_api.list_namespaced_pod(
        namespace=namespace,
        _request_timeout=10,
    )

    return group_capture_targets(
        response.items,
        namespace=namespace,
    )


def discover_all_capture_targets(
    core_api: client.CoreV1Api,
) -> dict:
    """Discover Pod and host capture targets across the cluster."""

    response = core_api.list_pod_for_all_namespaces(
        _request_timeout=10,
    )

    targets_by_node = group_capture_targets(response.items)

    for node_name, targets in targets_by_node.items():
        if not any(
            target.get("host_network", False)
            for target in targets
        ):
            targets.append({
                "name": "host-network",
                "namespace": "(host)",
                "uid": f"host:{node_name}",
                "node": node_name,
                "host_network": True,
                "host_network_pods": [],
            })

    return targets_by_node


def group_capture_targets(
    pods: list,
    namespace: str | None = None,
) -> dict:
    """Filter eligible Pods and group them by node."""

    targets_by_node = {}
    host_targets_by_node = {}
    for pod in pods:
        metadata = pod.metadata
        spec = pod.spec
        status = pod.status

        if not metadata or not spec or not status:
            continue

        if status.phase != "Running":
            continue

        if metadata.deletion_timestamp is not None:
            continue

        if spec.host_network and namespace is not None:
            continue

        labels = getattr(metadata, "labels", None) or {}

        if labels.get("app") == "netshoot-diagnostics":
            continue

        target_namespace = (
            namespace
            if namespace is not None
            else metadata.namespace
        )

        if not all([
            metadata.name,
            metadata.uid,
            target_namespace,
            spec.node_name,
            status.pod_ip,
        ]):
            continue

        node = spec.node_name

        target = {
            "name": metadata.name,
            "namespace": target_namespace,
            "uid": metadata.uid,
            "ip": status.pod_ip,
        }

        if spec.host_network:
            if node in host_targets_by_node:
                host_targets_by_node[node]["host_network_pods"].append(
                    target
                )
                continue

            target = {
                **target,
                "host_network": True,
                "host_network_pods": [target],
            }

            host_targets_by_node[node] = target

        targets_by_node.setdefault(node, []).append(target)

    return targets_by_node

def filter_capture_targets_by_scope(
    targets_by_node: dict,
    scope: str,
) -> dict:
    """Keep only the targets matching the requested capture scope."""

    if scope not in ("both", "pod", "host"):
        raise ValueError("Invalid Netshoot capture scope")

    filtered_by_node = {}

    for node_name, targets in targets_by_node.items():

        if scope == "pod":
            selected = [
                target for target in targets
                if not target.get("host_network", False)
            ]

        elif scope == "host":
            selected = [
                target for target in targets
                if target.get("host_network", False)
            ]

        else:
            selected = targets

        if selected:
            filtered_by_node[node_name] = selected

    return filtered_by_node

def schedule_capture_jobs(
    core_api: client.CoreV1Api,
    batch_api: client.BatchV1Api,
    namespaces: list[str] | None,
    duration_seconds: int = 60,
    scope: str = "both",
) -> dict:
    """Schedule one Job per node, rolling back on partial failure."""

    targets_by_node = discover_targets_across_namespaces(
        core_api,
        namespaces,
    )

    targets_by_node = filter_capture_targets_by_scope(
        targets_by_node,
        scope,
    )

    scheduled_jobs = {}
    created_job_names = []

    try:
        for node_name, targets in targets_by_node.items():
            job_name = submit_netshoot_job(
                batch_api=batch_api,
                node_name=node_name,
                targets=targets,
                duration_seconds=duration_seconds,
            )

            created_job_names.append(job_name)

            scheduled_jobs[node_name] = {
                "job_name": job_name,
                "targets": targets,
            }

    except Exception:
        cleanup_failures = []

        # Reverse order: clean up the most recently created Jobs first.
        for job_name in reversed(created_job_names):
            try:
                batch_api.delete_namespaced_job(
                    name=job_name,
                    namespace=DIAGNOSTICS_NAMESPACE,
                    propagation_policy="Foreground",
                    _request_timeout=10,
                )

            except ApiException as exc:
                if exc.status != 404:
                    logger.exception(
                        "Could not delete Netshoot Job %s",
                        job_name,
                    )
                    cleanup_failures.append(job_name)

            except Exception:
                logger.exception(
                    "Could not delete Netshoot Job %s",
                    job_name,
                )
                cleanup_failures.append(job_name)

        if cleanup_failures:
            raise CaptureSchedulingCleanupError(
                cleanup_failures
            )

        # Preserve the original scheduling exception.
        raise

    return scheduled_jobs



def discover_targets_across_namespaces(
    core_api: client.CoreV1Api,
    namespaces: list[str] | None,
) -> dict:
    """
    Discover capture targets across approved namespaces
    and group all resulting pods by Kubernetes node.
    """
    if namespaces is None:
        return discover_all_capture_targets(core_api)

    targets_by_node = {}

    for namespace in dict.fromkeys(namespaces):
        namespace_targets = discover_capture_targets(
            core_api,
            namespace,
        )

        for node_name, targets in namespace_targets.items():
            targets_by_node.setdefault(node_name, []).extend(targets)

    return targets_by_node







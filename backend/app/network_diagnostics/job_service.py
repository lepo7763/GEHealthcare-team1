import json
from kubernetes import client


DIAGNOSTICS_NAMESPACE = "iomt-integration"
NETSHOOT_IMAGE = "docker.io/nicolaka/netshoot:v0.16"


def build_netshoot_job(
    node_name: str,
    targets: list[dict] | None = None,
) -> client.V1Job:
    """
    Build a temporary Netshoot Job for a specific node.
    This function does not submit the Job to Kubernetes.
    """

    if not node_name:
        raise ValueError("Node name is required")

    labels = {"app": "netshoot-diagnostics"}

    container = client.V1Container(
        name="netshoot",
        image=NETSHOOT_IMAGE,
        image_pull_policy="IfNotPresent",
        command=["/bin/sh", "-c", "echo Netshoot Job started"],
        resources=client.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "128Mi"},
            limits={"cpu": "250m", "memory": "256Mi"},
        ),
        env=[
            client.V1EnvVar(
                name="CAPTURE_TARGETS_JSON",
                value=json.dumps(targets if targets is not None else []),
            )
        ],
    )

    pod_spec = client.V1PodSpec(
        node_name=node_name,
        restart_policy="Never",
        containers=[container],
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
            active_deadline_seconds=120,
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
) -> str:
    """
    Submit a Netshoot Job to Kubernetes and return
    its generated name.
    """

    job = build_netshoot_job(node_name, targets)

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
    """
    Discover eligible running pods and group them by node.
    Does not deploy any Jobs.
    """

    response = core_api.list_namespaced_pod(
        namespace=namespace,
        _request_timeout=10,
    )

    targets_by_node = {}

    for pod in response.items:
        metadata = pod.metadata
        spec = pod.spec
        status = pod.status

        if not metadata or not spec or not status:
            continue

        if status.phase != "Running":
            continue

        if metadata.deletion_timestamp is not None:
            continue

        # Host-networked pods need separate capture handling.
        if spec.host_network:
            continue

        if not all([
            metadata.name,
            metadata.uid,
            spec.node_name,
            status.pod_ip,
        ]):
            continue

        node = spec.node_name

        target = {
            "name": metadata.name,
            "namespace": namespace,
            "uid": metadata.uid,
            "ip": status.pod_ip,
        }

        targets_by_node.setdefault(node, []).append(target)

    return targets_by_node



def schedule_capture_jobs(
    core_api: client.CoreV1Api,
    batch_api: client.BatchV1Api,
    namespaces: list[str],
) -> dict:
    """
    Discover targets across approved namespaces and
    schedule one diagnostic Job per node.
    """

    targets_by_node = discover_targets_across_namespaces(
        core_api,
        namespaces,
    )

    scheduled_jobs = {}

    for node_name, targets in targets_by_node.items():
        job_name = submit_netshoot_job(
            batch_api=batch_api,
            node_name=node_name,
            targets=targets,
        )

        scheduled_jobs[node_name] = {
            "job_name": job_name,
            "targets": targets,
        }

    return scheduled_jobs



def discover_targets_across_namespaces(
    core_api: client.CoreV1Api,
    namespaces: list[str],
) -> dict:
    """
    Discover capture targets across approved namespaces
    and group all resulting pods by Kubernetes node.
    """

    targets_by_node = {}

    for namespace in dict.fromkeys(namespaces):
        namespace_targets = discover_capture_targets(
            core_api,
            namespace,
        )

        for node_name, targets in namespace_targets.items():
            targets_by_node.setdefault(node_name, []).extend(targets)

    return targets_by_node


def find_ready_sandbox_id(
    pod_uid: str,
    sandboxes: list[dict],
) -> str:
    """
    Find the active container runtime sandbox
    corresponding to a Kubernetes Pod UID.
    """

    matches = []

    for sandbox in sandboxes:
        metadata = sandbox.get("metadata") or {}

        if metadata.get("uid") != pod_uid:
            continue

        if sandbox.get("state") != "SANDBOX_READY":
            continue

        matches.append(sandbox)

    if len(matches) != 1:
        raise ValueError(
            f"Expected one ready sandbox for pod {pod_uid}, "
            f"found {len(matches)}"
        )

    sandbox_id = matches[0].get("id")

    if not sandbox_id:
        raise ValueError("Ready sandbox has no ID")

    return sandbox_id







from kubernetes import client
from .schemas import PodInfo, PodListResponse
from fastapi import HTTPException
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream
import time


def list_pods(
    v1: client.CoreV1Api, namespace: str
) -> PodListResponse:

    pods = v1.list_namespaced_pod(
        namespace=namespace,
        _request_timeout=10,
    )

    results = []

    for pod in pods.items:
        if not pod.metadata or not pod.metadata.name:
            continue

        results.append(
            PodInfo(
                name=pod.metadata.name,
                status=pod.status.phase if pod.status else "Unknown",
                ip=pod.status.pod_ip if pod.status else None,
            )
        )

    return PodListResponse(
        namespace=namespace,
        pods=results,
    )

def read_running_pod(
    v1: client.CoreV1Api,
    pod_name: str,
    namespace: str
) -> PodInfo:
    
    try:
        pod = v1.read_namespaced_pod(
            name = pod_name,
            namespace = namespace,
            _request_timeout = 10
        )

    except ApiException as e:
        if e.status == 404:
            raise HTTPException(
                status_code = 404,
                detail = "Target pod not found"
            ) from e

        if e.status == 403:
            raise HTTPException(
                status_code = 403,
                detail = "Not authorized to inspect target pod"
            ) from e

        raise HTTPException(
            status_code = 503,
            detail = "Unable to inspect target pod"
        ) from e

    status = pod.status.phase if pod.status else "unknown"

    if status != "Running":
        raise HTTPException(
            status_code = 409,
            detail = "Target pod isn't running"
        )

    return pod

def validate_capture_target(
    v1: client.CoreV1Api,
    pod_name: str,
    namespace: str
) -> PodInfo:

    pod = read_running_pod(v1, pod_name, namespace)

    return PodInfo(
        name=pod_name,
        status=pod.status.phase,
        ip=pod.status.pod_ip
    )

def check_netshoot_tool(
        v1: client.CoreV1Api,
        pod_name: str,
        namespace: str
) -> str:

    #check that the target pod exists and is running
    pod = read_running_pod(v1, pod_name, namespace)

    state = get_netshoot_state(pod)

    if state != "running":
        raise HTTPException(
            status_code = 409,
            detail = f"Netshoot container is {state}"
        )

    #execute fixed diagnostic command inside netshoot
    try:
        return stream(
            v1.connect_post_namespaced_pod_exec,
            pod_name,
            namespace,
            container = "netshoot-capture",
            command = ["tcpdump", "--version"],
            stderr = True,
            stdin = False,
            stdout = True,
            tty = False,
            _request_timeout = 10
        )

    except ApiException as e:
        if e.status == 403:
            raise HTTPException(
                status_code = 403,
                detail = "Not authorized to execute diagnostics"
            )from e

        raise HTTPException(
            status_code= 503,
            detail = "Unable to execute diagnostic command"
        )from e

def netshoot_is_running(pod, container_name = "netshoot-capture") -> bool:
    #find ephemeral container information
    
    containers = getattr(
        pod.spec, "ephemeral_containers", None
    ) or []

    if not any(c.name == container_name for c in containers):
        return False

    #find current container runtime status
    statuses =getattr(
        pod.status, "ephemeral_container_statuses", None
    ) or []

    for status in statuses:
        if status.name == container_name:
            return getattr(status.state, "running", None) is not None

    return False

def netshoot_is_attached(
    pod,
    container_name="netshoot-capture"
) -> bool:

    containers = getattr(
        pod.spec, "ephemeral_containers", None
    ) or []

    return any(
        container.name == container_name
        for container in containers
    )

def get_netshoot_state(
        pod,
        container_name = "netshoot-capture"
) -> str:

    if not netshoot_is_attached(pod, container_name):
        return "missing"

    statuses = getattr(
        pod.status, "ephemeral_container_statuses", None
    ) or []

    for status in statuses:
        if status.name != container_name:
            continue

        state = getattr(status, "state", None)

        if state is None:
            return "not_ready"

        if getattr(state, "running", None) is not None:
            return "running"

        if getattr(state, "terminated", None) is not None:
            return "terminated"

        return "not_ready"

    return "not_ready"

def build_netshoot_container(pod) -> dict:
    #prevent duplicates or unnecessary attachemnts
    state = get_netshoot_state(pod)

    if state != "missing":
        raise HTTPException(
            status_code = 409,
            detail = f"Netshoot container is already {state}"
        )

    #select an existing application container to target
    app_containers = getattr(pod.spec, "containers", None) or []

    if not app_containers:
        raise HTTPException(
            status_code = 409,
            detail = "Target pod has no application containers"
        )

    target_name = app_containers[0].name

    return {
        "name": "netshoot-capture",
        "image": (
            "us-artifactory.apps.ge-healthcare.net/"
            "docker-axone-all/nicolaka/netshoot:v0.16"
        ),
        "imagePullPolicy": "Never",
        "targetContainerName": target_name,
        "command": [
            "/bin/sh",
            "-c",
            "while true; do sleep 3600; done"
        ]
    }

def attach_netshoot(
    v1: client.CoreV1Api,
    pod_name: str,
    namespace: str
) -> str:

    #retrieve and validate target pod
    pod = read_running_pod(v1, pod_name, namespace)

    #build ephemeral container
    container_config = build_netshoot_container(pod)

    #prepare kubernetes patch request
    patch_body = {
        "spec": {
            "ephemeralContainers": [container_config]
        }
    }

    try: 
        v1.patch_namespaced_pod_ephemeralcontainers(
            name = pod_name,
            namespace = namespace,
            body = patch_body,
            _request_timeout = 10
        )

    except ApiException as e:
        if e.status == 403:
            raise HTTPException(
                status_code = 403,
                detail = "Not authorized to attach Netshoot"
            ) from e

        if e.status == 409:
            raise HTTPException(
                status_code = 409,
                detail = "Pod configuration changed during attachment"
            ) from e

        raise HTTPException(
            status_code = 503,
            detail = "Unable to attach Netshoot"
        )from e

    return container_config["name"]


def wait_for_netshoot(
    v1: client.CoreV1Api,
    pod_name: str,
    namespace: str,
    max_attempts: int = 5,
    retry_interval: float = 1.0
) -> str:

    for attempt in range(max_attempts):
        pod = read_running_pod(v1, pod_name, namespace)
        state = get_netshoot_state(pod)

        if state == "running":
            return "netshoot-capture"

        if state == "terminated":
            raise HTTPException(
                status_code=409,
                detail="Netshoot terminated before becoming ready"
            )

        if attempt < max_attempts - 1:
            time.sleep(retry_interval)

    raise HTTPException(
        status_code=503,
        detail="Netshoot did not become ready"
    )

def attach_netshoot_and_wait(
    v1: client.CoreV1Api,
    pod_name: str,
    namespace: str
) -> str:

    #request attachment of diasgnostic container
    container_name = attach_netshoot(
        v1,
        pod_name,
        namespace
    )

    #wait until container is running
    ready_name = wait_for_netshoot(
        v1,
        pod_name,
        namespace
    )

    return ready_name


def ensure_netshoot_ready(
    v1: client.CoreV1Api,
    pod_name: str,
    namespace: str
) -> str:

    # Retrieve the application pod.
    pod = read_running_pod(v1, pod_name, namespace)

    # Determine whether Netshoot is already available.
    state = get_netshoot_state(pod)

    if state == "running":
        return "netshoot-capture"

    if state == "not_ready":
        return wait_for_netshoot(
            v1, pod_name, namespace
        )

    if state == "missing":
        return attach_netshoot_and_wait(
            v1, pod_name, namespace
        )

    if state == "terminated":
        raise HTTPException(
            status_code=409,
            detail="Existing Netshoot container has terminated"
        )

    raise HTTPException(
        status_code=503,
        detail="Unknown Netshoot container state"
    )

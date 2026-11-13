"""Create a temporary Kubernetes Job to capture and analyze network traffic."""

import base64
import re
import shlex
import time
import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Callable, Optional

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from app.tshark.analyzer import analyze_capture
from app.tshark.config import (
    TSHARK_CAPTURE_CONTAINER,
    TSHARK_CAPTURE_VOLUME,
    TSHARK_DIAGNOSTICS_NAMESPACE,
    TSHARK_DURATION,
    TSHARK_IMAGE,
    TSHARK_INTERFACE,
    TSHARK_MAX_CAPTURE_SIZE_KB,
    TSHARK_MAX_DURATION,
    TSHARK_MAX_PACKETS,
    TSHARK_POLL_INTERVAL,
    TSHARK_REQUEST_TIMEOUT,
)

ANALYSIS_BEGIN = "__TSHARK_ANALYSIS_BEGIN__"
ANALYSIS_END = "__TSHARK_ANALYSIS_END__"
PCAP_BEGIN = "__TSHARK_PCAP_BEGIN__"
PCAP_END = "__TSHARK_PCAP_END__"
CAPTURE_STARTED = "__TSHARK_CAPTURE_STARTED__"
_CAPTURE_LOCK = Lock()


class TSharkCaptureError(RuntimeError):
    """A capture workload failed or did not return usable artifacts."""

    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.status_code = status_code


def _analysis_command() -> str:
    fields = (
        "frame.len",
        "frame.protocols",
        "ip.src",
        "ip.dst",
        "ipv6.src",
        "ipv6.dst",
        "tcp.srcport",
        "tcp.dstport",
        "tcp.flags.reset",
        "tcp.analysis.retransmission",
        "dns.flags.rcode",
    )
    arguments = " ".join(f"-e {field}" for field in fields)
    return (
        f"tshark -r /captures/capture.pcapng -T fields "
        f"-E separator=, -E header=y -E quote=d {arguments}"
    )


def build_capture_job(
    duration: int,
    capture_id: Optional[str] = None,
) -> client.V1Job:
    """Build a bounded, non-host-networked Job that captures its own interface."""
    if not TSHARK_IMAGE:
        raise ValueError("TSHARK_IMAGE must be configured")
    if not TSHARK_DIAGNOSTICS_NAMESPACE:
        raise ValueError("TSHARK_DIAGNOSTICS_NAMESPACE must be configured")
    if not 1 <= duration <= TSHARK_MAX_DURATION:
        raise ValueError(
            f"Capture duration must be between 1 and {TSHARK_MAX_DURATION} seconds."
        )

    capture_id = capture_id or uuid.uuid4().hex
    if not re.fullmatch(r"[a-z0-9-]{1,32}", capture_id):
        raise ValueError("Capture ID must contain only lowercase letters, digits, or hyphens.")
    labels = {
        "app.kubernetes.io/name": "iomt-tshark-capture",
        "iomt.gehealthcare.com/capture-id": capture_id,
    }
    script = "\n".join(
        (
            "set -eu",
            f"echo {CAPTURE_STARTED}",
            "tshark "
            f"-i {shlex.quote(TSHARK_INTERFACE)} -p -n "
            f"-a duration:{duration} "
            f"-a filesize:{TSHARK_MAX_CAPTURE_SIZE_KB} "
            f"-c {TSHARK_MAX_PACKETS} "
            "-w /captures/capture.pcapng",
            'test -s /captures/capture.pcapng || { echo "Capture file is missing or empty" >&2; exit 1; }',
            f"echo {ANALYSIS_BEGIN}",
            _analysis_command(),
            f"echo {ANALYSIS_END}",
            f"echo {PCAP_BEGIN}",
            "base64 /captures/capture.pcapng",
            f"echo {PCAP_END}",
        )
    )

    container = client.V1Container(
        name=TSHARK_CAPTURE_CONTAINER,
        image=TSHARK_IMAGE,
        image_pull_policy="IfNotPresent",
        command=["/bin/sh", "-c", script],
        resources=client.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "128Mi"},
            limits={"cpu": "500m", "memory": "256Mi"},
        ),
        security_context=client.V1SecurityContext(
            privileged=False,
            allow_privilege_escalation=False,
        ),
        volume_mounts=[
            client.V1VolumeMount(
                name=TSHARK_CAPTURE_VOLUME,
                mount_path="/captures",
            )
        ],
    )
    pod_spec = client.V1PodSpec(
        restart_policy="Never",
        containers=[container],
        automount_service_account_token=False,
        volumes=[
            client.V1Volume(
                name=TSHARK_CAPTURE_VOLUME,
                empty_dir=client.V1EmptyDirVolumeSource(
                    size_limit="12Mi",
                ),
            )
        ],
    )
    return client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name=f"tshark-capture-{capture_id[:16]}",
            namespace=TSHARK_DIAGNOSTICS_NAMESPACE,
            labels=labels,
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            active_deadline_seconds=duration + 180,
            ttl_seconds_after_finished=300,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=pod_spec,
            ),
        ),
    )


def _create_or_reuse_job(
    batch: client.BatchV1Api,
    job: client.V1Job,
) -> str:
    name = job.metadata.name
    namespace = TSHARK_DIAGNOSTICS_NAMESPACE
    try:
        batch.read_namespaced_job(name=name, namespace=namespace)
        return name
    except ApiException as exc:
        if exc.status != 404:
            raise

    try:
        batch.create_namespaced_job(
            namespace=namespace,
            body=job,
            _request_timeout=TSHARK_REQUEST_TIMEOUT,
        )
        return name
    except ApiException as exc:
        if exc.status != 409:
            raise
        batch.read_namespaced_job(name=name, namespace=namespace)
        return name


def _pod_failure_message(pod: client.V1Pod) -> Optional[str]:
    status = pod.status
    if status is None:
        return None

    for condition in status.conditions or []:
        if condition.type == "PodScheduled" and condition.status == "False":
            return f"Capture Job could not be scheduled: {condition.message or condition.reason}"

    for container_status in status.container_statuses or []:
        waiting = getattr(container_status.state, "waiting", None)
        if waiting and waiting.reason in ("ErrImagePull", "ImagePullBackOff"):
            return f"Capture image could not be pulled: {waiting.message or waiting.reason}"
    return None


def _read_capture_pod(
    core: client.CoreV1Api,
    job_name: str,
) -> Optional[client.V1Pod]:
    pods = core.list_namespaced_pod(
        namespace=TSHARK_DIAGNOSTICS_NAMESPACE,
        label_selector=f"job-name={job_name}",
        _request_timeout=TSHARK_REQUEST_TIMEOUT,
    )
    if not pods.items:
        return None
    return pods.items[0]


def _read_job_logs(
    core: client.CoreV1Api,
    pod_name: str,
) -> str:
    return core.read_namespaced_pod_log(
        name=pod_name,
        namespace=TSHARK_DIAGNOSTICS_NAMESPACE,
        container=TSHARK_CAPTURE_CONTAINER,
        timestamps=False,
        _request_timeout=TSHARK_REQUEST_TIMEOUT,
    )


def _section(logs: str, begin: str, end: str) -> str:
    try:
        return logs.split(begin, 1)[1].split(end, 1)[0].strip()
    except IndexError as exc:
        raise TSharkCaptureError(
            f"Capture workload output is missing the {begin} artifact marker."
        ) from exc


def _wait_for_capture(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    job_name: str,
    duration: int,
    on_state: Optional[Callable[[str], None]],
    on_progress: Optional[Callable[[int, int], None]],
) -> tuple[client.V1Pod, str]:
    deadline = time.monotonic() + duration + 180
    capture_started_at = None

    while time.monotonic() < deadline:
        job = batch.read_namespaced_job_status(
            name=job_name,
            namespace=TSHARK_DIAGNOSTICS_NAMESPACE,
            _request_timeout=TSHARK_REQUEST_TIMEOUT,
        )
        pod = _read_capture_pod(core, job_name)
        job_status = job.status
        conditions = {
            condition.type: condition.status
            for condition in (job_status.conditions or [] if job_status else [])
        }

        if pod is None:
            if conditions.get("Failed") == "True":
                raise TSharkCaptureError(
                    "Capture Job failed before its Pod was created; check workload permissions and scheduling.",
                    status_code=503,
                )
            time.sleep(TSHARK_POLL_INTERVAL)
            continue
        pod_error = _pod_failure_message(pod)
        if pod_error:
            raise TSharkCaptureError(pod_error, status_code=503)

        logs = ""
        pod_status = pod.status
        container_statuses = pod_status.container_statuses if pod_status else None
        container_ready_to_read = any(
            status.state
            and (
                status.state.running is not None
                or status.state.terminated is not None
            )
            for status in (container_statuses or [])
        )
        if container_ready_to_read:
            logs = _read_job_logs(core, pod.metadata.name)
        if capture_started_at is None and CAPTURE_STARTED in logs:
            capture_started_at = time.monotonic()
            if on_state:
                on_state("capturing")

        if capture_started_at is not None and on_progress:
            elapsed = max(0, int(time.monotonic() - capture_started_at))
            on_progress(min(duration, elapsed), duration)

        if conditions.get("Complete") == "True":
            if on_state:
                on_state("processing")
            if not logs:
                logs = _read_job_logs(core, pod.metadata.name)
            return pod, logs
        if conditions.get("Failed") == "True":
            detail = next(
                (
                    condition.message or condition.reason
                    for condition in (
                        job_status.conditions or [] if job_status else []
                    )
                    if condition.type == "Failed"
                ),
                "Capture Job failed.",
            )
            try:
                failure_logs = _read_job_logs(core, pod.metadata.name).strip()
            except ApiException:
                failure_logs = ""
            if failure_logs:
                detail = f"{detail} Capture output: {failure_logs[-1000:]}"
            raise TSharkCaptureError(detail)

        if capture_started_at is None and on_state:
            on_state("deploying")
        time.sleep(TSHARK_POLL_INTERVAL)

    raise TSharkCaptureError(
        f"Capture Job timed out after {duration} seconds plus startup allowance.",
        status_code=504,
    )


def _capture_error(exc: ApiException) -> TSharkCaptureError:
    if exc.status == 403:
        return TSharkCaptureError(
            "Kubernetes denied capture Job access. Grant the backend ServiceAccount "
            "least-privilege Job, Pod-list, and Pod-log permissions in the diagnostics namespace.",
            status_code=403,
        )
    if exc.status == 404:
        return TSharkCaptureError(
            f"Diagnostics namespace {TSHARK_DIAGNOSTICS_NAMESPACE!r} was not found.",
            status_code=503,
        )
    return TSharkCaptureError(
        f"Kubernetes capture workload request failed ({exc.status}): {exc.reason}"
    )


def cleanup_capture_job(batch: client.BatchV1Api, job_name: str) -> None:
    try:
        batch.delete_namespaced_job(
            name=job_name,
            namespace=TSHARK_DIAGNOSTICS_NAMESPACE,
            propagation_policy="Foreground",
            grace_period_seconds=0,
            _request_timeout=TSHARK_REQUEST_TIMEOUT,
        )
    except ApiException as exc:
        if exc.status != 404:
            raise TSharkCaptureError(
                f"Capture Job {job_name} could not be cleaned up: "
                f"{exc.reason or exc.status}."
            ) from exc


def _capture_network(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    duration: Optional[int] = None,
    include_pcap: bool = False,
    on_state: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    capture_id: Optional[str] = None,
    defer_cleanup: bool = False,
) -> dict:
    """Run one temporary capture Job and return analysis plus optional PCAPNG bytes.

    The Job has no host network or host PID access. It only sees traffic visible
    to its own pod interface; this does not provide cluster-wide visibility.
    """
    capture_duration = TSHARK_DURATION if duration is None else duration
    if type(capture_duration) is not int or not 1 <= capture_duration <= TSHARK_MAX_DURATION:
        raise ValueError(
            f"Capture duration must be between 1 and {TSHARK_MAX_DURATION} seconds."
        )

    job = build_capture_job(capture_duration, capture_id=capture_id)
    job_name = None
    started_at = datetime.now(timezone.utc)
    primary_error = None
    try:
        if on_state:
            on_state("pending")
            on_state("deploying")
        job_name = _create_or_reuse_job(batch, job)
        pod, logs = _wait_for_capture(
            core, batch, job_name, capture_duration, on_state, on_progress
        )
        analysis_csv = _section(logs, ANALYSIS_BEGIN, ANALYSIS_END)
        pcap_base64 = "".join(_section(logs, PCAP_BEGIN, PCAP_END).split())
        try:
            pcap_bytes = base64.b64decode(pcap_base64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise TSharkCaptureError("Capture Job returned invalid PCAPNG data.") from exc
        if not pcap_bytes:
            raise TSharkCaptureError("Capture file is missing or empty.")

        analysis = analyze_capture(analysis_csv)
        packets_analyzed = analysis["packetsAnalyzed"]
        packets_captured = packets_analyzed
        capture_state = "completed" if packets_captured else "failed"
        if capture_state == "failed" and on_state:
            on_state("failed")
        elif on_state:
            on_state("completed")
        result = {
            "status": capture_state,
            "captureState": capture_state,
            "error": (
                None
                if packets_captured
                else "No packets were captured on the workload interface; network visibility is not established."
            ),
            "namespace": TSHARK_DIAGNOSTICS_NAMESPACE,
            "workload": job_name,
            "pod": pod.metadata.name,
            "interface": TSHARK_INTERFACE,
            "durationSeconds": capture_duration,
            "startedAt": started_at.isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "captureLimits": {
                "maxPackets": TSHARK_MAX_PACKETS,
                "maxDurationSeconds": TSHARK_MAX_DURATION,
                "maxCaptureBytes": TSHARK_MAX_CAPTURE_SIZE_KB * 1024,
            },
            "packetsCaptured": packets_captured,
            "packetsAnalyzed": packets_analyzed,
            **analysis,
        }
        if include_pcap:
            result["pcapBytes"] = pcap_bytes
        if defer_cleanup:
            result["cleanupJobName"] = job_name
        return result
    except ApiException as exc:
        converted = _capture_error(exc)
        primary_error = converted
        if on_state:
            on_state("failed")
        raise converted from exc
    except Exception as exc:
        primary_error = exc
        if on_state:
            on_state("failed")
        raise
    except BaseException as exc:
        primary_error = exc
        if on_state:
            on_state("cancelled")
        raise
    finally:
        if job_name and (not defer_cleanup or primary_error is not None):
            try:
                cleanup_capture_job(batch, job_name)
            except TSharkCaptureError as cleanup_error:
                if primary_error is not None:
                    message = (
                        f"{primary_error} Additionally, {cleanup_error}"
                    )
                    raise TSharkCaptureError(message) from primary_error
                raise


def capture_network(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    duration: Optional[int] = None,
    include_pcap: bool = False,
    on_state: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    capture_id: Optional[str] = None,
    defer_cleanup: bool = False,
) -> dict:
    if not _CAPTURE_LOCK.acquire(blocking=False):
        raise TSharkCaptureError(
            "Another TShark capture is already in progress.",
            status_code=409,
        )
    try:
        return _capture_network(
            core=core,
            batch=batch,
            duration=duration,
            include_pcap=include_pcap,
            on_state=on_state,
            on_progress=on_progress,
            capture_id=capture_id,
            defer_cleanup=defer_cleanup,
        )
    finally:
        _CAPTURE_LOCK.release()

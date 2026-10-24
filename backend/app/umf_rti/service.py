import json
import time
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from .config import UmfRtiConfig, get_umf_rti_config
from .schemas import UmfRtiCaptureResult, UmfRtiParams

UMF_RTI_SERVICE_ID = "umf-rti"
UMF_RTI_LABEL = "UMF RTI"

# Container waiting reasons that indicate the Pod will never start (fail fast instead of waiting minutes)
FATAL_WAITING_REASONS = frozenset(
    {
        "ImagePullBackOff",
        "ErrImagePull",
        "CreateContainerConfigError",
        "CreateContainerError",
        "InvalidImageName",
    }
)


class UmfRtiPrerequisiteError(Exception):
    """Raised when required Secrets/ConfigMaps or router ports are missing before Job creation."""

    pass


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def check_prerequisites(core_v1: client.CoreV1Api, cfg: UmfRtiConfig) -> None:
    """
    Verifies that the QoS ConfigMap and the 3 Secrets (SDDS, Collector JAR, License)
    exist in `iomt-integration` before we attempt to launch a Job.
    If any are missing, raises UmfRtiPrerequisiteError with an actionable message.
    """
    missing: List[str] = []

    try:
        cm = core_v1.read_namespaced_config_map(
            name=cfg.qos_configmap, namespace=cfg.namespace, _request_timeout=10
        )
        if not cm.data or cfg.qos_key not in cm.data:
            missing.append(f"ConfigMap '{cfg.qos_configmap}' (missing key '{cfg.qos_key}')")
    except ApiException as e:
        if e.status == 404:
            missing.append(f"ConfigMap '{cfg.qos_configmap}'")
        else:
            raise UmfRtiPrerequisiteError(
                f"Failed to check ConfigMap '{cfg.qos_configmap}' in '{cfg.namespace}': {e.reason}"
            ) from e

    for secret_name in (cfg.sdds_secret, cfg.collector_secret, cfg.license_secret):
        try:
            core_v1.read_namespaced_secret(
                name=secret_name, namespace=cfg.namespace, _request_timeout=10
            )
        except ApiException as e:
            if e.status == 404:
                missing.append(f"Secret '{secret_name}'")
            else:
                raise UmfRtiPrerequisiteError(
                    f"Failed to check Secret '{secret_name}' in '{cfg.namespace}': {e.reason}"
                ) from e

    if missing:
        joined = ", ".join(missing)
        raise UmfRtiPrerequisiteError(
            f"Missing UMF RTI prerequisite resource(s) in namespace '{cfg.namespace}': {joined}. "
            "Run './kubernetes/umf-rti-setup.sh' to provision them."
        )


def resolve_router_peer(
    core_v1: client.CoreV1Api, domain_id: int, cfg: UmfRtiConfig
) -> str:
    """
    Resolves the NDDS_DISCOVERY_PEERS locator for the given DDS domain.

    Why we do this dynamically:
    The live platform blocks multicast in CommissioningQoS.xml. Instead, DDS participants
    discover each other via the headless 'axone-router-1' Service in namespace 'pm'.
    That service exposes UDP ports named like 'domain-12-10410' or 'domain-32-15410'.
    We inspect the Service spec, find all ports matching 'domain-{domain_id}-*', pick the
    lowest port number (the entry peer port), and return:
        udpv4://axone-router-1.pm.svc.cluster.local:<port>
    """
    if cfg.discovery_peers_override.strip():
        return cfg.discovery_peers_override.strip()

    try:
        svc = core_v1.read_namespaced_service(
            name=cfg.router_service,
            namespace=cfg.router_namespace,
            _request_timeout=10,
        )
    except ApiException as e:
        raise UmfRtiPrerequisiteError(
            f"Could not read DDS router service '{cfg.router_namespace}/{cfg.router_service}' "
            f"(HTTP {e.status}: {e.reason}). Set IOMT_UMF_RTI_DISCOVERY_PEERS to override."
        ) from e

    prefix = f"domain-{domain_id}-"
    matching_ports: List[int] = []
    for port_obj in (svc.spec.ports if svc and svc.spec else None) or []:
        name = port_obj.name or ""
        if name.startswith(prefix) and port_obj.port:
            matching_ports.append(int(port_obj.port))

    if not matching_ports:
        raise UmfRtiPrerequisiteError(
            f"No port matching '{prefix}*' found on service "
            f"'{cfg.router_namespace}/{cfg.router_service}' for domain {domain_id}."
        )

    chosen_port = min(matching_ports)
    fqdn = f"{cfg.router_service}.{cfg.router_namespace}.svc.cluster.local"
    return f"udpv4://{fqdn}:{chosen_port}"


def build_job(
    cfg: UmfRtiConfig,
    params: UmfRtiParams,
    router_peer: str,
    job_name: Optional[str] = None,
) -> client.V1Job:
    """
    Constructs the Kubernetes V1Job spec for a single UMF RTI capture session.

    Security & Isolation highlights:
    - Uses the cached platform runtime image (imagePullPolicy: IfNotPresent).
    - Mounts our tiny collector JAR, license, QoS XML, and SDDS certs read-only.
    - Runs as non-root UID/GID 2017 with all Linux capabilities dropped and no ServiceAccount token.
    - Never uses hostNetwork; communicates over standard cluster DNS/pod network.
    """
    name = job_name or f"umf-rti-capture-{uuid.uuid4().hex[:8]}"
    labels = {
        "app.kubernetes.io/name": "umf-rti",
        "app.kubernetes.io/managed-by": "iomt-analysis-tool",
        "iomt-analysis-tool/service": UMF_RTI_SERVICE_ID,
        "iomt-analysis-tool/job": name,
    }

    command = [
        "/bin/sh",
        "-c",
        (
            "exec java "
            "-cp /opt/umf-rti/umf-rti-collector.jar:/opt/axone-umfcompatibilitycheck/lib/nddsjava.jar "
            "-Djava.library.path=/opt/axone-umfcompatibilitycheck/lib/overrides:/opt/axone-umfcompatibilitycheck/lib "
            "com.gehc.iomt.umfrti.UmfRtiCollector "
            '--domain "$UMF_DOMAIN_ID" '
            '--duration "$UMF_DURATION_SECONDS" '
            "--qos-file /opt/axone-tools/qos/CommissioningQoS.xml "
            '--qos-profile "$UMF_QOS_PROFILE"'
        ),
    ]

    env = [
        client.V1EnvVar(
            name="LD_LIBRARY_PATH",
            value="/opt/axone-umfcompatibilitycheck/lib/overrides:/opt/axone-umfcompatibilitycheck/lib",
        ),
        client.V1EnvVar(name="SDDS_HOME", value="/opt/axone-tools/sdds"),
        client.V1EnvVar(
            name="NDDS_QOS_PROFILES", value="/opt/axone-tools/qos/CommissioningQoS.xml"
        ),
        client.V1EnvVar(name="DDS_SECURE", value="secure"),
        client.V1EnvVar(name="DDS_INTERFACES", value=cfg.dds_interfaces),
        client.V1EnvVar(name="DDS_INTERFACES_MONITORING", value=cfg.dds_interfaces),
        client.V1EnvVar(name="NDDS_DISCOVERY_PEERS", value=router_peer),
        client.V1EnvVar(
            name="RTI_LICENSE_FILE", value="/opt/umf-rti-license/rti_license.dat"
        ),
        client.V1EnvVar(name="HOME", value="/tmp"),
        client.V1EnvVar(name="UMF_DOMAIN_ID", value=str(params.umf_domain_id)),
        client.V1EnvVar(
            name="UMF_DURATION_SECONDS", value=str(params.umf_duration_seconds)
        ),
        client.V1EnvVar(name="UMF_QOS_PROFILE", value=cfg.qos_profile),
    ]

    volume_mounts = [
        client.V1VolumeMount(
            name="collector-jar", mount_path="/opt/umf-rti", read_only=True
        ),
        client.V1VolumeMount(
            name="rti-license", mount_path="/opt/umf-rti-license", read_only=True
        ),
        client.V1VolumeMount(
            name="qos-config", mount_path="/opt/axone-tools/qos", read_only=True
        ),
        client.V1VolumeMount(
            name="sdds-certs", mount_path="/opt/axone-tools/sdds", read_only=True
        ),
    ]

    volumes = [
        client.V1Volume(
            name="collector-jar",
            secret=client.V1SecretVolumeSource(secret_name=cfg.collector_secret),
        ),
        client.V1Volume(
            name="rti-license",
            secret=client.V1SecretVolumeSource(secret_name=cfg.license_secret),
        ),
        client.V1Volume(
            name="qos-config",
            config_map=client.V1ConfigMapVolumeSource(name=cfg.qos_configmap),
        ),
        client.V1Volume(
            name="sdds-certs",
            secret=client.V1SecretVolumeSource(secret_name=cfg.sdds_secret),
        ),
    ]

    container = client.V1Container(
        name="umf-rti",
        image=cfg.image,
        image_pull_policy="IfNotPresent",
        command=command,
        env=env,
        volume_mounts=volume_mounts,
        resources=client.V1ResourceRequirements(
            requests={"cpu": cfg.cpu_request, "memory": cfg.memory_request},
            limits={"cpu": cfg.cpu_limit, "memory": cfg.memory_limit},
        ),
        security_context=client.V1SecurityContext(
            run_as_non_root=True,
            run_as_user=2017,
            allow_privilege_escalation=False,
            capabilities=client.V1Capabilities(drop=["ALL"]),
        ),
    )

    pull_secrets = (
        [client.V1LocalObjectReference(name=cfg.image_pull_secret)]
        if cfg.image_pull_secret
        else None
    )

    pod_spec = client.V1PodSpec(
        restart_policy="Never",
        host_network=False,
        dns_policy="ClusterFirst",
        automount_service_account_token=False,
        image_pull_secrets=pull_secrets,
        security_context=client.V1PodSecurityContext(
            run_as_non_root=True,
            run_as_user=2017,
            fs_group=2017,
        ),
        containers=[container],
        volumes=volumes,
    )

    job_spec = client.V1JobSpec(
        backoff_limit=0,
        active_deadline_seconds=params.umf_duration_seconds + 300,
        ttl_seconds_after_finished=cfg.job_ttl_seconds,
        template=client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=labels),
            spec=pod_spec,
        ),
    )

    return client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=cfg.namespace,
            labels=labels,
        ),
        spec=job_spec,
    )


def parse_ndjson_output(
    raw_text: str, max_bytes: int
) -> Tuple[str, int, bool, int, int, int, int, Optional[str], List[str], Optional[str]]:
    """
    Parses the collector pod's stdout line-by-line.
    Counts discovered participants, topics, writers, and readers.
    Non-JSON lines (e.g. JVM or RTI warnings printed to stdout) are recorded as warnings
    while keeping only clean NDJSON lines in `ndjson_text` (or preserving raw lines if needed).
    """
    encoded = raw_text.encode("utf-8", errors="replace")
    truncated = len(encoded) >= max_bytes

    # If limit_bytes truncated the final line mid-JSON, drop the incomplete trailing fragment
    if truncated and raw_text and not raw_text.endswith("\n"):
        last_nl = raw_text.rfind("\n")
        if last_nl != -1:
            raw_text = raw_text[: last_nl + 1]

    participants = 0
    topics = 0
    writers = 0
    readers = 0
    collector_version: Optional[str] = None
    warnings: List[str] = []
    collector_error: Optional[str] = None

    for line_num, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"Line {line_num} was not valid JSON: {line[:120]}")
            continue

        if not isinstance(obj, dict):
            warnings.append(f"Line {line_num} was not a JSON object")
            continue

        rec_type = obj.get("type")
        if rec_type == "participant":
            participants += 1
        elif rec_type == "topic":
            topics += 1
        elif rec_type == "writer":
            writers += 1
        elif rec_type == "reader":
            readers += 1
        elif rec_type == "summary":
            collector_version = obj.get("collector_version")
        elif rec_type == "error":
            collector_error = obj.get("message") or "Collector reported an error"
        else:
            warnings.append(f"Line {line_num} had unknown record type '{rec_type}'")

    if truncated:
        warnings.append(f"Output reached max_bytes limit ({max_bytes} bytes) and was truncated.")

    return (
        raw_text,
        len(encoded),
        truncated,
        participants,
        topics,
        writers,
        readers,
        collector_version,
        warnings,
        collector_error,
    )


def _find_job_pod(
    core_v1: client.CoreV1Api, namespace: str, job_name: str
) -> Optional[client.V1Pod]:
    """Finds the Pod created by our Kubernetes Job using its label selector."""
    pods = core_v1.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"iomt-analysis-tool/job={job_name}",
        _request_timeout=10,
    ).items
    return pods[0] if pods else None


def _extract_pod_state(
    pod: Optional[client.V1Pod],
) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Returns (waiting_reason, terminated_exit_code, terminated_message)
    from the Pod's first container status.
    """
    if not pod or not pod.status or not pod.status.container_statuses:
        return None, None, None
    st = pod.status.container_statuses[0]
    if not st.state:
        return None, None, None
    if st.state.waiting:
        return st.state.waiting.reason, None, st.state.waiting.message
    if st.state.terminated:
        return (
            None,
            st.state.terminated.exit_code,
            st.state.terminated.message or st.state.terminated.reason,
        )
    return None, None, None


def capture_umf_rti(
    core_v1: client.CoreV1Api,
    batch_v1: client.BatchV1Api,
    params: UmfRtiParams,
    cfg: Optional[UmfRtiConfig] = None,
    on_tick: Optional[Callable[[int, int, str], None]] = None,
) -> UmfRtiCaptureResult:
    """
    Full lifecycle runner for a UMF RTI diagnostic capture:
    1. Resolves the router peer for `params.umf_domain_id`.
    2. Creates the Job in `cfg.namespace`.
    3. Polls until the Job finishes, fails fast on image/config errors, or times out.
    4. Reads the Pod's stdout log and parses the NDJSON records.
    5. Always deletes the Job (and its Pod via propagationPolicy='Background') in `finally`.
    """
    cfg = cfg or get_umf_rti_config()
    check_prerequisites(core_v1, cfg)
    router_peer = resolve_router_peer(core_v1, params.umf_domain_id, cfg)

    job_manifest = build_job(cfg, params, router_peer)
    job_name = job_manifest.metadata.name
    started_at = _utcnow_iso()
    start_monotonic = time.monotonic()
    wait_timeout = params.umf_duration_seconds + 360

    pod_name: Optional[str] = None
    exit_code: Optional[int] = None
    run_error: Optional[str] = None
    raw_log = ""

    try:
        batch_v1.create_namespaced_job(
            namespace=cfg.namespace, body=job_manifest, _request_timeout=15
        )

        while True:
            elapsed = int(time.monotonic() - start_monotonic)
            capped_elapsed = min(elapsed, params.umf_duration_seconds)
            if on_tick:
                on_tick(
                    capped_elapsed,
                    params.umf_duration_seconds,
                    f"Capturing UMF RTI (domain {params.umf_domain_id})",
                )

            # Inspect Job status
            job_obj = batch_v1.read_namespaced_job(
                name=job_name, namespace=cfg.namespace, _request_timeout=10
            )
            pod = _find_job_pod(core_v1, cfg.namespace, job_name)
            if pod and pod.metadata and pod.metadata.name:
                pod_name = pod.metadata.name

            waiting_reason, term_code, term_msg = _extract_pod_state(pod)
            if term_code is not None:
                exit_code = term_code

            # Did the Job succeed?
            if job_obj.status and (job_obj.status.succeeded or 0) > 0:
                if exit_code is None:
                    exit_code = 0
                break

            # Did the Job fail?
            if job_obj.status and (job_obj.status.failed or 0) > 0:
                run_error = (
                    f"UMF RTI collector exited with code {exit_code}"
                    if exit_code is not None
                    else f"UMF RTI Job failed ({term_msg or 'unknown reason'})"
                )
                break

            # Fast-fail if the container is stuck in ImagePullBackOff or config error
            if waiting_reason in FATAL_WAITING_REASONS and elapsed >= min(
                cfg.startup_fast_fail_seconds, 10
            ):
                run_error = (
                    f"UMF RTI container failed to start ({waiting_reason}): "
                    f"{term_msg or 'check image and secrets in ' + cfg.namespace}"
                )
                break

            # Overall timeout safety net
            if elapsed >= wait_timeout:
                extra = f" (pod waiting: {waiting_reason})" if waiting_reason else ""
                run_error = (
                    f"UMF RTI capture timed out after {elapsed}s waiting for Job '{job_name}'{extra}."
                )
                break

            time.sleep(cfg.poll_interval_seconds)

        # Read the pod log if a pod was created
        if pod_name:
            try:
                raw_log = (
                    core_v1.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=cfg.namespace,
                        container="umf-rti",
                        limit_bytes=params.umf_max_bytes,
                        timestamps=False,
                        _request_timeout=30,
                    )
                    or ""
                )
            except ApiException as e:
                # If the container never started (e.g. ImagePullBackOff), reading logs returns 400
                if not run_error:
                    run_error = f"Could not read logs from pod '{pod_name}': {e.reason}"

    finally:
        # Always clean up the Job and its Pod so iomt-integration stays empty
        try:
            batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=cfg.namespace,
                propagation_policy="Background",
                _request_timeout=15,
            )
        except Exception:
            pass

    finished_at = _utcnow_iso()
    (
        ndjson_text,
        log_bytes,
        truncated,
        participants_count,
        topics_count,
        writers_count,
        readers_count,
        collector_version,
        warnings,
        collector_error,
    ) = parse_ndjson_output(raw_log, params.umf_max_bytes)

    final_error = run_error or collector_error
    if exit_code not in (None, 0) and not final_error:
        final_error = f"UMF RTI collector exited with code {exit_code}"

    return UmfRtiCaptureResult(
        domain_id=params.umf_domain_id,
        duration_seconds=params.umf_duration_seconds,
        router_peer=router_peer,
        image=cfg.image,
        namespace=cfg.namespace,
        job_name=job_name,
        pod_name=pod_name,
        started_at_utc=started_at,
        finished_at_utc=finished_at,
        exit_code=exit_code,
        ndjson_text=ndjson_text,
        log_bytes=log_bytes,
        truncated=truncated,
        participants_count=participants_count,
        topics_count=topics_count,
        writers_count=writers_count,
        readers_count=readers_count,
        collector_version=collector_version,
        warnings=warnings,
        error=final_error,
    )


def write_umf_rti_artifacts(
    zf: zipfile.ZipFile, result: UmfRtiCaptureResult
) -> List[str]:
    """
    Writes the 3 UMF RTI files into the diagnostic ZIP archive:
      - umf-rti/umf-rti-discovery.ndjson
      - umf-rti/umf-rti-summary.json
      - umf-rti/README.txt
    Returns the list of relative file paths written.
    """
    ndjson_path = "umf-rti/umf-rti-discovery.ndjson"
    summary_path = "umf-rti/umf-rti-summary.json"
    readme_path = "umf-rti/README.txt"

    zf.writestr(ndjson_path, result.ndjson_text)

    summary_payload = {
        "service": UMF_RTI_SERVICE_ID,
        "label": UMF_RTI_LABEL,
        "domain_id": result.domain_id,
        "duration_seconds": result.duration_seconds,
        "router_peer": result.router_peer,
        "image": result.image,
        "namespace": result.namespace,
        "job_name": result.job_name,
        "pod_name": result.pod_name,
        "started_at_utc": result.started_at_utc,
        "finished_at_utc": result.finished_at_utc,
        "exit_code": result.exit_code,
        "log_bytes": result.log_bytes,
        "truncated": result.truncated,
        "counts": {
            "participants": result.participants_count,
            "topics": result.topics_count,
            "writers": result.writers_count,
            "readers": result.readers_count,
        },
        "collector_version": result.collector_version,
        "warnings": result.warnings,
        "error": result.error,
    }
    zf.writestr(summary_path, json.dumps(summary_payload, indent=2))

    readme_text = (
        "UMF RTI Diagnostic Capture\n"
        "==========================\n\n"
        f"Domain ID:        {result.domain_id}\n"
        f"Duration (s):     {result.duration_seconds}\n"
        f"Router Peer:      {result.router_peer}\n"
        f"Started (UTC):    {result.started_at_utc}\n"
        f"Finished (UTC):   {result.finished_at_utc}\n"
        f"Participants:     {result.participants_count}\n"
        f"Topics:           {result.topics_count}\n"
        f"Writers:          {result.writers_count}\n"
        f"Readers:          {result.readers_count}\n\n"
        "Files in this folder:\n"
        "- umf-rti-discovery.ndjson: Newline-delimited JSON records of discovered UMF RTI\n"
        "  participants, topics, writers, and readers, including GUIDs, types, liveness, and QoS.\n"
        "- umf-rti-summary.json: Capture metadata, entity counts, and any warnings or errors.\n\n"
        "Privacy / PHI Notice:\n"
        "This capture contains UMF RTI discovery and QoS metadata only. No topic sample payloads\n"
        "or patient identifiers are subscribed to or recorded.\n"
    )
    zf.writestr(readme_path, readme_text)

    return [ndjson_path, summary_path, readme_path]
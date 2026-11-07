import base64
import io
import os
import tarfile
import tempfile
import time
import uuid
import zipfile

from app.log_collection.schemas import LogCollectionManifest
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream

from kubernetes import client

from .config import UmfRtiConfig
from .schemas import UmfRtiCaptureResult, UmfRtiParams


class UmfRtiPrerequisiteError(Exception):
    """Raised when required Secrets or cluster resources for UMF RTI are missing."""


class UmfRtiCaptureError(Exception):
    """Raised when UMF RTI capture Job fails or times out."""


# --- QoS / recording config builders -----------------------------------------
# The capture layers a small override profile on top of the image's built-in WAN
# profile. Both XML docs are reproduced verbatim from the validated spike
# (see PLAN.md Appendix B); only values that live in config.py are substituted,
# so peers/limits/partition are never re-hardcoded here.

# The image's built-in WAN QoS profile we extend.
_BASE_QOS_PROFILE = "AxoneNetQoSLibrary::umfwan_server_viewpod_qos"
_QOS_LIBRARY = "Cap"
_QOS_PROFILE = "universal"
# base_name the recording config references to pull in our overrides.
CAPTURE_QOS_PROFILE = f"{_QOS_LIBRARY}::{_QOS_PROFILE}"
# TODO: rtirecordingservice mangles the <file> name (capture.db -> "capture."). the capture command mv's it to this clean name afterwards.
RECORDING_DB_BASENAME = "capture.db"


def build_override_xml(config: UmfRtiConfig) -> str:
    """Build the universal QoS override profile (`Cap::universal`).

    Pure function. Enables both transports via the base profile, lists every
    router peer, and applies the two fixes the recorder needs (raised
    type_object limit + unbounded reader resource limits).
    """
    peers = "\n".join(
        f"            <element>{peer}</element>" for peer in config.initial_peers()
    )
    return f"""<?xml version="1.0"?>
<dds xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <qos_library name="{_QOS_LIBRARY}">
    <qos_profile name="{_QOS_PROFILE}" base_name="{_BASE_QOS_PROFILE}">
      <participant_qos>
        <discovery>
          <initial_peers>
{peers}
          </initial_peers>
          <accept_unknown_peers>true</accept_unknown_peers>
        </discovery>
        <resource_limits>
          <!-- REQUIRED: S35c_sapphire TypeObjects exceed the 300000 default; recorder records nothing for umfnum/umfwav without this. -1/UNLIMITED is rejected. -->
          <type_object_max_serialized_length>{config.type_object_max_serialized_length}</type_object_max_serialized_length>
        </resource_limits>
      </participant_qos>
      <datareader_qos>
        <history><kind>KEEP_LAST_HISTORY_QOS</kind><depth>8</depth></history>
        <resource_limits>
          <max_samples>LENGTH_UNLIMITED</max_samples>
          <max_instances>LENGTH_UNLIMITED</max_instances>
          <max_samples_per_instance>LENGTH_UNLIMITED</max_samples_per_instance>
        </resource_limits>
      </datareader_qos>
    </qos_profile>
  </qos_library>
</dds>
"""


def build_recording_cfg_xml(domain_id: int, config: UmfRtiConfig) -> str:
    """Build the `rtirecordingservice` config for one domain.

    Pure function. `domain_id` is the only per-capture variable; everything else
    comes from config. Stores readable JSON-in-SQLite and uses a wildcard
    subscriber partition so the named-partition viewpod writers match.
    """
    db_path = f"{config.output_dir}/{RECORDING_DB_BASENAME}"
    return f"""<?xml version="1.0"?>
<dds xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <recording_service name="cap">
    <storage>
      <sqlite>
        <storage_format>JSON_SQLITE</storage_format>
        <file>{db_path}</file>
      </sqlite>
    </storage>
    <domain_participant name="P">
      <domain_id>{domain_id}</domain_id>
      <participant_qos base_name="{CAPTURE_QOS_PROFILE}"/>
    </domain_participant>
    <session name="S">
      <!-- REQUIRED: viewpod umfnum/umfwav writers are in a named partition; wildcard matches them. Without this they silently never match. -->
      <subscriber_qos><partition><name><element>{config.partition}</element></name></partition></subscriber_qos>
      <topic_group name="G" participant_ref="P">
        <allow_topic_name_filter>*</allow_topic_name_filter>
        <datareader_qos>
          <reliability><kind>RELIABLE_RELIABILITY_QOS</kind></reliability>
          <history><kind>KEEP_LAST_HISTORY_QOS</kind><depth>{config.reader_history_depth}</depth></history>
          <resource_limits>
            <max_samples>LENGTH_UNLIMITED</max_samples>
            <max_instances>LENGTH_UNLIMITED</max_instances>
            <max_samples_per_instance>LENGTH_UNLIMITED</max_samples_per_instance>
          </resource_limits>
        </datareader_qos>
      </topic_group>
    </session>
  </recording_service>
</dds>
"""


# --- capture command + Job manifest ------------------------------------------
# Env values the MDH-tools image expects that don't live in config (they're
# fixed by the image, not deployment-tunable).
_WITHWAN_QOS_PATH = "/opt/axone-tools/qos/MDH-tools-RTIAdminConsole-WithWAN.xml"
_DDS_SECURE = "secure"
_DDS_INTERFACES = "eth0"
_RTI_LICENSE_FILE = "/opt/rti_license.dat"
# The WithWAN QoS references these three role-named WAN port env vars and fails
# to parse (silent 0 endpoints) if any is undefined, so all are exported. Each
# maps to its domain's configured port; only the viewpod one is actually bound
# for a single-domain capture, but all must exist.
_WAN_ROLE_DOMAIN = {"LOGGER": 7, "SOURCEPOD": 12, "VIEWPOD": 13}
# Backstop that reaps the Job if the backend never deletes it; this just prevents orphans.
# TODO: explicitly delete the Jobs
_JOB_TTL_SECONDS = 600


def build_capture_command(params: UmfRtiParams, config: UmfRtiConfig) -> str:
    """Build the shell script the capture pod runs (pure function).

    Writes the two QoS/recording XML files, exports the image's env contract
    (incl. the pod's own IP as the WAN public address), records for the
    requested duration, restores the mangled user-data filename, drops a
    `.done` sentinel, then idles so the backend can pull the files out.
    """
    override_xml = build_override_xml(config)
    rec_xml = build_recording_cfg_xml(params.umf_domain_id, config)
    db_path = f"{config.output_dir}/{RECORDING_DB_BASENAME}"
    mangled_path = f"{config.output_dir}/capture."

    wan_port_exports = "\n".join(
        f"export DDS_RTWAN_SERVER_PORT_{role}={config.wan_ports[domain]}"
        for role, domain in _WAN_ROLE_DOMAIN.items()
        if domain in config.wan_ports
    )

    return f"""set -e
mkdir -p {config.output_dir}

cat > /tmp/override.xml <<'OVERRIDE_EOF'
{override_xml}OVERRIDE_EOF

cat > /tmp/rec.xml <<'REC_EOF'
{rec_xml}REC_EOF

export SDDS_HOME={config.sdds_home}
export DDS_SECURE={_DDS_SECURE}
export DDS_INTERFACES={_DDS_INTERFACES}
export DDS_INTERFACES_MONITORING={_DDS_INTERFACES}
export RTI_LICENSE_FILE={_RTI_LICENSE_FILE}
export DDS_RTWAN_SERVER_PUBLIC_ADDRESS="$(hostname -i)"
{wan_port_exports}
export NDDS_QOS_PROFILES="{_WITHWAN_QOS_PATH};/tmp/override.xml"

timeout {params.umf_duration_seconds} rtirecordingservice -cfgFile /tmp/rec.xml -cfgName cap || true

# rtirecordingservice mangles the user-data filename ("{RECORDING_DB_BASENAME}" -> "capture."); restore it.
mv {mangled_path} {db_path} 2>/dev/null || true

touch {config.output_dir}/.done
sleep {config.collect_grace_seconds}
"""


def build_job_manifest(params: UmfRtiParams, config: UmfRtiConfig) -> client.V1Job:
    """Build the capture Job (pure function).

    One-shot Job: a single container running the capture script on an emptyDir
    at `output_dir`. The image is present on the node (pull policy Never).
    """
    job_name = f"{config.job_prefix}-{uuid.uuid4().hex[:8]}"
    script = build_capture_command(params, config)
    labels = {"app": config.job_prefix}

    container = client.V1Container(
        name="capture",
        # TODO(multi-node): "Never" assumes the image is already on the node, which
        # holds for the single-node lab but will ErrImageNeverPull on a multi-node
        # cluster if the Job lands on a node without it. Make pull policy + pull
        # secret (and maybe nodeSelector) config-driven. I'm waiting to see how
        # Ethan handles this for NetShoot so we can have the same approach.
        image=config.image,
        image_pull_policy="Never",
        command=["/bin/sh", "-c", script],
        resources=client.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "256Mi"},
            limits={"cpu": "500m", "memory": "1Gi"},
        ),
        volume_mounts=[
            client.V1VolumeMount(name="out", mount_path=config.output_dir),
        ],
    )
    pod_spec = client.V1PodSpec(
        restart_policy="Never",
        containers=[container],
        volumes=[
            client.V1Volume(name="out", empty_dir=client.V1EmptyDirVolumeSource()),
        ],
    )
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels),
        spec=pod_spec,
    )
    job_spec = client.V1JobSpec(
        template=template,
        backoff_limit=0,
        ttl_seconds_after_finished=_JOB_TTL_SECONDS,
    )
    return client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name=job_name, namespace=config.namespace, labels=labels
        ),
        spec=job_spec,
    )


def check_prerequisites(core: client.CoreV1Api, config: UmfRtiConfig) -> None:
    """No prerequisites to verify for the current approach.

    TODO: delete this,
    """
    return None


# Echoed by the in-pod probe when the capture script has finished recording.
_DONE_MARKER = "__UMF_DONE__"
# Container waiting reasons we treat as fatal (fail fast with a clear message
# instead of waiting out the startup timeout). ErrImageNeverPull is the
# multi-node pull-policy case (see the TODO in build_job_manifest).
_POD_FATAL_WAITING = {"ErrImageNeverPull", "ImagePullBackOff", "CrashLoopBackOff"}


def _create_job(
    batch: client.BatchV1Api, job: client.V1Job, config: UmfRtiConfig
) -> str:
    """Create the capture Job and return the server-assigned name."""
    try:
        created = batch.create_namespaced_job(namespace=config.namespace, body=job)
    except ApiException as e:
        raise UmfRtiCaptureError(
            f"Could not create capture Job in {config.namespace}: {e.reason or e}"
        ) from e
    name = created.metadata.name if created.metadata else None
    if not name:
        raise UmfRtiCaptureError("Created capture Job has no name.")
    return name


def _wait_for_pod_running(
    core: client.CoreV1Api, job_name: str, config: UmfRtiConfig
) -> str:
    """Resolve the Job's pod and wait until it is Running (or already done).

    Raises UmfRtiCaptureError on a failed/unschedulable pod or startup timeout.
    """
    selector = f"job-name={job_name}"
    deadline = time.monotonic() + config.startup_timeout_seconds
    last_pod: str | None = None
    while time.monotonic() < deadline:
        pods = core.list_namespaced_pod(
            namespace=config.namespace, label_selector=selector
        ).items
        if pods:
            pod = pods[0]
            last_pod = pod.metadata.name if pod.metadata else last_pod
            status = pod.status
            phase = status.phase if status else None
            if phase in ("Running", "Succeeded") and last_pod:
                return last_pod
            if phase == "Failed":
                raise UmfRtiCaptureError(
                    f"Capture pod {last_pod} failed before recording started."
                )
            for cs in (status.container_statuses or []) if status else []:
                waiting = cs.state.waiting if cs.state else None
                if waiting and waiting.reason in _POD_FATAL_WAITING:
                    detail = f" - {waiting.message}" if waiting.message else ""
                    raise UmfRtiCaptureError(
                        f"Capture pod {last_pod} cannot start: {waiting.reason}{detail}"
                    )
        time.sleep(config.poll_interval_seconds)
    where = f"last pod {last_pod}" if last_pod else "no pod was scheduled"
    raise UmfRtiCaptureError(
        f"Capture pod did not reach Running within "
        f"{config.startup_timeout_seconds}s ({where})."
    )


def _wait_for_done(
    core: client.CoreV1Api,
    pod_name: str,
    params: UmfRtiParams,
    config: UmfRtiConfig,
) -> None:
    """Poll the pod for the `.done` sentinel the capture script drops.

    The sentinel appears once recording stops and the DB is flushed, so this is
    the signal that the files are safe to collect. Raises on pod death/timeout.
    """
    probe = f"test -f {config.output_dir}/.done && echo {_DONE_MARKER}"
    deadline = (
        time.monotonic() + params.umf_duration_seconds + config.collect_grace_seconds
    )
    while time.monotonic() < deadline:
        try:
            pod = core.read_namespaced_pod(name=pod_name, namespace=config.namespace)
            phase = pod.status.phase if pod.status else None
        except ApiException:
            phase = None
        if phase == "Failed":
            raise UmfRtiCaptureError(
                f"Capture pod {pod_name} exited (Failed) before signaling done."
            )
        try:
            out = stream(
                core.connect_get_namespaced_pod_exec,
                pod_name,
                config.namespace,
                command=["sh", "-c", probe],
                container="capture",
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _preload_content=True,
                _request_timeout=15,
            )
        except ApiException:
            out = ""
        if _DONE_MARKER in out:
            return
        # Script touches .done before its final sleep, so a finished container
        # means recording completed (exec can't reach a stopped container).
        if phase == "Succeeded":
            return
        time.sleep(config.poll_interval_seconds)
    raise UmfRtiCaptureError(
        f"Recording did not finish within "
        f"{params.umf_duration_seconds + config.collect_grace_seconds}s "
        f"(pod {pod_name})."
    )


def _collect_recording(
    core: client.CoreV1Api, pod_name: str, config: UmfRtiConfig
) -> str:
    """Copy the recording dir out of the pod into a local temp dir.

    Streams `tar | base64` over exec (base64 keeps the bytes intact across the
    exec websocket, which otherwise mangles binary), decodes, and extracts.
    Returns the temp dir path; the caller is responsible for deleting it.
    """
    command = [
        "sh",
        "-c",
        f"tar czf - -C {config.output_dir} . 2>/dev/null | base64",
        # the '-' means stream the binary to stdout instead of a file
    ]
    try:
        out = stream(
            core.connect_get_namespaced_pod_exec,
            pod_name,
            config.namespace,
            command=command,
            container="capture",
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=True,
            _request_timeout=120,
        )
    except ApiException as e:
        raise UmfRtiCaptureError(
            f"Could not copy recording from pod {pod_name}: {e.reason or e}"
        ) from e

    try:
        archive = base64.b64decode(out)
    except (ValueError, TypeError) as e:
        raise UmfRtiCaptureError(f"Recording archive was not valid base64: {e}") from e

    recording_dir = tempfile.mkdtemp(prefix="umf-rti-")
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            tar.extractall(recording_dir, filter="data")
    except (tarfile.TarError, EOFError) as e:
        raise UmfRtiCaptureError(f"Could not unpack recording archive: {e}") from e
    return recording_dir


def capture_umf_rti(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    params: UmfRtiParams,
    config: UmfRtiConfig,
) -> UmfRtiCaptureResult:
    """Run one capture: create the Job, wait for recording, pull the files out.

    The returned result carries `recording_dir` (a local temp dir); the caller
    must delete it once the files have been zipped.
    """
    job = build_job_manifest(params, config)
    job_name = _create_job(batch, job, config)
    pod_name = _wait_for_pod_running(core, job_name, config)
    _wait_for_done(core, pod_name, params, config)
    recording_dir = _collect_recording(core, pod_name, config)

    names = sorted(os.listdir(recording_dir))
    db_files = [n for n in names if n.endswith(".db")]
    total_bytes = sum(
        os.path.getsize(os.path.join(recording_dir, n)) for n in db_files
    )
    user_data_file = RECORDING_DB_BASENAME if RECORDING_DB_BASENAME in names else None

    # TODO: parse the user-data DB for per-topic sample counts.
    # TODO: delete the Job (propagation=Foreground) in a finally.
    return UmfRtiCaptureResult(
        domain_id=params.umf_domain_id,
        duration_seconds=params.umf_duration_seconds,
        recording_dir=recording_dir,
        recording_files=db_files,
        user_data_file=user_data_file,
        total_bytes=total_bytes,
    )


def write_artifacts(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    result: UmfRtiCaptureResult,
    params: UmfRtiParams,
    config: UmfRtiConfig,
) -> None:
    pass  # TODO


def write_failure_artifacts(
    zf: zipfile.ZipFile,
    manifest: LogCollectionManifest,
    message: str,
    params: UmfRtiParams,
    config: UmfRtiConfig,
) -> None:
    pass  # TODO

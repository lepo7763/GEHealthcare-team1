import zipfile

from app.log_collection.schemas import LogCollectionManifest

from kubernetes import client
from kubernetes.client.exceptions import ApiException

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


def check_prerequisites(core: client.CoreV1Api, config: UmfRtiConfig) -> None:
    try:
        core.read_namespaced_secret(name=config.sdds_secret_name, namespace=config.namespace)
    except ApiException as e:
        raise UmfRtiPrerequisiteError


def capture_umf_rti(
    core: client.CoreV1Api,
    batch: client.BatchV1Api,
    params: UmfRtiParams,
    config: UmfRtiConfig,
) -> UmfRtiCaptureResult:
    raise NotImplementedError  # TODO


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

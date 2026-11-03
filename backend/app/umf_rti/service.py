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

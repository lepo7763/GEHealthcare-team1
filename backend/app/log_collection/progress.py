from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import List, Optional

# Service identifiers. Only container logs are implemented today; the tracker is
# shaped as a per-service list so more services (netshoot, UMF RTI, ...) can be
# added later without changing the progress contract.
CONTAINER_LOGS_SERVICE_ID = "container-logs"

# Statuses that mean a collection is actively running.
RUNNING_STATUSES = frozenset({"listing", "collecting", "packaging"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ServiceProgress:
    id: str
    label: str
    status: str = "pending"  # pending | collecting | done | error
    pods_total: int = 0
    pods_done: int = 0
    containers_total: int = 0
    containers_done: int = 0
    current: Optional[str] = None  # "namespace/pod"
    errors: int = 0


@dataclass
class CollectionProgress:
    status: str = "idle"  # idle | listing | collecting | packaging | done | error
    services: List[ServiceProgress] = field(default_factory=list)
    message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


def _find_service(state: CollectionProgress, service_id: str) -> Optional[ServiceProgress]:
    for service in state.services:
        if service.id == service_id:
            return service
    return None


class ProgressTracker:
    """Thread-safe, in-memory progress for the (single) running collection.

    FastAPI runs the sync collection endpoint in a worker thread while the
    progress endpoint is polled from another, so every access is locked. This is
    intentionally a process-global singleton: the tool targets one workstation.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._state = CollectionProgress()

    def reset(self) -> None:
        with self._lock:
            self._state = CollectionProgress()

    def begin(self, services: List[ServiceProgress]) -> None:
        with self._lock:
            self._state = CollectionProgress(
                status="listing",
                services=list(services),
                started_at=_utcnow(),
            )

    def set_status(self, status: str, message: Optional[str] = None) -> None:
        with self._lock:
            self._state.status = status
            if message is not None:
                self._state.message = message

    def set_service_totals(
        self, service_id: str, pods_total: int, containers_total: int
    ) -> None:
        with self._lock:
            self._state.status = "collecting"
            service = _find_service(self._state, service_id)
            if service:
                service.status = "collecting"
                service.pods_total = pods_total
                service.containers_total = containers_total

    def record_container(
        self, service_id: str, current: Optional[str], had_error: bool = False
    ) -> None:
        with self._lock:
            service = _find_service(self._state, service_id)
            if service:
                service.containers_done += 1
                service.current = current
                if had_error:
                    service.errors += 1

    def record_pod_done(self, service_id: str) -> None:
        with self._lock:
            service = _find_service(self._state, service_id)
            if service:
                service.pods_done += 1

    def finish(self) -> None:
        with self._lock:
            self._state.status = "done"
            self._state.finished_at = _utcnow()
            for service in self._state.services:
                if service.status != "error":
                    service.status = "done"
                    service.current = None

    def fail(self, message: str) -> None:
        with self._lock:
            self._state.status = "error"
            self._state.message = message
            self._state.finished_at = _utcnow()

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self._state)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._state.status in RUNNING_STATUSES


# Process-global tracker, shared by the service (writer) and router (reader).
tracker = ProgressTracker()

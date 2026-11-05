from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import List, Optional

# Service identifiers shared by the collector, orchestrator and UI.
CONTAINER_LOGS_SERVICE_ID = "container-logs"
UMF_RTI_SERVICE_ID = "umf-rti"

CONTAINER_LOGS_LABEL = "Container Log Collection"
UMF_RTI_LABEL = "UMF RTI"

# Statuses that mean a collection is actively running.
RUNNING_STATUSES = frozenset({"listing", "collecting", "packaging"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ServiceProgress:
    """Progress for one independently counted service.

    ``total``/``completed`` are always in the service's own ``unit``.  We
    deliberately do not aggregate container counts and elapsed seconds into a
    single percentage: the UI renders one bar per service.
    """

    id: str
    label: str
    status: str = "pending"  # pending | collecting | done | error
    completed: int = 0
    total: int = 0
    unit: str = "items"
    current: Optional[str] = None
    errors: int = 0
    error: Optional[str] = None


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

    def try_begin(self, services: List[ServiceProgress]) -> bool:
        """Atomically claim the single collection slot.

        Returns False when another collection is already running.  The router
        still does an early check for a friendly 409, but this closes the race
        between two requests arriving at the same time.
        """
        with self._lock:
            if self._state.status in RUNNING_STATUSES:
                return False
            self._state = CollectionProgress(
                status="listing",
                services=list(services),
                started_at=_utcnow(),
            )
            return True

    def set_status(self, status: str, message: Optional[str] = None) -> None:
        with self._lock:
            self._state.status = status
            if message is not None:
                self._state.message = message

    def set_service_total(
        self, service_id: str, total: int, unit: Optional[str] = None
    ) -> None:
        with self._lock:
            self._state.status = "collecting"
            service = _find_service(self._state, service_id)
            if service:
                service.status = "collecting"
                service.total = max(0, total)
                if unit is not None:
                    service.unit = unit

    def increment_service(
        self,
        service_id: str,
        amount: int = 1,
        current: Optional[str] = None,
        had_error: bool = False,
    ) -> None:
        with self._lock:
            service = _find_service(self._state, service_id)
            if service:
                service.status = "collecting"
                service.completed += max(0, amount)
                if current is not None:
                    service.current = current
                if had_error:
                    service.errors += 1

    def set_service_completed(
        self, service_id: str, completed: int, current: Optional[str] = None
    ) -> None:
        with self._lock:
            self._state.status = "collecting"
            service = _find_service(self._state, service_id)
            if service:
                service.status = "collecting"
                service.completed = max(0, completed)
                if current is not None:
                    service.current = current

    def set_service_current(self, service_id: str, current: Optional[str]) -> None:
        with self._lock:
            service = _find_service(self._state, service_id)
            if service:
                service.current = current

    def record_error(
        self, service_id: str, message: str, increment: bool = True
    ) -> None:
        with self._lock:
            service = _find_service(self._state, service_id)
            if service:
                if increment:
                    service.errors += 1
                service.error = message

    def fail_service(self, service_id: str, message: str) -> None:
        with self._lock:
            service = _find_service(self._state, service_id)
            if service:
                service.status = "error"
                service.error = message
                service.errors += 1

    def finish(self) -> None:
        with self._lock:
            self._state.status = "done"
            self._state.finished_at = _utcnow()
            error_services = 0
            for service in self._state.services:
                if service.status == "error":
                    error_services += 1
                else:
                    service.status = "done"
                    service.current = None
            if error_services:
                self._state.message = f"Completed with {error_services} error(s)."
            else:
                self._state.message = "Completed."

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


# Process-global tracker, shared by the orchestrator (writer) and router (reader).
tracker = ProgressTracker()

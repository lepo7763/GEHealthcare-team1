from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import List, Optional

# Service identifiers shared by the collector, orchestrator and UI.
CONTAINER_LOGS_SERVICE_ID = "container-logs"
UMF_RTI_SERVICE_ID = "umf-rti"
AXONE_LOGS_SERVICE_ID = "axone-logs"
CORE_DUMPS_SERVICE_ID = "core-dumps"
FIREWALL_SERVICE_ID = "firewall"

CONTAINER_LOGS_LABEL = "Container Log Collection"
UMF_RTI_LABEL = "UMF RTI"
AXONE_LOGS_LABEL = "Axone Logs"
CORE_DUMPS_LABEL = "Core Dumps"
FIREWALL_LABEL = "Firewall Settings"

# Statuses that mean a collection is actively running.
RUNNING_STATUSES = frozenset({"listing", "collecting", "packaging"})


class CollectionCancelled(Exception):
    """The user asked to stop the running collection.

    Raised from collector checkpoints (``tracker.raise_if_cancelled()``) and
    caught by the orchestrator, which packages whatever finished. It unwinds
    through each collector's ``finally``/``with`` blocks, so the Kubernetes Jobs
    they created are deleted on the way out.
    """


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
    status: str = "pending"  # pending | collecting | done | error | cancelled | skipped
    completed: int = 0
    total: int = 0
    unit: str = "items"
    current: Optional[str] = None
    errors: int = 0
    error: Optional[str] = None


@dataclass
class CollectionProgress:
    status: str = "idle"  # idle | listing | collecting | packaging | done | error | cancelled
    services: List[ServiceProgress] = field(default_factory=list)
    message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    # Set by request_cancel(); the run keeps its status until a checkpoint sees it.
    cancel_requested: bool = False


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

    def complete_service(self, service_id: str) -> None:
        """Mark one service finished (unless it already failed).

        Called as each service returns, so a later cancel can tell finished
        services apart from the one that was interrupted.
        """
        with self._lock:
            service = _find_service(self._state, service_id)
            if service and service.status != "error":
                service.status = "done"
                service.current = None

    def request_cancel(self) -> bool:
        """Ask the running collection to stop. False if nothing is running."""
        with self._lock:
            if self._state.status not in RUNNING_STATUSES:
                return False
            if not self._state.cancel_requested:
                self._state.cancel_requested = True
                self._state.message = (
                    "Cancelling: stopping the current step and removing deployed tools."
                )
            return True

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._state.cancel_requested

    def raise_if_cancelled(self) -> None:
        """Collector checkpoint: raise CollectionCancelled if a cancel is pending."""
        if self.cancel_requested:
            raise CollectionCancelled()

    def finish_cancelled(self) -> None:
        """End the run as cancelled; finished services keep their results."""
        with self._lock:
            self._state.status = "cancelled"
            self._state.finished_at = _utcnow()
            for service in self._state.services:
                if service.status == "pending":
                    service.status = "skipped"
                elif service.status == "collecting":
                    service.status = "cancelled"
                service.current = None
            kept = sum(1 for s in self._state.services if s.status == "done")
            self._state.message = (
                f"Cancelled. Results from {kept} finished service(s) were packaged."
                if kept
                else "Cancelled before any service finished."
            )

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
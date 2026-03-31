"""
Execution-host lease keepalive primitives.

This module owns host-side liveness reporting only. Lease state semantics,
validation, expiry, and runtime transitions remain in the control plane.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import logging
import threading

from ..core.config import settings


@dataclass(frozen=True)
class AttemptLeaseKeepaliveTarget:
    runtime_session_id: int
    attempt_id: int
    lease_token: str


class AttemptLeaseKeepaliveController:
    """Host-owned keepalive loop for the currently active runtime attempt."""

    def __init__(
        self,
        *,
        session_factory,
        load_session,
        heartbeat_attempt,
        interval_seconds: float,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._load_session = load_session
        self._heartbeat_attempt = heartbeat_attempt
        self._interval_seconds = max(0.05, float(interval_seconds))
        self._logger = logger or logging.getLogger("execution_host_lease")
        self._lock = threading.RLock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._target: AttemptLeaseKeepaliveTarget | None = None
        self._thread = threading.Thread(
            target=self._run,
            name="attempt-lease-keepalive",
            daemon=True,
        )
        self._thread.start()

    def activate(self, *, runtime_session_id: int, attempt_id: int, lease_token: str) -> None:
        target = AttemptLeaseKeepaliveTarget(
            runtime_session_id=int(runtime_session_id),
            attempt_id=int(attempt_id),
            lease_token=str(lease_token or "").strip(),
        )
        with self._lock:
            self._target = target
        self._wake_event.set()

    def deactivate(self) -> None:
        with self._lock:
            self._target = None
        self._wake_event.set()

    def close(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        self._thread.join(timeout=max(1.0, self._interval_seconds * 2))

    def _snapshot_target(self) -> AttemptLeaseKeepaliveTarget | None:
        with self._lock:
            return self._target

    def _clear_target_if_matches(self, target: AttemptLeaseKeepaliveTarget) -> None:
        with self._lock:
            if self._target == target:
                self._target = None
        self._wake_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            target = self._snapshot_target()
            if target is None:
                self._wake_event.wait(timeout=0.5)
                self._wake_event.clear()
                continue

            signaled = self._wake_event.wait(timeout=self._interval_seconds)
            self._wake_event.clear()
            if self._stop_event.is_set():
                break
            if signaled:
                continue

            db = self._session_factory()
            try:
                runtime_session = self._load_session(db, target.runtime_session_id)
                if runtime_session is None:
                    self._logger.warning(
                        "Attempt lease keepalive stopped: runtime session %s disappeared",
                        target.runtime_session_id,
                    )
                    self._clear_target_if_matches(target)
                    continue
                self._heartbeat_attempt(
                    db,
                    runtime_session,
                    attempt_id=target.attempt_id,
                    lease_token=target.lease_token,
                )
            except ValueError as exc:
                self._logger.warning(
                    "Attempt lease keepalive stopped for session=%s attempt=%s: %s",
                    target.runtime_session_id,
                    target.attempt_id,
                    exc,
                )
                self._clear_target_if_matches(target)
            except Exception as exc:
                self._logger.warning(
                    "Attempt lease keepalive failed for session=%s attempt=%s: %s",
                    target.runtime_session_id,
                    target.attempt_id,
                    exc,
                )
            finally:
                try:
                    db.close()
                except Exception:
                    pass


@dataclass(frozen=True)
class ExecutionHostLeaseContext:
    attempt_lease_keepalive: AttemptLeaseKeepaliveController | None


_current_execution_host_lease_context: ContextVar[ExecutionHostLeaseContext | None] = ContextVar(
    "execution_host_lease_context",
    default=None,
)


def execution_host_lease_heartbeat_interval_seconds() -> int:
    lease_seconds = max(1, int(getattr(settings, "RUNTIME_ATTEMPT_LEASE_SECONDS", 300)))
    configured_seconds = max(
        1,
        int(getattr(settings, "RUNTIME_ATTEMPT_HEARTBEAT_INTERVAL_SECONDS", 60)),
    )
    return max(1, min(configured_seconds, max(1, lease_seconds // 2)))


def get_current_execution_host_lease_context() -> ExecutionHostLeaseContext | None:
    return _current_execution_host_lease_context.get()


def set_current_execution_host_lease_context(
    context: ExecutionHostLeaseContext | None,
):
    return _current_execution_host_lease_context.set(context)


def reset_current_execution_host_lease_context(token) -> None:
    _current_execution_host_lease_context.reset(token)


def activate_current_attempt_keepalive(
    *,
    runtime_session_id: int,
    attempt_id: int,
    lease_token: str,
) -> bool:
    context = get_current_execution_host_lease_context()
    if context is None or context.attempt_lease_keepalive is None:
        return False
    context.attempt_lease_keepalive.activate(
        runtime_session_id=runtime_session_id,
        attempt_id=attempt_id,
        lease_token=lease_token,
    )
    return True


def deactivate_current_attempt_keepalive() -> bool:
    context = get_current_execution_host_lease_context()
    if context is None or context.attempt_lease_keepalive is None:
        return False
    context.attempt_lease_keepalive.deactivate()
    return True

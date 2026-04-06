"""
Execution-host lease keepalive primitives.

This module owns host-side liveness reporting only. Lease state semantics,
validation, expiry, and runtime transitions remain in the control plane.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import threading
from typing import Any, Callable, Dict, Optional

from ..core.config import settings


class ExecutionHostKeepaliveLostError(RuntimeError):
    """Raised when host-side lease keepalive is no longer healthy."""

    def __init__(self, message: str, *, diagnostic: Optional[Dict[str, Any]] = None):
        self.diagnostic = dict(diagnostic or {})
        super().__init__(message)


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
        publish_diagnostic: Optional[Callable[..., None]] = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._load_session = load_session
        self._heartbeat_attempt = heartbeat_attempt
        self._publish_diagnostic = publish_diagnostic
        self._interval_seconds = max(0.05, float(interval_seconds))
        self._logger = logger or logging.getLogger("execution_host_lease")
        self._lock = threading.RLock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._target: AttemptLeaseKeepaliveTarget | None = None
        self._last_published_signature: tuple[Any, ...] | None = None
        self._unhealthy_diagnostic: Dict[str, Any] | None = None
        self._successful_heartbeat_seen = False
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
            self._last_published_signature = None
            self._unhealthy_diagnostic = None
            self._successful_heartbeat_seen = False
        self._publish_target_receipt(
            target,
            code="execution_host_keepalive_activation_requested",
            message="Execution host keepalive activation requested",
        )
        self._wake_event.set()

    def deactivate(self, *, reason: str = "deactivated") -> None:
        target = None
        with self._lock:
            target = self._target
            self._target = None
            self._last_published_signature = None
            self._unhealthy_diagnostic = None
            self._successful_heartbeat_seen = False
        if target is not None:
            self._publish_target_receipt(
                target,
                code="execution_host_keepalive_deactivated",
                message="Execution host keepalive deactivated",
                reason_code=str(reason or "deactivated").strip().lower() or "deactivated",
            )
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
                self._last_published_signature = None
                self._successful_heartbeat_seen = False
        self._wake_event.set()

    def _build_keepalive_receipt(
        self,
        target: AttemptLeaseKeepaliveTarget,
        *,
        code: str,
        message: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        receipt = {
            "code": str(code or "").strip(),
            "runtime_session_id": target.runtime_session_id,
            "attempt_id": target.attempt_id,
            "message": str(message or "").strip(),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        for key, value in (extra or {}).items():
            if value is not None:
                receipt[key] = value
        return receipt

    def _publish_target_receipt(
        self,
        target: AttemptLeaseKeepaliveTarget,
        *,
        code: str,
        message: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        receipt = self._build_keepalive_receipt(
            target,
            code=code,
            message=message,
            **extra,
        )
        if self._publish_diagnostic is not None:
            try:
                self._publish_diagnostic(
                    runtime_session_id=target.runtime_session_id,
                    attempt_id=target.attempt_id,
                    diagnostic=receipt,
                )
            except Exception as exc:
                self._logger.warning(
                    "Attempt lease keepalive receipt publish failed for session=%s attempt=%s code=%s: %s",
                    target.runtime_session_id,
                    target.attempt_id,
                    receipt.get("code"),
                    exc,
                )
        return receipt

    def _build_keepalive_diagnostic(
        self,
        target: AttemptLeaseKeepaliveTarget,
        *,
        state: str,
        reason_code: str,
        message: str,
    ) -> Dict[str, Any]:
        return {
            "code": "execution_host_keepalive",
            "runtime_session_id": target.runtime_session_id,
            "attempt_id": target.attempt_id,
            "state": str(state or "").strip().lower() or "failed",
            "reason_code": str(reason_code or "").strip().lower() or "unknown",
            "message": str(message or "").strip(),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

    def _publish_target_diagnostic(
        self,
        target: AttemptLeaseKeepaliveTarget,
        *,
        state: str,
        reason_code: str,
        message: str,
    ) -> Dict[str, Any]:
        diagnostic = self._build_keepalive_diagnostic(
            target,
            state=state,
            reason_code=reason_code,
            message=message,
        )
        signature = (
            target.runtime_session_id,
            target.attempt_id,
            diagnostic["state"],
            diagnostic["reason_code"],
            diagnostic["message"],
        )
        with self._lock:
            if self._last_published_signature == signature:
                return diagnostic
            self._last_published_signature = signature
        if self._publish_diagnostic is not None:
            try:
                self._publish_diagnostic(
                    runtime_session_id=target.runtime_session_id,
                    attempt_id=target.attempt_id,
                    diagnostic=diagnostic,
                )
            except Exception as exc:
                self._logger.warning(
                    "Attempt lease keepalive diagnostic publish failed for session=%s attempt=%s: %s",
                    target.runtime_session_id,
                    target.attempt_id,
                    exc,
                )
        return diagnostic

    def _remember_unhealthy_diagnostic(
        self,
        target: AttemptLeaseKeepaliveTarget,
        diagnostic: Dict[str, Any],
    ) -> None:
        with self._lock:
            if self._target == target:
                self._unhealthy_diagnostic = dict(diagnostic or {})

    def _mark_successful_heartbeat(self, target: AttemptLeaseKeepaliveTarget) -> bool:
        with self._lock:
            if self._target != target:
                return False
            first_success = not self._successful_heartbeat_seen
            self._successful_heartbeat_seen = True
            return first_success

    @staticmethod
    def _iso_datetime(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        return None

    def assert_healthy(self) -> None:
        with self._lock:
            diagnostic = dict(self._unhealthy_diagnostic or {})
        if not diagnostic:
            return
        state = str(diagnostic.get("state") or "failed").strip().lower() or "failed"
        reason_code = str(diagnostic.get("reason_code") or "unknown").strip().lower() or "unknown"
        message = str(diagnostic.get("message") or "execution host keepalive lost").strip()
        raise ExecutionHostKeepaliveLostError(
            f"Execution host keepalive lost (state={state}, reason={reason_code}): {message}",
            diagnostic=diagnostic,
        )

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

            self._publish_target_receipt(
                target,
                code="execution_host_keepalive_heartbeat_begin",
                message="Execution host keepalive heartbeat started",
            )
            db = self._session_factory()
            try:
                runtime_session = self._load_session(db, target.runtime_session_id)
                if runtime_session is None:
                    message = f"runtime session {target.runtime_session_id} disappeared"
                    self._logger.warning(
                        "Attempt lease keepalive stopped: %s",
                        message,
                    )
                    diagnostic = self._publish_target_diagnostic(
                        target,
                        state="stopped",
                        reason_code="runtime_session_missing",
                        message=message,
                    )
                    self._remember_unhealthy_diagnostic(target, diagnostic)
                    self._clear_target_if_matches(target)
                    continue
                attempt = self._heartbeat_attempt(
                    db,
                    runtime_session,
                    attempt_id=target.attempt_id,
                    lease_token=target.lease_token,
                )
                last_heartbeat_at = self._iso_datetime(
                    getattr(attempt, "last_heartbeat_at", None) if attempt is not None else None
                )
                lease_expires_at = self._iso_datetime(
                    getattr(attempt, "lease_expires_at", None) if attempt is not None else None
                )
                if self._mark_successful_heartbeat(target):
                    self._publish_target_receipt(
                        target,
                        code="execution_host_keepalive_first_heartbeat_ack",
                        message="Execution host keepalive first heartbeat acknowledged",
                        last_heartbeat_at=last_heartbeat_at,
                        lease_expires_at=lease_expires_at,
                    )
                self._publish_target_receipt(
                    target,
                    code="execution_host_keepalive_heartbeat_end",
                    message="Execution host keepalive heartbeat completed",
                    last_heartbeat_at=last_heartbeat_at,
                    lease_expires_at=lease_expires_at,
                )
            except ValueError as exc:
                message = str(exc)
                self._logger.warning(
                    "Attempt lease keepalive stopped for session=%s attempt=%s: %s",
                    target.runtime_session_id,
                    target.attempt_id,
                    message,
                )
                diagnostic = self._publish_target_diagnostic(
                    target,
                    state="stopped",
                    reason_code="heartbeat_validation_failed",
                    message=message,
                )
                self._remember_unhealthy_diagnostic(target, diagnostic)
                self._clear_target_if_matches(target)
            except Exception as exc:
                message = str(exc)
                self._logger.warning(
                    "Attempt lease keepalive failed for session=%s attempt=%s: %s",
                    target.runtime_session_id,
                    target.attempt_id,
                    message,
                )
                diagnostic = self._publish_target_diagnostic(
                    target,
                    state="failed",
                    reason_code="heartbeat_error",
                    message=message,
                )
                self._remember_unhealthy_diagnostic(target, diagnostic)
                self._clear_target_if_matches(target)
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


def deactivate_current_attempt_keepalive(*, reason: str = "deactivated") -> bool:
    context = get_current_execution_host_lease_context()
    if context is None or context.attempt_lease_keepalive is None:
        return False
    context.attempt_lease_keepalive.deactivate(reason=reason)
    return True


def assert_current_execution_host_keepalive_healthy() -> None:
    context = get_current_execution_host_lease_context()
    if context is None or context.attempt_lease_keepalive is None:
        return
    context.attempt_lease_keepalive.assert_healthy()

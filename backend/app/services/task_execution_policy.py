"""
Unified task execution eligibility policy for queued worker dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from ..models import Task, TaskStatus, WorkflowSession, WorkflowSessionStatus
from ..core.config import settings


TERMINAL_TASK_STATUSES = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}

TERMINAL_RUNTIME_STATUSES = {
    WorkflowSessionStatus.COMPLETED.value,
    WorkflowSessionStatus.FAILED.value,
    WorkflowSessionStatus.CANCELLED.value,
}

QUEUE_DISPATCHABLE_TASK_STATUSES = {
    TaskStatus.PENDING.value,
    TaskStatus.QUEUED.value,
    TaskStatus.IN_PROGRESS.value,
}

QUEUE_DISPATCHABLE_RUNTIME_STATUSES = {
    WorkflowSessionStatus.QUEUED.value,
    WorkflowSessionStatus.RUNNING.value,
    WorkflowSessionStatus.RESUMING.value,
}

LIVE_CELERY_RESULT_STATES = {"STARTED", "RETRY"}
TERMINAL_CELERY_RESULT_STATES = {"SUCCESS", "FAILURE", "REVOKED"}


@dataclass(frozen=True)
class TaskTransportProbeResult:
    state: str
    reason_code: str


def _status_value(status: Any) -> str:
    raw = getattr(status, "value", status)
    return str(raw or "").strip()


def _iter_transport_task_ids(entries: Any) -> Iterable[str]:
    for entry in entries or []:
        if isinstance(entry, dict):
            direct_id = str(entry.get("id") or "").strip()
            if direct_id:
                yield direct_id
                continue
            request = entry.get("request")
            if isinstance(request, dict):
                request_id = str(request.get("id") or "").strip()
                if request_id:
                    yield request_id


def probe_task_transport_state(celery_task_id: Optional[str]) -> TaskTransportProbeResult:
    normalized_task_id = str(celery_task_id or "").strip()
    if not normalized_task_id:
        if bool(getattr(settings, "TASKS_API_ENABLE_IN_PROCESS_RUNNER", False)):
            return TaskTransportProbeResult(
                state="unknown",
                reason_code="in_process_runner_enabled",
            )
        return TaskTransportProbeResult(
            state="not_live",
            reason_code="missing_queue_handle",
        )

    try:
        from .celery_app import celery_app
        from celery.result import AsyncResult

        inspector = celery_app.control.inspect()
        transport_buckets = {
            "active": inspector.active() or {},
            "scheduled": inspector.scheduled() or {},
            "reserved": inspector.reserved() or {},
        }
        for bucket_name, bucket_entries in transport_buckets.items():
            for worker_entries in bucket_entries.values():
                if normalized_task_id in set(_iter_transport_task_ids(worker_entries)):
                    return TaskTransportProbeResult(
                        state="live",
                        reason_code=f"transport_{bucket_name}",
                    )

        result_state = str(AsyncResult(normalized_task_id, app=celery_app).state or "").strip().upper()
        if result_state in LIVE_CELERY_RESULT_STATES:
            return TaskTransportProbeResult(
                state="live",
                reason_code=f"celery_result_{result_state.lower()}",
            )
        if result_state in TERMINAL_CELERY_RESULT_STATES:
            return TaskTransportProbeResult(
                state="not_live",
                reason_code=f"celery_result_{result_state.lower()}",
            )
        if result_state:
            return TaskTransportProbeResult(
                state="unknown",
                reason_code=f"celery_result_{result_state.lower()}",
            )
    except Exception:
        return TaskTransportProbeResult(
            state="unknown",
            reason_code="transport_probe_unavailable",
        )

    return TaskTransportProbeResult(
        state="unknown",
        reason_code="transport_probe_unknown",
    )


def is_terminal_task_status(status: Any) -> bool:
    return _status_value(status) in TERMINAL_TASK_STATUSES


def is_terminal_runtime_status(status: Any) -> bool:
    return _status_value(status) in TERMINAL_RUNTIME_STATUSES


def get_queue_execution_block_reason(
    task: Optional[Task],
    runtime_session: Optional[WorkflowSession] = None,
) -> Optional[str]:
    """
    Return a stable reason string when a queued worker must not execute a task.

    For quick-mode tasks, runtime session status is the primary source of truth.
    Task status is only used as a fallback when no runtime session exists.
    """
    if task is None:
        return "task_missing"

    if runtime_session is not None:
        runtime_status = _status_value(runtime_session.status)
        if runtime_status in TERMINAL_RUNTIME_STATUSES:
            return f"runtime_terminal:{runtime_status}"
        if runtime_status not in QUEUE_DISPATCHABLE_RUNTIME_STATUSES:
            return f"runtime_not_dispatchable:{runtime_status or 'unknown'}"
        return None

    task_status = _status_value(task.status)
    if task_status in TERMINAL_TASK_STATUSES:
        return f"task_terminal:{task_status}"
    if task_status not in QUEUE_DISPATCHABLE_TASK_STATUSES:
        return f"task_not_dispatchable:{task_status or 'unknown'}"
    return None

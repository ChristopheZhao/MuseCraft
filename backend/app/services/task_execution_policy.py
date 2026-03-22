"""
Unified task execution eligibility policy for queued worker dispatch.
"""
from __future__ import annotations

from typing import Any, Optional

from ..models import Task, TaskStatus, WorkflowSession, WorkflowSessionStatus


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


def _status_value(status: Any) -> str:
    raw = getattr(status, "value", status)
    return str(raw or "").strip()


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

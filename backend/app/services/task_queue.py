"""Celery transport adapter for video-generation execution."""

from __future__ import annotations

import logging
from typing import Any

from ..domain import QueuedExecutionCommand, QueuedExecutionKind
from .queued_execution_use_case import QueuedExecutionUseCase


def _video_command(task_id: str) -> QueuedExecutionCommand:
    return QueuedExecutionCommand(
        task_id=task_id,
        execution_kind=QueuedExecutionKind.VIDEO_GENERATION,
    )


class TaskQueueService:
    """Transport-facing video queue adapter."""

    def __init__(self, *, execution_use_case: QueuedExecutionUseCase | None = None) -> None:
        self._execution_use_case = execution_use_case or QueuedExecutionUseCase()
        self.logger = logging.getLogger("task_queue")

    def queue_task(self, task_id: str) -> str | None:
        from .celery_app import process_video_task

        return self._execution_use_case.enqueue(
            _video_command(task_id),
            dispatch=lambda stable_task_id: process_video_task.delay(stable_task_id).id,
        )


def sync_process_video_task(task_id: str) -> dict[str, Any]:
    """Worker and debug-runner entrypoint using the same application contract."""

    return QueuedExecutionUseCase().execute(_video_command(task_id))


def get_task_queue_stats() -> dict[str, Any]:
    """Return transport diagnostics; these values never advance runtime state."""

    try:
        from .celery_app import celery_app

        inspector = celery_app.control.inspect()
        active_tasks = inspector.active()
        scheduled_tasks = inspector.scheduled()
        reserved_tasks = inspector.reserved()
        total_active = sum(len(tasks) for tasks in (active_tasks or {}).values())
        total_scheduled = sum(len(tasks) for tasks in (scheduled_tasks or {}).values())
        total_reserved = sum(len(tasks) for tasks in (reserved_tasks or {}).values())
        return {
            "active_tasks": total_active,
            "scheduled_tasks": total_scheduled,
            "reserved_tasks": total_reserved,
            "total_pending": total_active + total_scheduled + total_reserved,
            "worker_status": "online" if active_tasks is not None else "offline",
        }
    except Exception as exc:
        logging.getLogger("task_queue").error("Failed to get queue stats: %s", exc)
        return {
            "active_tasks": 0,
            "scheduled_tasks": 0,
            "reserved_tasks": 0,
            "total_pending": 0,
            "worker_status": "unknown",
            "error": str(exc),
        }


def cancel_celery_task(celery_task_id: str) -> bool:
    """Cancel a transport task without changing MAS runtime truth."""

    try:
        from .celery_app import celery_app

        celery_app.control.revoke(celery_task_id, terminate=True)
        return True
    except Exception as exc:
        logging.getLogger("task_queue").error(
            "Failed to cancel Celery task %s: %s",
            celery_task_id,
            exc,
        )
        return False

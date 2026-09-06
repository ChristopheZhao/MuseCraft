"""Celery transport adapter for project workflow execution."""

from __future__ import annotations

from typing import Any

from ..domain import QueuedExecutionCommand, QueuedExecutionKind
from .queued_execution_use_case import QueuedExecutionUseCase


def _project_command(task_id: str) -> QueuedExecutionCommand:
    return QueuedExecutionCommand(
        task_id=task_id,
        execution_kind=QueuedExecutionKind.PROJECT_WORKFLOW,
    )


class ProjectJobQueueService:
    """Transport-facing project workflow queue adapter."""

    def __init__(self, *, execution_use_case: QueuedExecutionUseCase | None = None) -> None:
        self._execution_use_case = execution_use_case or QueuedExecutionUseCase()

    def queue_task(self, task_id: str) -> str | None:
        from .celery_app import process_project_job

        return self._execution_use_case.enqueue(
            _project_command(task_id),
            dispatch=lambda stable_task_id: process_project_job.delay(stable_task_id).id,
        )


def sync_process_project_job(task_id: str) -> dict[str, Any]:
    """Worker entrypoint using the scheduler-neutral application contract."""

    return QueuedExecutionUseCase().execute(_project_command(task_id))

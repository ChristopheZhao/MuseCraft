"""SQLAlchemy unit of work for atomic project commands."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from ..domain import ProjectTaskCompletion, ProjectTaskCreate, ProjectTaskRecord, TaskStatus
from ..models import Task
from .project_definition_store_sqlalchemy import SqlAlchemyProjectDefinitionUnitOfWork


class SqlAlchemyProjectCommandUnitOfWork(SqlAlchemyProjectDefinitionUnitOfWork):
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        super().__init__(session_factory)

    def add_task(self, command: ProjectTaskCreate) -> ProjectTaskRecord:
        if self._session is None:
            raise RuntimeError("Project command unit of work is not active")
        task = Task(
            title=command.title,
            description=command.description,
            task_type=command.task_type,
            status=TaskStatus.PENDING.value,
            project_id=command.project_id,
            episode_id=command.episode_id,
            input_parameters=command.input_data.to_dict(),
        )
        self._session.add(task)
        self._session.flush()
        return ProjectTaskRecord(
            task_id=str(task.task_id),
            status=TaskStatus(str(task.status)),
        )

    def complete_task(self, command: ProjectTaskCompletion) -> ProjectTaskRecord:
        if self._session is None:
            raise RuntimeError("Project command unit of work is not active")
        task = self._session.query(Task).filter(Task.task_id == str(command.task_id)).one_or_none()
        if task is None:
            raise RuntimeError(f"Project task {command.task_id} was not found")
        task.status = TaskStatus.COMPLETED.value
        task.error_message = None
        task.output_metadata = command.output_metadata.to_dict()
        task.update_progress(command.progress_step, command.progress_percentage)
        self._session.flush()
        return ProjectTaskRecord(
            task_id=str(task.task_id),
            status=TaskStatus(str(task.status)),
        )

"""Composition root for project-definition application services."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..services.project_service import ProjectDefinitionApplicationService
from ..services.project_workflow_service import ProjectWorkflowApplicationService
from .project_command_uow_sqlalchemy import SqlAlchemyProjectCommandUnitOfWork
from .project_definition_store_sqlalchemy import SqlAlchemyProjectDefinitionUnitOfWork
from .project_execution_read_model_sqlalchemy import SqlAlchemyProjectExecutionReadModelQuery


def build_project_definition_service(
    session_factory: Callable[[], Session] = SessionLocal,
) -> ProjectDefinitionApplicationService:
    return ProjectDefinitionApplicationService(
        lambda: SqlAlchemyProjectDefinitionUnitOfWork(session_factory)
    )


def build_project_workflow_service(
    session_factory: Callable[[], Session] = SessionLocal,
) -> ProjectWorkflowApplicationService:
    return ProjectWorkflowApplicationService(
        lambda: SqlAlchemyProjectCommandUnitOfWork(session_factory)
    )


def build_project_execution_read_model_query(
    session_factory: Callable[[], Session] = SessionLocal,
) -> SqlAlchemyProjectExecutionReadModelQuery:
    return SqlAlchemyProjectExecutionReadModelQuery(session_factory)

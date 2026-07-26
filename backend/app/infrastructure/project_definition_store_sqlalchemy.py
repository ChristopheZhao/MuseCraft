"""SQLAlchemy adapter for versioned project-definition persistence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain import (
    JsonObjectPayload,
    ProjectDefinitionError,
    ProjectDefinitionReason,
    ProjectDefinitionRecord,
    ProjectDefinitionWrite,
)
from ..models.project_workspace import ProjectWorkspace


class SqlAlchemyProjectDefinitionStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _record(row: ProjectWorkspace) -> ProjectDefinitionRecord:
        return ProjectDefinitionRecord(
            project_id=str(row.project_id),
            mode=str(row.mode),
            version=int(row.version),
            payload=JsonObjectPayload.from_mapping(
                dict(row.payload or {}),
                field_path=f"project_definition[{row.project_id}]",
            ),
        )

    def load(self, project_id: str) -> Optional[ProjectDefinitionRecord]:
        normalized_id = str(project_id or "").strip()
        row = self._session.execute(
            select(ProjectWorkspace).where(ProjectWorkspace.project_id == normalized_id)
        ).scalar_one_or_none()
        return self._record(row) if row is not None else None

    def save(self, command: ProjectDefinitionWrite) -> ProjectDefinitionRecord:
        project_id = str(command.project_id or "").strip()
        operation = "save_project_definition"
        payload = command.payload.to_dict()

        if command.expected_version is None:
            if self.load(project_id) is not None:
                raise ProjectDefinitionError(
                    reason_code=ProjectDefinitionReason.ALREADY_EXISTS,
                    operation=operation,
                    project_id=project_id,
                    message=f"Project definition {project_id} already exists",
                )
            row = ProjectWorkspace(
                project_id=project_id,
                mode=command.mode,
                version=1,
                payload=payload,
            )
            self._session.add(row)
            try:
                self._session.flush()
            except IntegrityError as exc:
                raise ProjectDefinitionError(
                    reason_code=ProjectDefinitionReason.ALREADY_EXISTS,
                    operation=operation,
                    project_id=project_id,
                    message=f"Project definition {project_id} already exists",
                ) from exc
            return self._record(row)

        expected_version = int(command.expected_version)
        result = self._session.execute(
            update(ProjectWorkspace)
            .where(
                ProjectWorkspace.project_id == project_id,
                ProjectWorkspace.version == expected_version,
            )
            .values(
                mode=command.mode,
                payload=payload,
                version=expected_version + 1,
            )
        )
        if result.rowcount != 1:
            reason = (
                ProjectDefinitionReason.RECORD_NOT_FOUND
                if self.load(project_id) is None
                else ProjectDefinitionReason.VERSION_CONFLICT
            )
            raise ProjectDefinitionError(
                reason_code=reason,
                operation=operation,
                project_id=project_id,
                message=(
                    f"Project definition {project_id} version mismatch; "
                    f"expected {expected_version}"
                ),
            )
        self._session.flush()
        record = self.load(project_id)
        if record is None:
            raise ProjectDefinitionError(
                reason_code=ProjectDefinitionReason.RECORD_NOT_FOUND,
                operation=operation,
                project_id=project_id,
                message=f"Project definition {project_id} disappeared after update",
            )
        return record

    def remove(self, project_id: str, *, expected_version: int) -> None:
        normalized_id = str(project_id or "").strip()
        normalized_expected_version = int(expected_version)
        result = self._session.execute(
            delete(ProjectWorkspace).where(
                ProjectWorkspace.project_id == normalized_id,
                ProjectWorkspace.version == normalized_expected_version,
            )
        )
        if result.rowcount != 1:
            observed_version = self._session.execute(
                select(ProjectWorkspace.version).where(ProjectWorkspace.project_id == normalized_id)
            ).scalar_one_or_none()
            reason = (
                ProjectDefinitionReason.RECORD_NOT_FOUND
                if observed_version is None
                else ProjectDefinitionReason.VERSION_CONFLICT
            )
            raise ProjectDefinitionError(
                reason_code=reason,
                operation="remove_project_definition",
                project_id=normalized_id,
                message=(
                    f"Project definition {normalized_id} was not found"
                    if reason is ProjectDefinitionReason.RECORD_NOT_FOUND
                    else (
                        f"Project definition {normalized_id} version mismatch; "
                        f"expected {normalized_expected_version}"
                    )
                ),
            )
        self._session.flush()

    def list_records(self) -> Sequence[ProjectDefinitionRecord]:
        rows = self._session.execute(
            select(ProjectWorkspace).order_by(ProjectWorkspace.created_at.asc())
        ).scalars()
        return tuple(self._record(row) for row in rows)


class SqlAlchemyProjectDefinitionUnitOfWork:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Optional[Session] = None
        self.store: SqlAlchemyProjectDefinitionStore

    def __enter__(self) -> "SqlAlchemyProjectDefinitionUnitOfWork":
        self._session = self._session_factory()
        self.store = SqlAlchemyProjectDefinitionStore(self._session)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("Project-definition unit of work is not active")
        self._session.commit()

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()

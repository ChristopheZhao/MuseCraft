"""Shared authority backing for project-level workflow facts and projections."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator, List, Optional, TYPE_CHECKING

from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models.project_workspace import ProjectWorkspace

if TYPE_CHECKING:
    from ..core.story_plan import ProjectState


class ProjectAuthorityStore:
    """Persist and load project wrapper facts from a shared durable backing."""

    def __init__(self, session_factory: Optional[Callable[[], Session]] = None) -> None:
        self._default_session_factory = session_factory or SessionLocal
        self._session_factory_override: Optional[Callable[[], Session]] = None

    def bind_session_factory(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory_override = session_factory

    def restore_default_session_factory(self) -> None:
        self._session_factory_override = None

    def _session_factory(self) -> Callable[[], Session]:
        return self._session_factory_override or self._default_session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        session = self._session_factory()()
        try:
            yield session
        finally:
            session.close()

    def save(self, project_state: "ProjectState") -> "ProjectState":
        payload = project_state.to_dict()

        with self._session_scope() as session:
            record = (
                session.query(ProjectWorkspace)
                .filter(ProjectWorkspace.project_id == project_state.project_id)
                .one_or_none()
            )
            if record is None:
                record = ProjectWorkspace(
                    project_id=project_state.project_id,
                    mode=project_state.mode,
                    payload=payload,
                )
                session.add(record)
            else:
                record.mode = project_state.mode
                record.payload = payload
            session.commit()

        return self.get(project_state.project_id) or project_state

    def get(self, project_id: str) -> Optional["ProjectState"]:
        from ..core.story_plan import ProjectState

        with self._session_scope() as session:
            record = (
                session.query(ProjectWorkspace)
                .filter(ProjectWorkspace.project_id == project_id)
                .one_or_none()
            )
            if record is None:
                return None
            payload = dict(record.payload or {})

        return ProjectState.from_dict(payload)

    def remove(self, project_id: str) -> None:
        with self._session_scope() as session:
            record = (
                session.query(ProjectWorkspace)
                .filter(ProjectWorkspace.project_id == project_id)
                .one_or_none()
            )
            if record is None:
                return
            session.delete(record)
            session.commit()

    def list_states(self) -> List["ProjectState"]:
        from ..core.story_plan import ProjectState

        with self._session_scope() as session:
            rows = (
                session.query(ProjectWorkspace)
                .order_by(ProjectWorkspace.created_at.asc())
                .all()
            )
            payloads = [dict(row.payload or {}) for row in rows]

        return [ProjectState.from_dict(payload) for payload in payloads]


project_authority_store = ProjectAuthorityStore()

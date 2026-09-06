"""Database-independent project definition and execution projection contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol, Sequence

from .agent_execution import JsonObjectPayload
from .enums import TaskStatus, TaskType


class ProjectDefinitionReason(str, Enum):
    RECORD_NOT_FOUND = "project_not_found"
    VERSION_CONFLICT = "project_version_conflict"
    ALREADY_EXISTS = "project_already_exists"
    INVALID_PAYLOAD = "invalid_project_definition"


class ProjectDefinitionError(RuntimeError):
    def __init__(
        self,
        *,
        reason_code: ProjectDefinitionReason,
        operation: str,
        project_id: str,
        message: str,
    ) -> None:
        self.reason_code = reason_code
        self.operation = str(operation or "project_definition")
        self.project_id = str(project_id or "").strip()
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ProjectDefinitionRecord:
    project_id: str
    mode: str
    version: int
    payload: JsonObjectPayload


@dataclass(frozen=True, slots=True)
class ProjectDefinitionWrite:
    project_id: str
    mode: str
    payload: JsonObjectPayload
    expected_version: Optional[int]


class ProjectDefinitionStore(Protocol):
    def load(self, project_id: str) -> Optional[ProjectDefinitionRecord]:
        ...

    def save(self, command: ProjectDefinitionWrite) -> ProjectDefinitionRecord:
        ...

    def remove(self, project_id: str, *, expected_version: int) -> None:
        ...

    def list_records(self) -> Sequence[ProjectDefinitionRecord]:
        ...


class ProjectDefinitionUnitOfWork(Protocol):
    store: ProjectDefinitionStore

    def __enter__(self) -> "ProjectDefinitionUnitOfWork":
        ...

    def __exit__(self, exc_type, exc, traceback) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


@dataclass(frozen=True, slots=True)
class ProjectTaskCreate:
    title: str
    description: str
    task_type: TaskType
    project_id: str
    input_data: JsonObjectPayload
    episode_id: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ProjectTaskRecord:
    task_id: str
    status: TaskStatus


@dataclass(frozen=True, slots=True)
class ProjectTaskCompletion:
    task_id: str
    output_metadata: JsonObjectPayload
    progress_step: str
    progress_percentage: int = 100


class ProjectCommandUnitOfWork(ProjectDefinitionUnitOfWork, Protocol):
    def add_task(self, command: ProjectTaskCreate) -> ProjectTaskRecord:
        ...

    def complete_task(self, command: ProjectTaskCompletion) -> ProjectTaskRecord:
        ...


@dataclass(frozen=True, slots=True)
class ProjectOperationReadModel:
    status: str = "idle"
    task_id: Optional[str] = None
    error: Optional[str] = None


@dataclass(frozen=True, slots=True)
class EpisodeExecutionReadModel:
    episode_id: str
    status: str = "idle"
    approved_script: str = ""
    workflow_task_id: Optional[str] = None
    aggregated_cost: float = 0.0
    aggregated_tokens: int = 0
    output_assets: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    error: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ProjectExecutionReadModel:
    project_id: str
    mode: str
    definition_version: int
    definition: JsonObjectPayload
    planning: ProjectOperationReadModel
    character_references: ProjectOperationReadModel
    episodes: tuple[EpisodeExecutionReadModel, ...]
    total_cost: float = 0.0
    total_tokens: int = 0
    completed_episodes: int = 0


class ProjectExecutionReadModelQuery(Protocol):
    def get(self, project_id: str) -> ProjectExecutionReadModel:
        ...

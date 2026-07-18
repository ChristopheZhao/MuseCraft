"""Stable contracts for queued application execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QueuedExecutionKind(str, Enum):
    VIDEO_GENERATION = "video_generation"
    PROJECT_WORKFLOW = "project_workflow"


class QueuedExecutionContractReason(str, Enum):
    TASK_ID_REQUIRED = "task_id_required"
    INVALID_TASK_ID = "invalid_task_id"
    INVALID_EXECUTION_KIND = "invalid_execution_kind"


class QueuedExecutionContractError(ValueError):
    """Raised when a transport command does not satisfy the public contract."""

    def __init__(self, *, reason_code: QueuedExecutionContractReason, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class QueuedExecutionCommand:
    """Scheduler-neutral command carrying only stable application identity."""

    task_id: str
    execution_kind: QueuedExecutionKind

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str):
            raise QueuedExecutionContractError(
                reason_code=QueuedExecutionContractReason.INVALID_TASK_ID,
                message="Queued execution task_id must be a string",
            )
        normalized_task_id = self.task_id.strip()
        if not normalized_task_id:
            raise QueuedExecutionContractError(
                reason_code=QueuedExecutionContractReason.TASK_ID_REQUIRED,
                message="Queued execution requires a stable task_id",
            )
        object.__setattr__(self, "task_id", normalized_task_id)

        if not isinstance(self.execution_kind, QueuedExecutionKind):
            raise QueuedExecutionContractError(
                reason_code=QueuedExecutionContractReason.INVALID_EXECUTION_KIND,
                message="Queued execution requires a QueuedExecutionKind",
            )

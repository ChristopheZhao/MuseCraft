"""Application adapter that persists and invokes one episode workflow task."""

from __future__ import annotations

from typing import Protocol

from ..core.database import SessionLocal as SyncSessionLocal
from ..domain import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentTaskReference,
    AgentType,
    EpisodeWorkflowExecutionReceipt,
    JsonObjectPayload,
    TaskStatus,
    TaskType,
)
from ..models import Task


class EpisodeWorkflowOrchestrator(Protocol):
    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        ...


class PersistentEpisodeWorkflowExecutor:
    """Own the ORM child-task lifecycle outside EpisodeOrchestratorAgent."""

    def __init__(
        self,
        *,
        orchestrator: EpisodeWorkflowOrchestrator,
        session_factory=SyncSessionLocal,
    ) -> None:
        self._orchestrator = orchestrator
        self._session_factory = session_factory

    def _create_task(
        self,
        *,
        parent_task: AgentTaskReference,
        title: str,
        description: str,
        input_data: JsonObjectPayload,
    ) -> AgentTaskReference:
        db = self._session_factory()
        try:
            task = Task(
                title=title,
                description=description,
                task_type=TaskType.VIDEO_GENERATION,
                status=TaskStatus.PENDING.value,
                session_id=parent_task.session_id,
                user_id=parent_task.user_id,
                input_parameters=input_data.to_dict(),
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return AgentTaskReference(
                task_id=str(task.task_id),
                task_type=TaskType.VIDEO_GENERATION.value,
                user_id=(str(task.user_id) if task.user_id is not None else None),
                session_id=(str(task.session_id) if task.session_id is not None else None),
            )
        finally:
            db.close()

    def _update_task_status(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        error_message: str | None = None,
    ) -> None:
        db = self._session_factory()
        try:
            task = db.query(Task).filter(Task.task_id == task_id).first()
            if task is None:
                raise RuntimeError(f"Episode workflow task {task_id} disappeared")
            task.status = status.value
            task.error_message = error_message
            db.commit()
        finally:
            db.close()

    async def execute_episode(
        self,
        *,
        parent_task: AgentTaskReference,
        title: str,
        description: str,
        input_data: JsonObjectPayload,
        execution_order: int,
    ) -> EpisodeWorkflowExecutionReceipt:
        child_task = self._create_task(
            parent_task=parent_task,
            title=title,
            description=description,
            input_data=input_data,
        )
        try:
            result = await self._orchestrator.execute(
                AgentExecutionRequest(
                    task=child_task,
                    agent_type=AgentType.ORCHESTRATOR.value,
                    input_data=input_data,
                    workflow_state_id=child_task.task_id,
                    execution_order=execution_order,
                )
            )
            receipt = EpisodeWorkflowExecutionReceipt(
                task_id=child_task.task_id,
                result=result,
            )
        except Exception as exc:
            self._update_task_status(
                task_id=child_task.task_id,
                status=TaskStatus.FAILED,
                error_message=str(exc),
            )
            raise

        self._update_task_status(
            task_id=child_task.task_id,
            status=TaskStatus.COMPLETED,
        )
        return receipt

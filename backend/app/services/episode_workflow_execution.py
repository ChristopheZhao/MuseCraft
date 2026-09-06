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
from ..infrastructure import SqlAlchemyRuntimeAttemptStore
from .runtime_session_bootstrap_control_plane import RuntimeSessionBootstrapControlPlane


class EpisodeWorkflowOrchestrator(Protocol):
    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        ...


class PersistentEpisodeWorkflowExecutor:
    """Create durable child executions for the application episode coordinator."""

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
            payload = input_data.to_dict()
            task = Task(
                title=title,
                description=description,
                task_type=TaskType.VIDEO_GENERATION,
                status=TaskStatus.PENDING.value,
                session_id=parent_task.session_id,
                user_id=parent_task.user_id,
                project_id=str(payload.get("project_id") or "").strip() or None,
                episode_id=str(payload.get("episode_id") or "").strip() or None,
                input_parameters=payload,
            )
            db.add(task)
            db.flush()
            db.refresh(task)
            RuntimeSessionBootstrapControlPlane(
                SqlAlchemyRuntimeAttemptStore(db)
            ).create_quick_session(
                task_id=str(task.task_id),
                expected_task_status=TaskStatus.PENDING,
                expected_latest_session_id=None,
                input_payload=input_data,
                project_id=str(task.project_id) if task.project_id else None,
                episode_id=str(task.episode_id) if task.episode_id else None,
            )
            db.commit()
            db.refresh(task)
            return AgentTaskReference(
                task_id=str(task.task_id),
                task_type=TaskType.VIDEO_GENERATION.value,
                user_id=(str(task.user_id) if task.user_id is not None else None),
                session_id=(str(task.session_id) if task.session_id is not None else None),
            )
        except Exception:
            db.rollback()
            raise
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
        result = await self._orchestrator.execute(
            AgentExecutionRequest(
                task=child_task,
                agent_type=AgentType.ORCHESTRATOR.value,
                input_data=input_data,
                workflow_state_id=child_task.task_id,
                execution_order=execution_order,
            )
        )
        return EpisodeWorkflowExecutionReceipt(
            task_id=child_task.task_id,
            result=result,
        )

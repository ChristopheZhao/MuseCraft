"""SQLAlchemy query adapter for immutable project execution projections."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import (
    EpisodeExecutionReadModel,
    JsonObjectPayload,
    ProjectDefinitionError,
    ProjectDefinitionReason,
    ProjectExecutionReadModel,
    ProjectOperationReadModel,
    WorkflowSessionStatus,
)
from ..models import (
    ProjectWorkspace,
    Task,
    WorkflowNodeAttempt,
    WorkflowPublishedDeliverable,
    WorkflowSession,
)


class SqlAlchemyProjectExecutionReadModelQuery:
    """Build a read-only projection from committed authority tables."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def get(self, project_id: str) -> ProjectExecutionReadModel:
        normalized_id = str(project_id or "").strip()
        session = self._session_factory()
        try:
            workspace = session.execute(
                select(ProjectWorkspace).where(ProjectWorkspace.project_id == normalized_id)
            ).scalar_one_or_none()
            if workspace is None:
                raise ProjectDefinitionError(
                    reason_code=ProjectDefinitionReason.RECORD_NOT_FOUND,
                    operation="get_project_execution_read_model",
                    project_id=normalized_id,
                    message=f"Project definition {normalized_id} was not found",
                )

            definition = dict(workspace.payload or {})
            episodes = list((definition.get("story_plan") or {}).get("episodes") or [])
            tasks = tuple(
                session.execute(
                    select(Task)
                    .where(Task.project_id == normalized_id)
                    .order_by(Task.created_at.desc(), Task.id.desc())
                ).scalars()
            )
            planning_task = next(
                (
                    task
                    for task in tasks
                    if (task.input_parameters or {}).get("handler_key") == "plan_project"
                ),
                None,
            )
            planning = self._task_operation(planning_task)
            character_references = self._character_reference_operation(planning_task)

            runtime_sessions = tuple(
                session.execute(
                    select(WorkflowSession)
                    .where(WorkflowSession.project_id == normalized_id)
                    .order_by(WorkflowSession.created_at.desc(), WorkflowSession.id.desc())
                ).scalars()
            )
            latest_by_episode: dict[str, WorkflowSession] = {}
            for runtime_session in runtime_sessions:
                episode_id = str(runtime_session.episode_id or "").strip()
                if episode_id and episode_id not in latest_by_episode:
                    latest_by_episode[episode_id] = runtime_session

            episode_models = tuple(
                self._episode_projection(
                    session,
                    episode,
                    latest_by_episode.get(str(episode.get("episode_id") or "")),
                    definition_version=int(workspace.version),
                )
                for episode in episodes
            )
            return ProjectExecutionReadModel(
                project_id=normalized_id,
                mode=str(workspace.mode),
                definition_version=int(workspace.version),
                definition=JsonObjectPayload.from_mapping(
                    definition,
                    field_path=f"project_execution_read_model[{normalized_id}].definition",
                ),
                planning=planning,
                character_references=character_references,
                episodes=episode_models,
                total_cost=sum(item.aggregated_cost for item in episode_models),
                total_tokens=sum(item.aggregated_tokens for item in episode_models),
                completed_episodes=sum(item.status == "completed" for item in episode_models),
            )
        finally:
            session.close()

    @staticmethod
    def _task_operation(task: Task | None) -> ProjectOperationReadModel:
        if task is None:
            return ProjectOperationReadModel()
        return ProjectOperationReadModel(
            status=str(task.status or "idle"),
            task_id=str(task.task_id),
            error=str(task.error_message) if task.error_message else None,
        )

    @staticmethod
    def _character_reference_operation(task: Task | None) -> ProjectOperationReadModel:
        if task is None:
            return ProjectOperationReadModel()
        value = (task.output_metadata or {}).get("character_references")
        if not isinstance(value, dict):
            if str(task.status) in {"pending", "queued", "in_progress"}:
                return ProjectOperationReadModel(status="queued", task_id=str(task.task_id))
            return ProjectOperationReadModel()
        return ProjectOperationReadModel(
            status=str(value.get("status") or "idle"),
            task_id=str(task.task_id),
            error=str(value.get("error")) if value.get("error") else None,
        )

    def _episode_projection(
        self,
        db: Session,
        episode: dict[str, Any],
        runtime_session: WorkflowSession | None,
        *,
        definition_version: int,
    ) -> EpisodeExecutionReadModel:
        episode_id = str(episode.get("episode_id") or "")
        approved_script = str(episode.get("approved_script") or "")
        if runtime_session is None:
            return EpisodeExecutionReadModel(
                episode_id=episode_id,
                approved_script=approved_script,
            )

        input_payload = dict(runtime_session.input_payload or {})
        status = self._runtime_status(str(runtime_session.status or ""))
        expected_revision = int(episode.get("editorial_revision", 0))
        observed_revision = input_payload.get("episode_editorial_revision")
        observed_definition_version = input_payload.get("project_definition_version")
        if status != "generating" and (
            observed_revision != expected_revision
            or observed_definition_version != definition_version
        ):
            status = "stale"

        task = db.execute(
            select(Task).where(Task.id == runtime_session.task_db_id)
        ).scalar_one_or_none()
        attempts = tuple(
            db.execute(
                select(WorkflowNodeAttempt).where(
                    WorkflowNodeAttempt.session_id == runtime_session.id
                )
            ).scalars()
        )
        metrics = [dict(attempt.metrics or {}) for attempt in attempts]
        deliverables = tuple(
            db.execute(
                select(WorkflowPublishedDeliverable).where(
                    WorkflowPublishedDeliverable.session_id == runtime_session.id,
                    WorkflowPublishedDeliverable.is_approved.is_(True),
                )
            ).scalars()
        )
        assets = dict(runtime_session.summary_output or {})
        if deliverables:
            assets["published_deliverables"] = [
                {
                    "deliverable_type": item.deliverable_type,
                    "payload_ref": item.payload_ref,
                    "summary": dict(item.summary or {}),
                    "revision_no": int(item.revision_no),
                }
                for item in deliverables
            ]
        return EpisodeExecutionReadModel(
            episode_id=episode_id,
            status=status,
            approved_script=approved_script,
            workflow_task_id=str(task.task_id) if task is not None else None,
            aggregated_cost=sum(self._number(item.get("total_cost")) for item in metrics),
            aggregated_tokens=sum(self._integer(item.get("total_tokens")) for item in metrics),
            output_assets=JsonObjectPayload.from_mapping(
                assets,
                field_path=f"project_execution_read_model.episodes[{episode_id}].output_assets",
            ),
            error=str(runtime_session.error_message) if runtime_session.error_message else None,
        )

    @staticmethod
    def _runtime_status(value: str) -> str:
        if value == WorkflowSessionStatus.COMPLETED.value:
            return "completed"
        if value in {
            WorkflowSessionStatus.FAILED.value,
            WorkflowSessionStatus.CANCELLED.value,
        }:
            return "failed"
        if value == WorkflowSessionStatus.QUEUED.value:
            return "queued"
        return "generating"

    @staticmethod
    def _number(value: object) -> float:
        return (
            float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
        )

    @staticmethod
    def _integer(value: object) -> int:
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0

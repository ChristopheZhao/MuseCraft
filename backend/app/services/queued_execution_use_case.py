"""Application use case shared by queued, in-process, and direct execution."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.constants import GenerationMode
from ..core.database import SessionLocal
from ..core.generation_mode import resolve_generation_mode
from ..core.story_plan import ProjectDefinition
from ..domain import (
    AgentExecutionContractError,
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentTaskReference,
    AgentType,
    QueuedExecutionCommand,
    QueuedExecutionKind,
    RuntimeStoreError,
    RuntimeStoreReason,
    TaskStatus,
)
from ..infrastructure import SqlAlchemyRuntimeAttemptStore
from ..models import Task
from .agent_execution_boundary import (
    build_agent_execution_request,
    require_canonical_execution_status,
)
from .project_job_contract import resolve_project_job_contract
from .queued_task_execution_host import run_agent_execution_in_host
from .runtime_attempt_keepalive_adapter import create_runtime_attempt_keepalive_controller
from .runtime_session_control_plane import RuntimeSessionControlPlane
from .task_execution_policy import get_queue_execution_block_reason
from ..infrastructure.project_definition_composition import (
    build_project_definition_service,
    build_project_workflow_service,
)
from .project_service import ProjectDefinitionApplicationService
from .project_workflow_service import ProjectWorkflowApplicationService


class QueuedExecutionApplicationError(RuntimeError):
    """Explicit application failure with a stable diagnostic reason."""

    def __init__(self, *, reason_code: str, task_id: str, message: str) -> None:
        self.reason_code = str(reason_code or "unknown").strip() or "unknown"
        self.task_id = str(task_id or "").strip()
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class _PreparedExecution:
    request: AgentExecutionRequest
    agent_type: AgentType
    result_metadata: dict[str, str]
    input_data: dict[str, Any]
    use_runtime_keepalive: bool = False


@dataclass(frozen=True, slots=True)
class _SkippedExecution:
    reason_code: str
    result_metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class _PreparedEpisodeExecution:
    parent_task: AgentTaskReference
    result_metadata: dict[str, str]
    input_data: dict[str, Any]


class QueuedExecutionUseCase:
    """Own application/control-plane decisions outside scheduler transports."""

    _QUICK_RUNTIME_EXECUTION_STATUSES = frozenset({"completed", "waiting_gate"})
    _PROJECT_PLANNING_EXECUTION_STATUSES = frozenset({"completed"})
    _EPISODE_COORDINATION_EXECUTION_STATUSES = frozenset({"completed"})

    def __init__(
        self,
        *,
        session_factory=None,
        host_runner=None,
        agent_factory=None,
        keepalive_factory=None,
        character_reference_runner=None,
        episode_coordinator_factory=None,
        project_definitions: ProjectDefinitionApplicationService | None = None,
        project_workflows: ProjectWorkflowApplicationService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session_factory = session_factory or SessionLocal
        self._host_runner = host_runner or run_agent_execution_in_host
        self._agent_factory = agent_factory or self._create_default_agent
        self._keepalive_factory = keepalive_factory or create_runtime_attempt_keepalive_controller
        self._character_reference_runner = character_reference_runner
        self._episode_coordinator_factory = (
            episode_coordinator_factory or self._create_default_episode_coordinator
        )
        self._project_definitions = project_definitions or build_project_definition_service(
            self._session_factory
        )
        self._project_workflows = project_workflows or build_project_workflow_service(
            self._session_factory
        )
        self._logger = logger or logging.getLogger("queued_execution_use_case")

    def enqueue(
        self,
        command: QueuedExecutionCommand,
        *,
        dispatch: Callable[[str], str],
    ) -> str | None:
        """Authorize dispatch, invoke a transport port, and persist its receipt."""

        task_payload: dict[str, Any]
        project_contract: tuple[str, str] | None = None
        db = self._session_factory()
        try:
            task = self._get_task(db, command.task_id)
            if task is None:
                raise self._task_missing(command.task_id)
            task_payload = dict(task.input_parameters or {})
            runtime_session = None
            if command.execution_kind == QueuedExecutionKind.VIDEO_GENERATION:
                mode = resolve_generation_mode(task_payload.get("mode"))
                if mode == GenerationMode.QUICK:
                    runtime_session = SqlAlchemyRuntimeAttemptStore(
                        db
                    ).load_latest_session_for_task(
                        command.task_id,
                    )
                    if runtime_session is None:
                        self._logger.error(
                            "Dispatch denied for quick task %s (runtime_missing)",
                            command.task_id,
                        )
                        return None
            else:
                project_contract = resolve_project_job_contract(task_payload)

            block_reason = get_queue_execution_block_reason(task, runtime_session)
            if block_reason:
                self._logger.info(
                    "Dispatch denied for task %s (%s)",
                    command.task_id,
                    block_reason,
                )
                return None
        finally:
            db.close()

        raw_transport_task_id = dispatch(command.task_id)
        transport_task_id = (
            raw_transport_task_id.strip() if isinstance(raw_transport_task_id, str) else ""
        )
        if not transport_task_id:
            raise QueuedExecutionApplicationError(
                reason_code="transport_receipt_missing",
                task_id=command.task_id,
                message=f"Transport returned no receipt for task {command.task_id}",
            )

        db = self._session_factory()
        try:
            task = self._get_task(db, command.task_id)
            if task is None:
                raise self._task_missing(command.task_id)
            output_metadata = dict(task.output_metadata or {})
            output_metadata["celery_task_id"] = transport_task_id
            if project_contract is not None:
                output_metadata["project_job"] = {
                    "job_kind": project_contract[0],
                    "handler_key": project_contract[1],
                }
            task.output_metadata = output_metadata
            if task.status == TaskStatus.PENDING.value:
                task.status = TaskStatus.QUEUED.value
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        return transport_task_id

    def execute(self, command: QueuedExecutionCommand) -> dict[str, Any]:
        """Execute one stable-ID command and preserve control-plane failure meaning."""

        try:
            prepared = self._prepare_execution(command)
            if isinstance(prepared, _SkippedExecution):
                return {
                    "status": "skipped",
                    "skip_reason": prepared.reason_code,
                    **prepared.result_metadata,
                }

            if isinstance(prepared, _PreparedEpisodeExecution):
                result_payload = asyncio.run(
                    self._episode_coordinator_factory().execute(
                        parent_task=prepared.parent_task,
                        input_data=prepared.input_data,
                    )
                )
                result_status = self._require_execution_status(
                    result_payload,
                    task_id=command.task_id,
                    field_path="episode_coordination_result.status",
                    allowed_statuses=self._EPISODE_COORDINATION_EXECUTION_STATUSES,
                )
                self._complete_episode_coordination(command, result_payload)
                return {
                    "status": result_status,
                    "result": result_payload,
                    **prepared.result_metadata,
                }

            executor = self._agent_factory(prepared.agent_type)
            keepalive = (
                self._keepalive_factory(logger=self._logger)
                if prepared.use_runtime_keepalive
                else None
            )
            execution_result = self._host_runner(
                request=prepared.request,
                executor=executor,
                attempt_lease_keepalive=keepalive,
            )
            if not isinstance(execution_result, AgentExecutionResult):
                raise QueuedExecutionApplicationError(
                    reason_code="invalid_host_result",
                    task_id=command.task_id,
                    message="Execution host returned a non-AgentExecutionResult value",
                )

            result_payload = execution_result.output_data.to_dict()
            result_status = self._require_execution_status(
                result_payload,
                task_id=command.task_id,
                field_path="agent_execution_result.output_data.status",
                allowed_statuses=(
                    self._PROJECT_PLANNING_EXECUTION_STATUSES
                    if command.execution_kind == QueuedExecutionKind.PROJECT_WORKFLOW
                    else self._QUICK_RUNTIME_EXECUTION_STATUSES
                ),
            )
            if command.execution_kind == QueuedExecutionKind.PROJECT_WORKFLOW:
                self._complete_project_execution(
                    command,
                    input_data=prepared.input_data,
                    result_payload=result_payload,
                )

            return {
                "status": result_status,
                "result": result_payload,
                **prepared.result_metadata,
            }
        except Exception as execution_error:
            try:
                self._mark_execution_failed(command, execution_error)
            except Exception as transition_error:
                raise QueuedExecutionApplicationError(
                    reason_code="failure_transition_failed",
                    task_id=command.task_id,
                    message=(
                        f"Task {command.task_id} execution failed ({execution_error}); "
                        f"failure transition also failed ({transition_error})"
                    ),
                ) from transition_error
            raise

    @staticmethod
    def _require_execution_status(
        payload: Any,
        *,
        task_id: str,
        field_path: str,
        allowed_statuses: frozenset[str],
    ) -> str:
        try:
            return require_canonical_execution_status(
                payload,
                field_path=field_path,
                allowed_statuses=allowed_statuses,
            )
        except AgentExecutionContractError as exc:
            raise QueuedExecutionApplicationError(
                reason_code="execution_status_invalid",
                task_id=task_id,
                message=f"Execution returned no canonical status: {exc}",
            ) from exc

    def _prepare_execution(
        self,
        command: QueuedExecutionCommand,
    ) -> _PreparedExecution | _PreparedEpisodeExecution | _SkippedExecution:
        db = self._session_factory()
        try:
            task = self._get_task(db, command.task_id)
            if task is None:
                raise self._task_missing(command.task_id)
            input_data = dict(task.input_parameters or {})

            if command.execution_kind == QueuedExecutionKind.VIDEO_GENERATION:
                mode = resolve_generation_mode(input_data.get("mode"))
                route = (
                    "orchestrator_mainline"
                    if mode == GenerationMode.QUICK
                    else "project_orchestrator_mainline"
                )
                runtime_session = None
                if mode == GenerationMode.QUICK:
                    runtime_session = SqlAlchemyRuntimeAttemptStore(
                        db
                    ).load_latest_session_for_task(
                        command.task_id,
                    )
                    if runtime_session is None:
                        return _SkippedExecution(
                            reason_code="runtime_missing",
                            result_metadata={"route": route, "mode": mode.value},
                        )
                block_reason = get_queue_execution_block_reason(task, runtime_session)
                if block_reason:
                    return _SkippedExecution(
                        reason_code=block_reason,
                        result_metadata={"route": route, "mode": mode.value},
                    )
                if runtime_session is not None:
                    runtime_payload = runtime_session.input_payload.to_dict()
                    if runtime_payload:
                        input_data = runtime_payload
                agent_type = AgentType.ORCHESTRATOR
                request = build_agent_execution_request(
                    task=task,
                    agent_type=agent_type,
                    input_data=input_data,
                    execution_order=1,
                )
                if mode == GenerationMode.PROJECT:
                    return _PreparedEpisodeExecution(
                        parent_task=request.task,
                        result_metadata={"route": route, "mode": mode.value},
                        input_data=dict(input_data),
                    )
                return _PreparedExecution(
                    request=request,
                    agent_type=agent_type,
                    result_metadata={"route": route, "mode": mode.value},
                    input_data=dict(input_data),
                    use_runtime_keepalive=mode == GenerationMode.QUICK,
                )

            job_kind, handler_key = resolve_project_job_contract(input_data)
            block_reason = get_queue_execution_block_reason(task)
            if block_reason:
                return _SkippedExecution(
                    reason_code=block_reason,
                    result_metadata={
                        "job_kind": job_kind,
                        "handler_key": handler_key,
                    },
                )

            task.status = TaskStatus.IN_PROGRESS.value
            task.update_progress("Project planning started", 1)
            db.commit()
            request = build_agent_execution_request(
                task=task,
                agent_type=AgentType.SERIES_PLANNER,
                input_data=input_data,
                execution_order=1,
            )
            return _PreparedExecution(
                request=request,
                agent_type=AgentType.SERIES_PLANNER,
                result_metadata={"job_kind": job_kind, "handler_key": handler_key},
                input_data=input_data,
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _complete_project_execution(
        self,
        command: QueuedExecutionCommand,
        *,
        input_data: dict[str, Any],
        result_payload: dict[str, Any],
    ) -> None:
        project_id = str(input_data.get("project_id") or "").strip() or None
        if project_id is None:
            raise QueuedExecutionApplicationError(
                reason_code="project_id_missing",
                task_id=command.task_id,
                message="Project planning command is missing project_id",
            )
        character_reference_result = {
            "status": "idle",
            "error": None,
        }
        if project_id:
            definition_payload = result_payload.get("project_definition")
            if not isinstance(definition_payload, dict):
                raise QueuedExecutionApplicationError(
                    reason_code="project_definition_result_missing",
                    task_id=command.task_id,
                    message="Series planner returned no typed project_definition payload",
                )
            expected_version = input_data.get("project_definition_version")
            if not isinstance(expected_version, int):
                raise QueuedExecutionApplicationError(
                    reason_code="project_definition_version_missing",
                    task_id=command.task_id,
                    message="Project planning command is missing project_definition_version",
                )
            planned_definition = ProjectDefinition.from_dict(definition_payload)
            self._project_workflows.apply_planning_result(
                definition=planned_definition,
                expected_version=expected_version,
                task_id=command.task_id,
                character_references_requested=bool(
                    input_data.get("generate_character_references", True)
                ),
            )
            character_reference_result = self._run_character_reference_generation(
                project_id,
                input_data=input_data,
            )
            self._record_character_reference_result(
                command.task_id,
                character_reference_result,
            )

    def _run_character_reference_generation(
        self,
        project_id: str,
        *,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        async def run() -> bool:
            if self._character_reference_runner is not None:
                return await self._character_reference_runner(
                    project_id,
                    project_definitions=self._project_definitions,
                    enabled=bool(input_data.get("generate_character_references", True)),
                    logger=self._logger,
                )
            from .character_reference_images import ensure_project_character_reference_images

            return await ensure_project_character_reference_images(
                project_id,
                project_definitions=self._project_definitions,
                enabled=bool(input_data.get("generate_character_references", True)),
                logger=self._logger,
            )

        try:
            started = asyncio.run(run())
            if not started:
                self._logger.info(
                    "Project character reference generation skipped for %s",
                    project_id,
                )
                return {"status": "skipped", "error": None}
            return {"status": "completed", "error": None}
        except Exception as exc:  # controlled independent post-processing failure
            self._logger.warning(
                "Project character reference generation failed for %s: %s",
                project_id,
                exc,
            )
            return {"status": "failed", "error": str(exc)}

    def _record_character_reference_result(
        self,
        task_id: str,
        result: dict[str, Any],
    ) -> None:
        db = self._session_factory()
        try:
            task = self._get_task(db, task_id)
            if task is None:
                raise self._task_missing(task_id)
            output_metadata = dict(task.output_metadata or {})
            output_metadata["character_references"] = dict(result)
            task.output_metadata = output_metadata
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _mark_execution_failed(
        self,
        command: QueuedExecutionCommand,
        error: Exception,
    ) -> None:
        db = self._session_factory()
        try:
            task = self._get_task(db, command.task_id)
            if task is None:
                return
            if command.execution_kind == QueuedExecutionKind.VIDEO_GENERATION:
                mode = resolve_generation_mode((task.input_parameters or {}).get("mode"))
                if mode == GenerationMode.QUICK:
                    store = SqlAlchemyRuntimeAttemptStore(db)
                    runtime_session = store.load_latest_session_for_task(command.task_id)
                    if runtime_session is None:
                        raise RuntimeStoreError(
                            reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                            operation="mark_queued_execution_failed",
                            message=(
                                f"Authoritative runtime session for task {command.task_id} "
                                "is missing"
                            ),
                        )
                    RuntimeSessionControlPlane(store).mark_failed(
                        runtime_session.session_id,
                        error_message=str(error),
                    )
                    db.commit()
                    return
                task.status = TaskStatus.FAILED.value
                task.error_message = str(error)
                db.commit()
                return

            task.status = TaskStatus.FAILED.value
            task.error_message = str(error)
            task.update_progress(
                "Project planning failed",
                task.progress_percentage or 1,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _complete_episode_coordination(
        self,
        command: QueuedExecutionCommand,
        result_payload: dict[str, Any],
    ) -> None:
        db = self._session_factory()
        try:
            task = self._get_task(db, command.task_id)
            if task is None:
                raise self._task_missing(command.task_id)
            task.status = TaskStatus.COMPLETED.value
            task.error_message = None
            output_metadata = dict(task.output_metadata or {})
            output_metadata["episode_coordination"] = result_payload
            task.output_metadata = output_metadata
            task.update_progress("Episode coordination completed", 100)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _update_task_progress(self, task_id: str, step: str, percentage: int) -> None:
        db = self._session_factory()
        try:
            task = self._get_task(db, task_id)
            if task is None:
                raise self._task_missing(task_id)
            task.update_progress(step, percentage)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _get_task(db, task_id: str):
        return db.query(Task).filter(Task.task_id == task_id).first()

    @staticmethod
    def _task_missing(task_id: str) -> QueuedExecutionApplicationError:
        return QueuedExecutionApplicationError(
            reason_code="task_missing",
            task_id=task_id,
            message=f"Task {task_id} was not found",
        )

    @staticmethod
    def _create_default_agent(agent_type: AgentType):
        if agent_type == AgentType.ORCHESTRATOR:
            from ..infrastructure.orchestrator_composition import build_orchestrator_agent

            return build_orchestrator_agent()
        if agent_type == AgentType.SERIES_PLANNER:
            from ..agents.series_planner import SeriesPlannerAgent
            from ..agents.utils.llm_policy import LLMPolicyManager

            policy_path = (
                Path(__file__)
                .resolve()
                .parents[1]
                .joinpath(
                    "config",
                    "llm_policies.yaml",
                )
            )
            planner_llms = LLMPolicyManager(str(policy_path)).build_llms_for_agent("series_planner")
            return SeriesPlannerAgent.create_default(llms=planner_llms)
        raise ValueError(f"Unsupported queued Agent type: {agent_type.value}")

    @staticmethod
    def _create_default_episode_coordinator():
        from ..infrastructure.project_definition_composition import (
            build_project_definition_service,
            build_project_execution_read_model_query,
        )
        from .episode_execution_coordinator import EpisodeExecutionCoordinator
        from .episode_workflow_execution import PersistentEpisodeWorkflowExecutor
        from ..infrastructure.orchestrator_composition import build_orchestrator_agent

        orchestrator = build_orchestrator_agent()
        return EpisodeExecutionCoordinator(
            project_definitions=build_project_definition_service(),
            execution_query=build_project_execution_read_model_query(),
            episode_executor=PersistentEpisodeWorkflowExecutor(orchestrator=orchestrator),
        )

from types import SimpleNamespace

import pytest

from app.core.story_plan import ProjectDefinition, StoryPlan
from app.domain import (
    AgentExecutionResult,
    AgentType,
    JsonObjectPayload,
    QueuedExecutionCommand,
    QueuedExecutionKind,
    TaskStatus,
    TaskType,
)
from app.infrastructure.project_definition_store_sqlalchemy import (
    SqlAlchemyProjectDefinitionUnitOfWork,
)
from app.models import Task
from app.services import project_job_queue
from app.services.project_job_contract import (
    PROJECT_JOB_HANDLER_PLAN_PROJECT,
    PROJECT_JOB_KIND_WORKFLOW,
    attach_project_plan_contract,
)
from app.services.project_service import ProjectDefinitionApplicationService
from app.services.queued_execution_use_case import QueuedExecutionUseCase


def _definition_service(session_factory):
    return ProjectDefinitionApplicationService(
        lambda: SqlAlchemyProjectDefinitionUnitOfWork(session_factory)
    )


def _create_task(session_factory, *, input_parameters, project_id, status="pending"):
    db = session_factory()
    try:
        task = Task(
            title="Project Planning",
            description="project planning",
            task_type=TaskType.SCRIPT_WRITING,
            status=status,
            project_id=project_id,
            input_parameters=input_parameters,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return str(task.task_id)
    finally:
        db.close()


def test_project_queue_adapter_dispatches_stable_id_through_use_case(monkeypatch):
    events = {}

    class _UseCase:
        def enqueue(self, command, *, dispatch):
            events["command"] = command
            return dispatch(command.task_id)

    monkeypatch.setattr(
        "app.services.celery_app.process_project_job",
        SimpleNamespace(delay=lambda task_id: SimpleNamespace(id=f"project-{task_id}")),
    )
    receipt = project_job_queue.ProjectJobQueueService(execution_use_case=_UseCase()).queue_task(
        "stable-project-task"
    )

    assert receipt == "project-stable-project-task"
    assert events["command"] == QueuedExecutionCommand(
        "stable-project-task", QueuedExecutionKind.PROJECT_WORKFLOW
    )


def test_project_enqueue_persists_transport_receipt(project_state_store):
    project_id = "project-enqueue"
    task_id = _create_task(
        project_state_store,
        project_id=project_id,
        input_parameters=attach_project_plan_contract(
            {"project_id": project_id, "mode": "project"}
        ),
    )
    use_case = QueuedExecutionUseCase(session_factory=project_state_store)

    receipt = use_case.enqueue(
        QueuedExecutionCommand(task_id, QueuedExecutionKind.PROJECT_WORKFLOW),
        dispatch=lambda stable_id: f"transport-{stable_id}",
    )

    db = project_state_store()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).one()
        assert task.status == TaskStatus.QUEUED.value
        assert task.output_metadata["celery_task_id"] == f"transport-{task_id}"
    finally:
        db.close()
    assert receipt == f"transport-{task_id}"


def test_project_execution_applies_planner_result_through_versioned_service(
    project_state_store,
):
    project_id = "project-execution"
    definition = ProjectDefinition(
        project_id=project_id,
        mode="project",
        story_plan=StoryPlan(
            project_id=project_id,
            user_prompt="placeholder",
            target_duration_seconds=60,
            aspect_ratio="16:9",
        ),
    )
    definitions = _definition_service(project_state_store)
    created = definitions.create(definition)
    planned = ProjectDefinition.from_dict(definition.to_dict())
    planned.story_plan.global_theme = "Planned theme"
    task_id = _create_task(
        project_state_store,
        project_id=project_id,
        status=TaskStatus.QUEUED.value,
        input_parameters=attach_project_plan_contract(
            {
                "project_id": project_id,
                "mode": "project",
                "project_definition_version": created.version,
                "generate_character_references": False,
            }
        ),
    )
    calls = {}

    def _host(**kwargs):
        calls.update(kwargs)
        return AgentExecutionResult(
            output_data=JsonObjectPayload.from_mapping(
                {
                    "status": "completed",
                    "project_definition": planned.to_dict(),
                },
                field_path="test.output",
            )
        )

    async def _character_refs(project_id_value, **kwargs):
        calls["character_refs"] = project_id_value
        return False

    use_case = QueuedExecutionUseCase(
        session_factory=project_state_store,
        host_runner=_host,
        agent_factory=lambda agent_type: calls.setdefault("agent_type", agent_type),
        character_reference_runner=_character_refs,
        project_definitions=definitions,
    )

    result = use_case.execute(QueuedExecutionCommand(task_id, QueuedExecutionKind.PROJECT_WORKFLOW))

    assert result["job_kind"] == PROJECT_JOB_KIND_WORKFLOW
    assert result["handler_key"] == PROJECT_JOB_HANDLER_PLAN_PROJECT
    assert calls["agent_type"] is AgentType.SERIES_PLANNER
    assert definitions.get(project_id).definition.story_plan.global_theme == "Planned theme"
    db = project_state_store()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).one()
        assert task.status == TaskStatus.COMPLETED.value
        assert task.output_metadata["character_references"]["status"] == "skipped"
    finally:
        db.close()


def test_project_worker_entrypoint_uses_project_command(monkeypatch):
    events = {}

    class _UseCase:
        def execute(self, command):
            events["command"] = command
            return {"status": "completed"}

    monkeypatch.setattr(project_job_queue, "QueuedExecutionUseCase", _UseCase)
    result = project_job_queue.sync_process_project_job("stable-project-worker")

    assert result == {"status": "completed"}
    assert events["command"].execution_kind is QueuedExecutionKind.PROJECT_WORKFLOW

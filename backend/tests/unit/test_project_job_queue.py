from types import SimpleNamespace

import pytest

from app.core.story_plan import (
    ProjectOperationState,
    ProjectState,
    StoryPlan,
    project_state_repository,
)
from app.domain import (
    AgentExecutionResult,
    AgentType,
    JsonObjectPayload,
    QueuedExecutionCommand,
    QueuedExecutionKind,
    TaskStatus,
    TaskType,
)
from app.models import Task
from app.services import project_job_queue
from app.services.project_job_contract import (
    PROJECT_JOB_HANDLER_PLAN_PROJECT,
    PROJECT_JOB_KIND_WORKFLOW,
    attach_project_plan_contract,
)
from app.services.queued_execution_use_case import QueuedExecutionUseCase

pytestmark = pytest.mark.usefixtures("project_state_store")


def _create_task(session_factory, *, input_parameters, status=TaskStatus.PENDING.value):
    db = session_factory()
    try:
        task = Task(
            title="Project Planning",
            description="project planning",
            task_type=TaskType.SCRIPT_WRITING,
            status=status,
            input_parameters=input_parameters,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return str(task.task_id)
    finally:
        db.close()


def _project_state(project_id):
    state = ProjectState(
        project_id=project_id,
        mode="project",
        story_plan=StoryPlan(
            project_id=project_id,
            user_prompt="test project",
            target_duration_seconds=120,
            aspect_ratio="16:9",
        ),
        global_settings={},
    )
    state.progress.planning.status = ProjectOperationState.QUEUED
    project_state_repository.save(state)
    return state


def _execution_result(payload):
    return AgentExecutionResult(
        output_data=JsonObjectPayload.from_mapping(
            payload,
            field_path="test.output_data",
        )
    )


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
        "stable-project-task",
        QueuedExecutionKind.PROJECT_WORKFLOW,
    )


def test_project_enqueue_persists_receipt_with_explicit_contract(project_state_store):
    task_id = _create_task(
        project_state_store,
        input_parameters=attach_project_plan_contract(
            {"project_id": "project-enqueue", "mode": "project"}
        ),
    )
    use_case = QueuedExecutionUseCase(session_factory=project_state_store)

    receipt = use_case.enqueue(
        QueuedExecutionCommand(task_id, QueuedExecutionKind.PROJECT_WORKFLOW),
        dispatch=lambda stable_id: f"transport-{stable_id}",
    )

    db = project_state_store()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        assert task.status == TaskStatus.QUEUED.value
        assert task.output_metadata["celery_task_id"] == f"transport-{task_id}"
        assert task.output_metadata["project_job"] == {
            "job_kind": PROJECT_JOB_KIND_WORKFLOW,
            "handler_key": PROJECT_JOB_HANDLER_PLAN_PROJECT,
        }
    finally:
        db.close()
    assert receipt == f"transport-{task_id}"


def test_project_enqueue_rejects_missing_explicit_dispatch_contract(project_state_store):
    task_id = _create_task(
        project_state_store,
        input_parameters={"project_id": "missing-contract", "mode": "project"},
    )
    use_case = QueuedExecutionUseCase(session_factory=project_state_store)

    with pytest.raises(ValueError, match="job_kind/handler_key"):
        use_case.enqueue(
            QueuedExecutionCommand(task_id, QueuedExecutionKind.PROJECT_WORKFLOW),
            dispatch=lambda stable_id: pytest.fail("dispatch must not run"),
        )


def test_project_execution_uses_same_application_entry_and_owns_business_transitions(
    project_state_store,
):
    project_id = "project-execution"
    _project_state(project_id)
    task_id = _create_task(
        project_state_store,
        input_parameters=attach_project_plan_contract(
            {
                "project_id": project_id,
                "mode": "project",
                "generate_character_references": False,
            }
        ),
        status=TaskStatus.QUEUED.value,
    )
    calls = {}

    def _host(**kwargs):
        calls.update(kwargs)
        return _execution_result({"status": "completed", "story_plan": {"project_id": project_id}})

    async def _character_refs(project_id_value, *, enabled, logger):
        calls["character_refs"] = (project_id_value, enabled)
        return False

    use_case = QueuedExecutionUseCase(
        session_factory=project_state_store,
        host_runner=_host,
        agent_factory=lambda agent_type: calls.setdefault("agent_type", agent_type) or object(),
        character_reference_runner=_character_refs,
    )

    result = use_case.execute(QueuedExecutionCommand(task_id, QueuedExecutionKind.PROJECT_WORKFLOW))

    db = project_state_store()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        assert task.status == TaskStatus.COMPLETED.value
        assert task.progress_percentage == 100
        assert task.output_metadata["project_id"] == project_id
    finally:
        db.close()
    state = project_state_repository.get(project_id)
    assert result["job_kind"] == PROJECT_JOB_KIND_WORKFLOW
    assert result["handler_key"] == PROJECT_JOB_HANDLER_PLAN_PROJECT
    assert calls["request"].task.task_id == task_id
    assert calls["agent_type"] == AgentType.SERIES_PLANNER
    assert calls["character_refs"] == (project_id, False)
    assert state.progress.planning.status == ProjectOperationState.COMPLETED
    assert state.progress.character_references.status == ProjectOperationState.SKIPPED


def test_project_worker_entrypoint_uses_project_command(monkeypatch):
    events = {}

    class _UseCase:
        def execute(self, command):
            events["command"] = command
            return {"status": "completed"}

    monkeypatch.setattr(project_job_queue, "QueuedExecutionUseCase", _UseCase)

    result = project_job_queue.sync_process_project_job("stable-project-worker")

    assert result == {"status": "completed"}
    assert events["command"].task_id == "stable-project-worker"
    assert events["command"].execution_kind == QueuedExecutionKind.PROJECT_WORKFLOW

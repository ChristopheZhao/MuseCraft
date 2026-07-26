import pytest
from pydantic import ValidationError
from sqlalchemy import event

from app.api.v1.endpoints.projects import (
    EpisodeGenerationRequest,
    EpisodeScriptRequest,
    _serialize_project_read_model,
)
from app.core.story_plan import EpisodeEditorialStatus, EpisodePlan, ProjectDefinition, StoryPlan
from app.domain import ProjectDefinitionError, ProjectDefinitionReason, TaskStatus, TaskType
from app.infrastructure.project_command_uow_sqlalchemy import SqlAlchemyProjectCommandUnitOfWork
from app.infrastructure.project_definition_store_sqlalchemy import (
    SqlAlchemyProjectDefinitionUnitOfWork,
)
from app.infrastructure.project_execution_read_model_sqlalchemy import (
    SqlAlchemyProjectExecutionReadModelQuery,
)
from app.models import Task, WorkflowNodeAttempt, WorkflowNodeState, WorkflowSession
from app.services.project_service import ProjectDefinitionApplicationService
from app.services.project_workflow_service import ProjectWorkflowApplicationService


def _definition(project_id="project-contract"):
    story = StoryPlan(
        project_id=project_id,
        user_prompt="Test project",
        target_duration_seconds=60,
        aspect_ratio="16:9",
    )
    episode = EpisodePlan.create(0, "Episode 1", 60, summary="Summary")
    story.add_episode(episode)
    return ProjectDefinition(project_id=project_id, mode="project", story_plan=story), episode


def _service(session_factory):
    return ProjectDefinitionApplicationService(
        lambda: SqlAlchemyProjectDefinitionUnitOfWork(session_factory)
    )


def test_project_definition_rejects_runtime_authority_fields():
    definition, _ = _definition()
    payload = definition.to_dict()
    payload["episodes_runtime"] = {}

    with pytest.raises(ValueError, match="runtime/read-model fields"):
        ProjectDefinition.from_dict(payload)


def test_project_definition_rejects_unknown_root_fields():
    definition, _ = _definition("project-strict-definition")
    payload = definition.to_dict()
    payload["workflow_session_id"] = 42

    with pytest.raises(ValueError, match="unsupported fields: workflow_session_id"):
        ProjectDefinition.from_dict(payload)


def test_same_version_commands_yield_one_commit_and_one_typed_conflict(
    project_state_store,
):
    service = _service(project_state_store)
    definition, episode = _definition("project-cas")
    created = service.create(definition)
    stale_copy = service.get(definition.project_id)

    updated = service.update_episode_script(
        project_id=definition.project_id,
        episode_id=episode.episode_id,
        script_text="Approved v1",
        approve=True,
        expected_version=created.version,
    )
    stale_copy.definition.story_plan.episodes[0].script_draft = "Lost update"
    with pytest.raises(ProjectDefinitionError) as exc_info:
        service.replace(stale_copy.definition, expected_version=stale_copy.version)

    assert exc_info.value.reason_code is ProjectDefinitionReason.VERSION_CONFLICT
    observed = service.get(definition.project_id)
    assert observed.version == updated.version == 2
    assert observed.definition.story_plan.episodes[0].approved_script == "Approved v1"


def test_project_remove_uses_atomic_expected_version_compare_and_delete(
    project_state_store,
):
    service = _service(project_state_store)
    definition, _episode = _definition("project-delete-cas")
    created = service.create(definition)
    updated = service.replace(definition, expected_version=created.version)
    statements = []
    engine = project_state_store.kw["bind"]

    def _capture_statement(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        statements.append(" ".join(str(statement).lower().split()))

    event.listen(engine, "before_cursor_execute", _capture_statement)
    try:
        with pytest.raises(ProjectDefinitionError) as exc_info:
            service.remove(
                definition.project_id,
                expected_version=created.version,
            )
    finally:
        event.remove(engine, "before_cursor_execute", _capture_statement)

    assert exc_info.value.reason_code is ProjectDefinitionReason.VERSION_CONFLICT
    observed = service.get(definition.project_id)
    assert observed.version == updated.version == 2
    delete_statement = next(
        statement
        for statement in statements
        if statement.startswith("delete from project_workspaces")
    )
    assert "project_workspaces.project_id =" in delete_statement
    assert "project_workspaces.version =" in delete_statement

    service.remove(definition.project_id, expected_version=updated.version)
    with pytest.raises(ProjectDefinitionError) as missing:
        service.get(definition.project_id)
    assert missing.value.reason_code is ProjectDefinitionReason.RECORD_NOT_FOUND


def test_project_creation_persists_definition_and_task_in_one_uow(project_state_store):
    definition, _ = _definition("project-command-uow")
    service = ProjectWorkflowApplicationService(
        lambda: SqlAlchemyProjectCommandUnitOfWork(project_state_store)
    )

    receipt = service.create_project(
        definition=definition,
        planning_input={
            "project_id": definition.project_id,
            "job_kind": "project_workflow",
            "handler_key": "plan_project",
        },
        title="Plan project",
        description="Test project",
    )

    db = project_state_store()
    try:
        task = db.query(Task).filter(Task.task_id == receipt.task.task_id).one()
        assert task.project_id == definition.project_id
        assert task.status == TaskStatus.PENDING.value
        assert task.input_parameters["project_definition_version"] == 1
    finally:
        db.close()
    assert _service(project_state_store).get(definition.project_id).version == 1


def test_planning_result_rolls_back_definition_when_task_completion_fails(
    project_state_store,
):
    definition, _ = _definition("project-planning-rollback")
    workflow = ProjectWorkflowApplicationService(
        lambda: SqlAlchemyProjectCommandUnitOfWork(project_state_store)
    )
    created = workflow.create_project(
        definition=definition,
        planning_input={
            "project_id": definition.project_id,
            "job_kind": "project_workflow",
            "handler_key": "plan_project",
        },
        title="Plan project",
        description="Test project",
    )
    planned = ProjectDefinition.from_dict(definition.to_dict())
    planned.story_plan.global_theme = "Must roll back"

    class _FailingTaskCompletionUnitOfWork(SqlAlchemyProjectCommandUnitOfWork):
        def complete_task(self, command):
            raise RuntimeError("task completion failed")

    failing_workflow = ProjectWorkflowApplicationService(
        lambda: _FailingTaskCompletionUnitOfWork(project_state_store)
    )

    with pytest.raises(RuntimeError, match="task completion failed"):
        failing_workflow.apply_planning_result(
            definition=planned,
            expected_version=created.project.version,
            task_id=created.task.task_id,
            character_references_requested=False,
        )

    observed = _service(project_state_store).get(definition.project_id)
    assert observed.version == 1
    assert observed.definition.story_plan.global_theme == ""
    db = project_state_store()
    try:
        task = db.query(Task).filter(Task.task_id == created.task.task_id).one()
        assert task.status == TaskStatus.PENDING.value
    finally:
        db.close()


def test_episode_execution_command_rejects_unapproved_selection_before_task_write(
    project_state_store,
):
    definition, episode = _definition("project-unapproved-command")
    workflow = ProjectWorkflowApplicationService(
        lambda: SqlAlchemyProjectCommandUnitOfWork(project_state_store)
    )
    created = workflow.create_project(
        definition=definition,
        planning_input={
            "project_id": definition.project_id,
            "job_kind": "project_workflow",
            "handler_key": "plan_project",
        },
        title="Plan project",
        description="Test project",
    )

    with pytest.raises(ProjectDefinitionError) as caught:
        workflow.enqueue_episode_execution(
            project_id=definition.project_id,
            expected_version=created.project.version,
            episode_ids=[episode.episode_id],
            episode_indices=[],
            auto_approve=False,
            execution_input={"project_id": definition.project_id},
            title="Execute episode",
            description="Test episode",
        )

    assert caught.value.reason_code is ProjectDefinitionReason.INVALID_PAYLOAD
    db = project_state_store()
    try:
        assert db.query(Task).filter(Task.project_id == definition.project_id).count() == 1
    finally:
        db.close()


def test_project_execution_projection_is_derived_and_serialization_is_read_only(
    project_state_store,
):
    definition, episode = _definition("project-read-model")
    created = _service(project_state_store).create(definition)
    db = project_state_store()
    try:
        task = Task(
            title="Episode workflow",
            description="Episode",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.COMPLETED.value,
            project_id=definition.project_id,
            episode_id=episode.episode_id,
            input_parameters={
                "project_id": definition.project_id,
                "episode_id": episode.episode_id,
            },
        )
        db.add(task)
        db.flush()
        runtime = WorkflowSession(
            task_db_id=task.id,
            mode="quick",
            project_id=definition.project_id,
            episode_id=episode.episode_id,
            status="completed",
            input_payload={
                "project_definition_version": created.version,
                "episode_editorial_revision": episode.editorial_revision,
            },
            summary_output={"final_video_url": "https://example.com/final.mp4"},
        )
        db.add(runtime)
        db.flush()
        node = WorkflowNodeState(
            session_id=runtime.id,
            node_key="compose",
            node_type="compose",
            order_index=1,
            scope_type="episode",
            status="completed",
        )
        db.add(node)
        db.flush()
        db.add(
            WorkflowNodeAttempt(
                session_id=runtime.id,
                node_id=node.id,
                attempt_no=1,
                trigger_reason="initial",
                requested_by="system",
                status="succeeded",
                metrics={"total_cost": 1.25, "total_tokens": 42},
            )
        )
        db.commit()
    finally:
        db.close()

    model = SqlAlchemyProjectExecutionReadModelQuery(project_state_store).get(definition.project_id)
    response = _serialize_project_read_model(model)

    assert response.version == 1
    assert response.episodes_runtime[episode.episode_id].status == "completed"
    assert (
        response.episodes_runtime[episode.episode_id]
        .output_assets["final_video_url"]
        .endswith("final.mp4")
    )
    assert response.total_cost == 1.25
    assert response.total_tokens == 42
    assert _service(project_state_store).get(definition.project_id).version == 1


def test_project_mutation_requests_require_expected_version():
    with pytest.raises(ValidationError):
        EpisodeScriptRequest(script_text="draft")
    with pytest.raises(ValidationError):
        EpisodeGenerationRequest()

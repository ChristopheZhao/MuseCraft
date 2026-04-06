import asyncio
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks
from pydantic import ValidationError

from app.agents.episode_orchestrator import EpisodeOrchestratorAgent
from app.api.v1.endpoints import projects as projects_endpoint
from app.core.constants import GenerationMode
from app.core.story_plan import (
    EpisodeEditorialStatus,
    EpisodeExecutionStatus,
    ProjectOperationState,
    ProjectState,
    StoryPlan,
    EpisodePlan,
    project_state_repository,
)
from app.models import Task, TaskStatus, TaskType
from app.api.v1.endpoints.projects import _serialize_project_state
from app.services.project_job_contract import (
    PROJECT_JOB_HANDLER_PLAN_PROJECT,
    PROJECT_JOB_KIND_WORKFLOW,
)
from app.services.project_service import update_episode_script


pytestmark = pytest.mark.usefixtures("project_state_store")


def _build_project_state(project_id: str = "project-contracts") -> tuple[ProjectState, EpisodePlan]:
    story_plan = StoryPlan(
        project_id=project_id,
        user_prompt="Test project",
        target_duration_seconds=180,
        aspect_ratio="16:9",
    )
    episode = EpisodePlan.create(
        sequence_index=0,
        title="Episode 1",
        target_duration_seconds=60,
        summary="Summary",
    )
    story_plan.add_episode(episode)

    project_state = ProjectState(
        project_id=project_id,
        mode="project",
        story_plan=story_plan,
        global_settings={},
    )
    project_state_repository.save(project_state)
    return project_state, episode


def test_mark_episode_runtime_status_does_not_mutate_editorial_status():
    project_state, episode = _build_project_state("project-contracts-separate")
    episode.status = EpisodeEditorialStatus.APPROVED

    project_state.mark_episode_runtime_status(
        episode.episode_id,
        EpisodeExecutionStatus.FAILED,
        error="runtime failed",
    )

    assert project_state.story_plan.episodes[0].status == EpisodeEditorialStatus.APPROVED
    assert project_state.episodes_runtime[episode.episode_id].status == EpisodeExecutionStatus.FAILED
    assert project_state.episodes_runtime[episode.episode_id].error == "runtime failed"
    project_state_repository.remove(project_state.project_id)


def test_project_state_to_dict_exposes_typed_progress_projection():
    project_state, episode = _build_project_state("project-contracts-progress")
    project_state.progress.planning.status = ProjectOperationState.IN_PROGRESS
    project_state.progress.planning.task_id = "task-plan-1"
    project_state.progress.character_references.status = ProjectOperationState.SKIPPED
    project_state.mark_episode_runtime_status(episode.episode_id, EpisodeExecutionStatus.COMPLETED)

    payload = project_state.to_dict()

    assert payload["progress"]["planning"]["status"] == ProjectOperationState.IN_PROGRESS.value
    assert payload["progress"]["planning"]["task_id"] == "task-plan-1"
    assert payload["progress"]["character_references"]["status"] == ProjectOperationState.SKIPPED.value
    assert payload["episodes_runtime"][episode.episode_id]["status"] == EpisodeExecutionStatus.COMPLETED.value
    assert payload["completed_episodes"] == 1

    project_state_repository.remove(project_state.project_id)


def test_update_episode_script_keeps_approved_script_until_reapproved():
    project_state, episode = _build_project_state("project-contracts-approved-script")
    episode.status = EpisodeEditorialStatus.APPROVED
    runtime = project_state.ensure_runtime_state(episode.episode_id)
    runtime.status = EpisodeExecutionStatus.COMPLETED
    runtime.approved_script = "approved v1"
    project_state_repository.save(project_state)

    updated = update_episode_script(
        project_id=project_state.project_id,
        episode_id=episode.episode_id,
        script_text="draft v2",
        approve=False,
    )

    refreshed_runtime = updated.episodes_runtime[episode.episode_id]
    assert updated.story_plan.episodes[0].script_draft == "draft v2"
    assert updated.story_plan.episodes[0].status == EpisodeEditorialStatus.NEEDS_REVISION
    assert refreshed_runtime.approved_script == "approved v1"
    assert refreshed_runtime.status == EpisodeExecutionStatus.STALE

    updated = update_episode_script(
        project_id=project_state.project_id,
        episode_id=episode.episode_id,
        script_text="draft v2",
        approve=True,
    )

    refreshed_runtime = updated.episodes_runtime[episode.episode_id]
    assert updated.story_plan.episodes[0].status == EpisodeEditorialStatus.APPROVED
    assert refreshed_runtime.approved_script == "draft v2"
    project_state_repository.remove(project_state.project_id)


def test_project_response_serialization_materializes_runtime_for_each_episode():
    project_state, episode = _build_project_state("project-contracts-runtime-projection")

    payload = _serialize_project_state(project_state)

    assert episode.episode_id in payload.episodes_runtime
    assert payload.episodes_runtime[episode.episode_id].status == EpisodeExecutionStatus.IDLE.value
    project_state_repository.remove(project_state.project_id)


def test_project_state_repository_round_trips_through_shared_backing():
    project_state, episode = _build_project_state("project-contracts-persistent-roundtrip")
    project_state.progress.planning.status = ProjectOperationState.IN_PROGRESS
    project_state.progress.planning.task_id = "task-plan-persistent"
    runtime = project_state.ensure_runtime_state(episode.episode_id)
    runtime.status = EpisodeExecutionStatus.STALE
    runtime.approved_script = "approved script"
    project_state_repository.save(project_state)

    loaded = project_state_repository.get(project_state.project_id)

    assert loaded is not None
    assert loaded.project_id == project_state.project_id
    assert loaded.progress.planning.status == ProjectOperationState.IN_PROGRESS
    assert loaded.progress.planning.task_id == "task-plan-persistent"
    assert loaded.story_plan.episodes[0].episode_id == episode.episode_id
    assert loaded.episodes_runtime[episode.episode_id].status == EpisodeExecutionStatus.STALE
    assert loaded.episodes_runtime[episode.episode_id].approved_script == "approved script"

    project_state_repository.remove(project_state.project_id)


def test_create_project_bootstraps_placeholder_from_shared_backing(monkeypatch, project_state_store):
    monkeypatch.setattr(projects_endpoint, "SessionLocal", project_state_store)
    monkeypatch.setattr(projects_endpoint, "_schedule_project_plan", lambda *args, **kwargs: "project-celery-1")

    response = asyncio.run(
        projects_endpoint.create_project(
            projects_endpoint.ProjectCreateRequest(
                user_prompt="A rabbit hero project",
                target_duration_seconds=120,
            )
        )
    )
    fetched = asyncio.run(projects_endpoint.get_project(response.project.project_id))

    assert fetched.project_id == response.project.project_id
    assert fetched.progress.planning.status == ProjectOperationState.QUEUED.value
    assert len(fetched.story_plan.episodes) >= 1
    assert fetched.story_plan.project_id == response.project.project_id

    project_state_repository.remove(response.project.project_id)


def test_create_project_attaches_explicit_project_job_contract(monkeypatch, project_state_store):
    monkeypatch.setattr(projects_endpoint, "SessionLocal", project_state_store)
    monkeypatch.setattr(projects_endpoint, "_schedule_project_plan", lambda *args, **kwargs: "project-celery-2")

    response = asyncio.run(
        projects_endpoint.create_project(
            projects_endpoint.ProjectCreateRequest(
                user_prompt="A fox detective project",
                target_duration_seconds=120,
            )
        )
    )

    db = project_state_store()
    try:
        task = db.query(Task).filter(Task.task_id == response.task_id).first()
        assert task is not None
        assert task.task_type == TaskType.SCRIPT_WRITING
        assert (task.input_parameters or {}).get("job_kind") == PROJECT_JOB_KIND_WORKFLOW
        assert (task.input_parameters or {}).get("handler_key") == PROJECT_JOB_HANDLER_PLAN_PROJECT
    finally:
        db.close()

    project_state_repository.remove(response.project.project_id)


def test_orchestrate_project_force_rerun_does_not_pre_mark_unapproved_episode(monkeypatch):
    project_state, episode = _build_project_state("project-contracts-force-rerun-endpoint")
    runtime = project_state.ensure_runtime_state(episode.episode_id)
    runtime.status = EpisodeExecutionStatus.IDLE
    episode.status = EpisodeEditorialStatus.DRAFT
    project_state_repository.save(project_state)

    fake_task = SimpleNamespace(id=101, task_id="task-force-rerun-endpoint", status="pending")

    class _FakeSession:
        def commit(self):
            return None

        def rollback(self):
            return None

        def add(self, _obj):
            return None

        def close(self):
            return None

    monkeypatch.setattr(projects_endpoint, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        projects_endpoint,
        "_create_task",
        lambda *args, **kwargs: fake_task,
    )

    response = asyncio.run(
        projects_endpoint.orchestrate_project(
            project_state.project_id,
            projects_endpoint.EpisodeGenerationRequest(
                episode_ids=[episode.episode_id],
                force_rerun=True,
            ),
            BackgroundTasks(),
        )
    )

    assert response.project.story_plan.episodes[0].status == EpisodeEditorialStatus.DRAFT.value
    assert response.project.episodes_runtime[episode.episode_id].status == EpisodeExecutionStatus.IDLE.value
    project_state_repository.remove(project_state.project_id)


def test_orchestrate_project_queues_episode_generation_through_task_queue(monkeypatch):
    project_state, episode = _build_project_state("project-contracts-queue-host")
    runtime = project_state.ensure_runtime_state(episode.episode_id)
    runtime.status = EpisodeExecutionStatus.IDLE
    episode.status = EpisodeEditorialStatus.APPROVED
    project_state_repository.save(project_state)

    fake_task = SimpleNamespace(id=202, task_id="task-project-queue", status=TaskStatus.QUEUED.value)
    queue_events = {}

    class _FakeSession:
        def commit(self):
            return None

        def rollback(self):
            return None

        def add(self, _obj):
            return None

        def close(self):
            return None

    class _FakeQueueService:
        def __init__(self):
            queue_events["created"] = queue_events.get("created", 0) + 1

        async def queue_task(self, task_id):
            queue_events["task_id"] = task_id

    monkeypatch.setattr(projects_endpoint, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(projects_endpoint, "TaskQueueService", _FakeQueueService)
    monkeypatch.setattr(
        projects_endpoint,
        "_create_task",
        lambda *args, **kwargs: fake_task,
    )

    background_tasks = BackgroundTasks()
    response = asyncio.run(
        projects_endpoint.orchestrate_project(
            project_state.project_id,
            projects_endpoint.EpisodeGenerationRequest(
                episode_ids=[episode.episode_id],
            ),
            background_tasks,
        )
    )

    assert queue_events["created"] == 1
    assert len(background_tasks.tasks) == 1
    scheduled = background_tasks.tasks[0]
    assert scheduled.args == (fake_task.id,)
    assert response.project.episodes_runtime[episode.episode_id].status == EpisodeExecutionStatus.GENERATING.value
    project_state_repository.remove(project_state.project_id)


def test_episode_generation_request_rejects_legacy_runtime_overrides_bag():
    with pytest.raises(ValidationError):
        projects_endpoint.EpisodeGenerationRequest(
            episode_ids=["episode-1"],
            runtime_overrides={"generate_audio": True},
        )


def test_episode_orchestrator_force_rerun_does_not_bypass_editorial_approval():
    agent = object.__new__(EpisodeOrchestratorAgent)
    agent.logger = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None)
    agent._validate_input = lambda _input, _required: None

    async def _noop_async(*args, **kwargs):
        return None

    async def _forbidden_run_single_episode(*args, **kwargs):
        raise AssertionError("force_rerun must not execute unapproved episodes")

    agent._sync_project_foundation = lambda _project_state: None
    agent._ensure_project_character_reference_images = _noop_async
    agent._update_progress = _noop_async
    agent._run_single_episode = _forbidden_run_single_episode

    project_state, episode = _build_project_state("project-contracts-force-rerun-orchestrator")
    runtime = project_state.ensure_runtime_state(episode.episode_id)
    runtime.status = EpisodeExecutionStatus.COMPLETED
    episode.status = EpisodeEditorialStatus.DRAFT
    project_state_repository.save(project_state)

    agent._resolve_episode_selection = lambda _project_state, _input: [_project_state.story_plan.episodes[0]]

    task = SimpleNamespace(
        status=TaskStatus.PENDING.value,
        error_message=None,
        session_id="session-force-rerun",
        user_id=None,
        update_progress=lambda *args, **kwargs: None,
    )
    db = SimpleNamespace(commit=lambda: None)

    result = asyncio.run(
        EpisodeOrchestratorAgent._execute_impl(
            agent,
            task,
            {
                "project_id": project_state.project_id,
                "mode": GenerationMode.PROJECT.value,
                "force_rerun": True,
            },
            db,
        )
    )

    assert result["episodes"][0]["skipped"] is True
    assert result["episodes"][0]["reason"] == "Episode script not approved for generation"
    assert result["episodes"][0]["status"] == EpisodeExecutionStatus.COMPLETED.value
    project_state_repository.remove(project_state.project_id)

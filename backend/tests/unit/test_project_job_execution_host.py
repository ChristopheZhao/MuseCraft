from types import SimpleNamespace

import pytest

from app.core.story_plan import ProjectOperationState, ProjectState, StoryPlan, project_state_repository
from app.services import project_job_execution_host
from app.services.project_job_contract import (
    PROJECT_JOB_HANDLER_PLAN_PROJECT,
    PROJECT_JOB_KIND_WORKFLOW,
    attach_project_plan_contract,
)


pytestmark = pytest.mark.usefixtures("project_state_store")


def test_run_project_job_in_host_executes_project_planning_handler(monkeypatch):
    project_id = "project-job-host-route"
    project_state = ProjectState(
        project_id=project_id,
        mode="project",
        story_plan=StoryPlan(
            project_id=project_id,
            user_prompt="host route test",
            target_duration_seconds=120,
            aspect_ratio="16:9",
        ),
        global_settings={},
    )
    project_state.progress.character_references.status = ProjectOperationState.IN_PROGRESS
    project_state_repository.save(project_state)

    host_events = {}

    class _FakePlanner:
        async def execute(self, *, task, input_data, db, execution_order=1):
            host_events["task_id"] = task.task_id
            host_events["input_data"] = dict(input_data)
            host_events["execution_order"] = execution_order
            return {"status": "completed", "story_plan": {"project_id": project_id}}

    class _FakePolicyManager:
        def __init__(self, _path):
            host_events["policy_loaded"] = True

        def build_llms_for_agent(self, agent_key):
            host_events["agent_key"] = agent_key
            return {}

    reset_calls = []
    progress_calls = []

    async def _fake_character_refs(project_id_value, *, enabled, logger):
        host_events["character_refs"] = {
            "project_id": project_id_value,
            "enabled": enabled,
            "logger_present": logger is not None,
        }
        return False

    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(project_job_execution_host, "reset_event_bus", lambda: reset_calls.append(True))
    monkeypatch.setattr("app.agents.utils.llm_policy.LLMPolicyManager", _FakePolicyManager)
    monkeypatch.setattr(
        "app.agents.series_planner.SeriesPlannerAgent.create_default",
        classmethod(lambda cls, llms=None: _FakePlanner()),
    )
    monkeypatch.setattr(
        "app.services.character_reference_images.ensure_project_character_reference_images",
        _fake_character_refs,
    )

    task = SimpleNamespace(
        id=1,
        task_id="project-job-host-task",
        update_progress=lambda message, progress: progress_calls.append((message, progress)),
    )
    db = SimpleNamespace(commit=lambda: None)

    result = project_job_execution_host.run_project_job_in_host(
        PROJECT_JOB_KIND_WORKFLOW,
        PROJECT_JOB_HANDLER_PLAN_PROJECT,
        task=task,
        input_data=attach_project_plan_contract(
            {
                "project_id": project_id,
                "generate_character_references": True,
            }
        ),
        db=db,
        execution_order=3,
    )

    refreshed = project_state_repository.get(project_id)

    assert reset_calls == [True]
    assert result["status"] == "completed"
    assert result["job_kind"] == PROJECT_JOB_KIND_WORKFLOW
    assert result["handler_key"] == PROJECT_JOB_HANDLER_PLAN_PROJECT
    assert host_events["policy_loaded"] is True
    assert host_events["agent_key"] == "series_planner"
    assert host_events["task_id"] == "project-job-host-task"
    assert host_events["execution_order"] == 3
    assert host_events["character_refs"]["project_id"] == project_id
    assert progress_calls == [("Generating character references", 90)]
    assert refreshed is not None
    assert refreshed.progress.character_references.status == ProjectOperationState.SKIPPED
    assert refreshed.progress.character_references.error is None

    project_state_repository.remove(project_id)

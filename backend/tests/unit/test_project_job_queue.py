from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.core.story_plan import ProjectOperationState, ProjectState, StoryPlan, project_state_repository
from app.models import Task, TaskStatus, TaskType
from app.services import project_job_queue
from app.services.project_job_contract import (
    PROJECT_JOB_HANDLER_PLAN_PROJECT,
    PROJECT_JOB_KIND_WORKFLOW,
    attach_project_plan_contract,
)


pytestmark = pytest.mark.usefixtures("project_state_store")


def _create_task(session_factory, *, input_parameters, status=TaskStatus.PENDING.value, task_type=TaskType.SCRIPT_WRITING):
    db: Session = session_factory()
    try:
        task = Task(
            title="Project Planning",
            description="project planning",
            task_type=task_type,
            status=status,
            input_parameters=input_parameters,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
    finally:
        db.close()
    return task_id


def test_project_job_queue_persists_celery_handle_with_explicit_contract(monkeypatch, project_state_store):
    task_id = _create_task(
        project_state_store,
        input_parameters=attach_project_plan_contract({"project_id": "project-job-1", "mode": "project"}),
    )

    monkeypatch.setattr(project_job_queue, "SyncSessionLocal", project_state_store)
    monkeypatch.setattr(
        "app.services.celery_app.process_project_job",
        SimpleNamespace(delay=lambda queued_task_id: SimpleNamespace(id=f"project-celery-{queued_task_id}")),
    )

    celery_task_id = project_job_queue.ProjectJobQueueService().queue_task(task_id)

    db = project_state_store()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        assert celery_task_id == f"project-celery-{task_id}"
        assert task.status == TaskStatus.QUEUED.value
        assert (task.output_metadata or {}).get("celery_task_id") == f"project-celery-{task_id}"
        assert (task.output_metadata or {}).get("project_job") == {
            "job_kind": PROJECT_JOB_KIND_WORKFLOW,
            "handler_key": PROJECT_JOB_HANDLER_PLAN_PROJECT,
        }
    finally:
        db.close()


def test_project_job_queue_rejects_missing_explicit_dispatch_contract(monkeypatch, project_state_store):
    task_id = _create_task(
        project_state_store,
        input_parameters={"project_id": "project-job-missing-contract", "mode": "project"},
    )
    monkeypatch.setattr(project_job_queue, "SyncSessionLocal", project_state_store)

    with pytest.raises(ValueError, match="job_kind/handler_key"):
        project_job_queue.ProjectJobQueueService().queue_task(task_id)


def test_sync_process_project_job_routes_through_explicit_project_job_contract(monkeypatch, project_state_store):
    project_id = "project-job-sync-route"
    project_state = ProjectState(
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
    project_state.progress.planning.status = ProjectOperationState.QUEUED
    project_state_repository.save(project_state)

    task_id = _create_task(
        project_state_store,
        input_parameters=attach_project_plan_contract({"project_id": project_id, "mode": "project"}),
        status=TaskStatus.QUEUED.value,
    )

    host_calls = {}

    def _fake_host(job_kind, handler_key, *, task, input_data, db, execution_order=1):
        host_calls["job_kind"] = job_kind
        host_calls["handler_key"] = handler_key
        host_calls["task_id"] = task.id
        host_calls["input_data"] = dict(input_data)
        host_calls["execution_order"] = execution_order
        return {
            "status": "completed",
            "result": {"story_plan": {"project_id": project_id}},
            "job_kind": job_kind,
            "handler_key": handler_key,
        }

    monkeypatch.setattr(project_job_queue, "SyncSessionLocal", project_state_store)
    monkeypatch.setattr(project_job_queue, "run_project_job_in_host", _fake_host)

    result = project_job_queue.sync_process_project_job(task_id)

    db = project_state_store()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        assert task.status == TaskStatus.COMPLETED.value
        assert result["job_kind"] == PROJECT_JOB_KIND_WORKFLOW
        assert result["handler_key"] == PROJECT_JOB_HANDLER_PLAN_PROJECT
        assert host_calls["job_kind"] == PROJECT_JOB_KIND_WORKFLOW
        assert host_calls["handler_key"] == PROJECT_JOB_HANDLER_PLAN_PROJECT
        assert host_calls["task_id"] == task_id
        assert host_calls["execution_order"] == 1
    finally:
        db.close()

    refreshed = project_state_repository.get(project_id)
    assert refreshed is not None
    assert refreshed.progress.planning.status == ProjectOperationState.COMPLETED
    assert refreshed.progress.planning.error is None
    project_state_repository.remove(project_id)

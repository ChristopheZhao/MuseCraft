import asyncio
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from types import SimpleNamespace

from app.core.database import Base
from app.models import (
    Task,
    TaskType,
    TaskStatus,
    WorkflowSessionStatus,
    WorkflowNodeStatus,
)
from app.services.runtime_session_service import RuntimeSessionService
from app.services.script_review_contract import get_script_review_contract


@pytest.fixture
def sync_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_task(db):
    task = Task(
        title="Runtime Test",
        description="runtime test",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.PENDING.value,
        input_parameters={"user_prompt": "test prompt"},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_get_or_create_session_initializes_default_nodes(sync_db):
    task = _create_task(sync_db)

    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)

    assert session.status == WorkflowSessionStatus.QUEUED.value
    assert task.output_metadata["workflow_session_id"] == session.id
    assert view is not None
    assert [node["node_key"] for node in view["nodes"]] == [
        "concept",
        "script",
        "image",
        "video",
        "voice",
        "compose",
        "audio",
        "quality",
    ]


def test_mark_session_running_and_completed_updates_projection(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

    RuntimeSessionService.mark_session_running_sync(sync_db, session, task=task)
    running_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    assert running_view["status"] == WorkflowSessionStatus.RUNNING.value
    assert running_view["current_node_key"] == "concept"
    assert running_view["nodes"][0]["status"] == WorkflowNodeStatus.RUNNING.value

    RuntimeSessionService.mark_session_completed_sync(
        sync_db,
        session,
        task=task,
        summary_output={"final_video_url": "https://example.com/final.mp4"},
    )
    completed_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    assert completed_view["status"] == WorkflowSessionStatus.COMPLETED.value
    assert completed_view["summary_output"]["final_video_url"] == "https://example.com/final.mp4"
    assert completed_view["nodes"][0]["status"] == WorkflowNodeStatus.COMPLETED.value
    assert all(
        node["status"] in {WorkflowNodeStatus.COMPLETED.value, WorkflowNodeStatus.SKIPPED.value}
        for node in completed_view["nodes"]
    )


def test_open_human_gate_exposes_waiting_gate_in_runtime_view(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        task=task,
        progress_step="Generating script",
        progress_percentage=15,
    )
    RuntimeSessionService.complete_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        attempt_id=attempt.id,
        output_artifacts=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        metrics={"scenes_generated": 1},
        artifact_refs=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        node_status=WorkflowNodeStatus.RUNNING.value,
    )
    RuntimeSessionService.open_human_gate_sync(
        sync_db,
        session,
        node_key="script",
        gate_name="script_review",
        gate_type="human_review",
        attempt_id=attempt.id,
        facts={"script_preview_text": "draft"},
        allowed_actions=["approve", "revise", "replan"],
        recommended_action="approve",
        task=task,
        progress_step="Waiting for script approval",
        progress_percentage=35,
    )
    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    nodes_by_key = {node["node_key"]: node for node in view["nodes"]}

    assert view["status"] == WorkflowSessionStatus.WAITING_GATE.value
    assert view["current_node_key"] == "script"
    assert view["active_gate"]["gate_name"] == "script_review"
    assert view["active_gate"]["latest_decision"] is None
    assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.PENDING_GATE.value


def test_submit_gate_decision_marks_revision_state(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        task=task,
        progress_step="Generating script",
        progress_percentage=15,
    )
    RuntimeSessionService.complete_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        attempt_id=attempt.id,
        output_artifacts=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        metrics={"scenes_generated": 1},
        artifact_refs=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        node_status=WorkflowNodeStatus.RUNNING.value,
    )
    RuntimeSessionService.open_human_gate_sync(
        sync_db,
        session,
        node_key="script",
        gate_name="script_review",
        gate_type="human_review",
        attempt_id=attempt.id,
        facts={"script_preview_text": "draft"},
        allowed_actions=["approve", "revise", "replan"],
        recommended_action="approve",
        task=task,
        progress_step="Waiting for script approval",
        progress_percentage=35,
    )

    decision = RuntimeSessionService.submit_gate_decision_sync(
        sync_db,
        session.id,
        node_key="script",
        action="revise",
        feedback_text="tighten scene pacing",
        structured_constraints={"keep_character": True},
    )
    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    nodes_by_key = {node["node_key"]: node for node in view["nodes"]}

    assert decision.action == "revise"
    assert view["status"] == WorkflowSessionStatus.RESUMING.value
    assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.NEEDS_REVISION.value
    assert nodes_by_key["script"]["revision_index"] == 1
    assert view["active_gate"]["latest_decision"]["feedback_text"] == "tighten scene pacing"
    refreshed_session = RuntimeSessionService.get_session_by_id_sync(sync_db, session.id)
    review_contract = get_script_review_contract(refreshed_session.input_payload)
    assert review_contract is not None
    assert review_contract["action"] == "revise"
    assert review_contract["feedback_text"] == "tighten scene pacing"
    assert review_contract["structured_constraints"] == {"keep_character": True}


def test_mark_session_cancelled_for_task_cancels_without_runtime_session(monkeypatch):
    task = SimpleNamespace(id=7, status=TaskStatus.IN_PROGRESS.value)
    commit_events = {"count": 0}

    class _FakeDb:
        async def commit(self):
            commit_events["count"] += 1

    async def _return_none(*args, **kwargs):
        return None

    monkeypatch.setattr(RuntimeSessionService, "get_latest_session_for_task", _return_none)

    result = asyncio.run(RuntimeSessionService.mark_session_cancelled_for_task(_FakeDb(), task))

    assert result is None
    assert task.status == TaskStatus.CANCELLED.value
    assert commit_events["count"] == 1


def test_create_session_for_task_refreshes_task_after_commit(monkeypatch):
    refreshed_targets = []

    class _FakeAsyncDb:
        def __init__(self):
            self._added = []

        def add(self, obj):
            self._added.append(obj)

        async def flush(self):
            for obj in self._added:
                if getattr(obj, "id", None) is None:
                    obj.id = 123

        async def commit(self):
            return None

        async def refresh(self, obj):
            refreshed_targets.append(obj)

    async def _noop_ensure_default_nodes(db, session):
        return None

    monkeypatch.setattr(RuntimeSessionService, "_ensure_default_nodes_async", _noop_ensure_default_nodes)

    task = SimpleNamespace(
        id=7,
        task_id="task-7",
        input_parameters={"user_prompt": "test prompt"},
        output_metadata={},
    )
    fake_db = _FakeAsyncDb()

    session = asyncio.run(RuntimeSessionService.create_session_for_task(fake_db, task, mode="quick"))

    assert session.id == 123
    assert task.output_metadata["workflow_session_id"] == 123
    assert refreshed_targets[0] is session
    assert refreshed_targets[1] is task

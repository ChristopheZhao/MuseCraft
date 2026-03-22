import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import Task, TaskStatus, TaskType, WorkflowSessionStatus
from app.services import task_queue
from app.services.runtime_session_service import RuntimeSessionService


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield SessionLocal
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_task(session_factory, *, input_parameters):
    db = session_factory()
    try:
        task = Task(
            title="Queue Test",
            description="queue test",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.PENDING.value,
            input_parameters=input_parameters,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
    finally:
        db.close()
    return task_id


def test_sync_process_video_task_routes_voice_settings_to_standard_dispatch(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={
            "user_prompt": "test prompt",
            "voice_settings": {"voice_id": "narrator_a"},
        },
    )
    dispatch_calls = {}

    async def _fake_dispatch(mode, *, task, input_data, db, execution_order=1):
        dispatch_calls["mode"] = mode.value
        dispatch_calls["task_id"] = task.id
        dispatch_calls["input_data"] = dict(input_data)
        dispatch_calls["execution_order"] = execution_order
        task.status = TaskStatus.COMPLETED.value
        db.commit()
        return {"workflow_status": "completed", "final_video_url": "https://example.com/final.mp4"}

    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    reset_calls = []
    monkeypatch.setattr(task_queue, "reset_event_bus", lambda: reset_calls.append(True))
    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(task_queue, "dispatch_generation", _fake_dispatch)

    result = task_queue.sync_process_video_task(task_id)

    assert reset_calls == [True]
    assert result["route"] == "orchestrator_mainline"
    assert result["mode"] == "quick"
    assert result["status"] == "completed"
    assert dispatch_calls["mode"] == "quick"
    assert dispatch_calls["task_id"] == task_id
    assert dispatch_calls["input_data"]["voice_settings"] == {"voice_id": "narrator_a"}


def test_sync_process_video_task_routes_silent_quick_payload_to_orchestrator_mainline(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test prompt"},
    )
    dispatch_calls = {}

    async def _fake_dispatch(mode, *, task, input_data, db, execution_order=1):
        dispatch_calls["mode"] = mode.value
        dispatch_calls["task_id"] = task.id
        dispatch_calls["input_data"] = dict(input_data)
        dispatch_calls["execution_order"] = execution_order
        task.status = TaskStatus.COMPLETED.value
        db.commit()
        return {"workflow_status": "completed", "final_video_url": "https://example.com/final.mp4"}

    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(task_queue, "dispatch_generation", _fake_dispatch)

    result = task_queue.sync_process_video_task(task_id)

    assert result["route"] == "orchestrator_mainline"
    assert result["mode"] == "quick"
    assert result["status"] == "completed"
    assert dispatch_calls["mode"] == "quick"
    assert dispatch_calls["task_id"] == task_id
    assert dispatch_calls["input_data"]["user_prompt"] == "test prompt"


def test_sync_process_video_task_prefers_runtime_session_payload_for_quick_dispatch(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "task payload"},
    )
    dispatch_calls = {}

    async def _fake_dispatch(mode, *, task, input_data, db, execution_order=1):
        dispatch_calls["input_data"] = dict(input_data)
        task.status = TaskStatus.COMPLETED.value
        db.commit()
        return {"workflow_status": "completed"}

    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(task_queue, "dispatch_generation", _fake_dispatch)

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        session = task_queue.RuntimeSessionService.get_or_create_session_for_task_sync(db, task, mode="quick")
        session.input_payload = {"user_prompt": "runtime payload", "runtime_contracts": {"script_review": {"action": "approve"}}}
        db.commit()
    finally:
        db.close()

    result = task_queue.sync_process_video_task(task_id)

    assert result["route"] == "orchestrator_mainline"
    assert dispatch_calls["input_data"]["user_prompt"] == "runtime payload"
    assert dispatch_calls["input_data"]["runtime_contracts"] == {"script_review": {"action": "approve"}}


def test_queue_task_persists_celery_handle_and_sets_queued(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test prompt"},
    )

    monkeypatch.setattr(
        "app.services.celery_app.process_video_task",
        SimpleNamespace(delay=lambda queued_task_id: SimpleNamespace(id=f"celery-{queued_task_id}")),
    )
    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)

    celery_task_id = asyncio.run(task_queue.TaskQueueService().queue_task(task_id))

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        assert celery_task_id == f"celery-{task_id}"
        assert task.status == TaskStatus.QUEUED.value
        assert (task.output_metadata or {}).get("celery_task_id") == f"celery-{task_id}"
    finally:
        db.close()


def test_queue_task_skips_waiting_gate_runtime_session(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test prompt"},
    )
    delay_calls = {}

    def _unexpected_delay(_queued_task_id):
        delay_calls["called"] = True
        return SimpleNamespace(id="unexpected")

    monkeypatch.setattr(
        "app.services.celery_app.process_video_task",
        SimpleNamespace(delay=_unexpected_delay),
    )
    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        session = RuntimeSessionService.get_or_create_session_for_task_sync(db, task, mode="quick")
        session.status = WorkflowSessionStatus.WAITING_GATE.value
        task.status = TaskStatus.IN_PROGRESS.value
        db.commit()
    finally:
        db.close()

    celery_task_id = asyncio.run(task_queue.TaskQueueService().queue_task(task_id))

    assert celery_task_id is None
    assert delay_calls == {}


def test_sync_process_video_task_skips_terminal_quick_runtime(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test prompt"},
    )
    dispatch_calls = {}

    async def _fake_dispatch(mode, *, task, input_data, db, execution_order=1):
        dispatch_calls["called"] = True
        return {"workflow_status": "completed"}

    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(task_queue, "dispatch_generation", _fake_dispatch)

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        session = RuntimeSessionService.get_or_create_session_for_task_sync(db, task, mode="quick")
        RuntimeSessionService.mark_session_failed_sync(
            db,
            session,
            error_message="boom",
            task=task,
        )
    finally:
        db.close()

    result = task_queue.sync_process_video_task(task_id)

    assert result["status"] == "skipped"
    assert result["skip_reason"] == "runtime_terminal:failed"
    assert result["mode"] == "quick"
    assert result["route"] == "orchestrator_mainline"
    assert dispatch_calls == {}

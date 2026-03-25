import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.constants import GenerationMode
from app.core.database import Base
from app.models import Task, TaskStatus, TaskType, WorkflowSessionStatus
from app.services import queued_task_execution_host
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


def test_run_generation_in_host_initializes_worker_host_and_routes_quick_to_orchestrator(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={
            "user_prompt": "test prompt",
            "voice_settings": {"voice_id": "narrator_a"},
        },
    )
    orchestrator_calls = {}

    class _FakeOrchestrator:
        async def execute(self, *, task, input_data, db, execution_order=1):
            orchestrator_calls["task_id"] = task.id
            orchestrator_calls["input_data"] = dict(input_data)
            orchestrator_calls["execution_order"] = execution_order
            task.status = TaskStatus.COMPLETED.value
            db.commit()
            return {"status": "completed", "final_video_url": "https://example.com/final.mp4"}

    reset_calls = []
    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(queued_task_execution_host, "reset_event_bus", lambda: reset_calls.append(True))
    monkeypatch.setattr(
        "app.agents.orchestrator.OrchestratorAgent.create_default",
        classmethod(lambda cls: _FakeOrchestrator()),
    )

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        result = queued_task_execution_host.run_generation_in_host(
            GenerationMode.QUICK,
            task=task,
            input_data={"user_prompt": "test prompt", "voice_settings": {"voice_id": "narrator_a"}},
            db=db,
            route="orchestrator_mainline",
            execution_order=1,
        )
    finally:
        db.close()

    assert reset_calls == [True]
    assert result["route"] == "orchestrator_mainline"
    assert result["mode"] == "quick"
    assert result["status"] == "completed"
    assert orchestrator_calls["task_id"] == task_id
    assert orchestrator_calls["input_data"]["voice_settings"] == {"voice_id": "narrator_a"}


def test_run_generation_in_host_routes_project_mode_to_episode_orchestrator(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"project_id": "project-1", "user_prompt": "test prompt"},
    )
    orchestrator_calls = {}

    class _FakeEpisodeOrchestrator:
        async def execute(self, *, task, input_data, db, execution_order=1):
            orchestrator_calls["task_id"] = task.id
            orchestrator_calls["input_data"] = dict(input_data)
            orchestrator_calls["execution_order"] = execution_order
            return {"status": "completed", "final_video_url": "https://example.com/project.mp4"}

    reset_calls = []
    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(queued_task_execution_host, "reset_event_bus", lambda: reset_calls.append(True))
    monkeypatch.setattr(
        "app.agents.episode_orchestrator.EpisodeOrchestratorAgent.create_default",
        classmethod(lambda cls: _FakeEpisodeOrchestrator()),
    )

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        result = queued_task_execution_host.run_generation_in_host(
            GenerationMode.PROJECT,
            task=task,
            input_data={"project_id": "project-1", "user_prompt": "test prompt"},
            db=db,
            route="project_orchestrator_mainline",
            execution_order=2,
        )
    finally:
        db.close()

    assert reset_calls == [True]
    assert result["route"] == "project_orchestrator_mainline"
    assert result["mode"] == "project"
    assert result["status"] == "completed"
    assert orchestrator_calls["task_id"] == task_id
    assert orchestrator_calls["input_data"]["project_id"] == "project-1"
    assert orchestrator_calls["execution_order"] == 2


def test_sync_process_video_task_routes_silent_quick_payload_to_orchestrator_mainline(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test prompt"},
    )
    dispatch_calls = {}
    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(
        task_queue,
        "run_generation_in_host",
        lambda mode, *, task, input_data, db, route, execution_order=1: dispatch_calls.update(
            {
                "mode": mode.value,
                "task_id": task.id,
                "input_data": dict(input_data),
                "execution_order": execution_order,
                "route": route,
            }
        )
        or {
            "status": "completed",
            "result": {"status": "completed", "final_video_url": "https://example.com/final.mp4"},
            "route": route,
            "mode": mode.value,
        },
    )

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
    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(
        task_queue,
        "run_generation_in_host",
        lambda mode, *, task, input_data, db, route, execution_order=1: dispatch_calls.update(
            {"input_data": dict(input_data)}
        )
        or {
            "status": "completed",
            "result": {"status": "completed"},
            "route": route,
            "mode": mode.value,
        },
    )

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

    def _fake_host(mode, *, task, input_data, db, route, execution_order=1):
        dispatch_calls["called"] = True
        return {"status": "completed", "result": {"status": "completed"}, "route": route, "mode": mode.value}

    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(task_queue, "run_generation_in_host", _fake_host)

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


def test_sync_process_video_task_marks_runtime_failure_via_runtime_service(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test prompt"},
    )

    def _raise_host_error(mode, *, task, input_data, db, route, execution_order=1):
        raise RuntimeError("host failed")

    monkeypatch.setattr(task_queue, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(task_queue, "run_generation_in_host", _raise_host_error)

    result = task_queue.sync_process_video_task(task_id)

    assert result == {"error": "host failed"}

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        runtime_session = RuntimeSessionService.get_latest_session_for_task_sync(db, task_id)
        assert task.status == TaskStatus.FAILED.value
        assert task.error_message == "host failed"
        assert runtime_session is not None
        assert runtime_session.status == WorkflowSessionStatus.FAILED.value
        assert runtime_session.error_message == "host failed"
    finally:
        db.close()

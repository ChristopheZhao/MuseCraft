import asyncio
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.constants import GenerationMode
from app.core.database import Base
from app.models import Task, TaskStatus, TaskType, WorkflowSessionStatus
from app.services import execution_host_lease
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


def test_run_generation_in_host_exposes_execution_host_lease_context(monkeypatch, session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test prompt"},
    )
    seen = {}

    class _FakeOrchestrator:
        async def execute(self, *, task, input_data, db, execution_order=1):
            context = execution_host_lease.get_current_execution_host_lease_context()
            seen["has_context"] = context is not None
            seen["has_keepalive"] = bool(context and context.attempt_lease_keepalive is not None)
            return {"status": "completed"}

    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(queued_task_execution_host, "reset_event_bus", lambda: None)
    monkeypatch.setattr(
        "app.agents.orchestrator.OrchestratorAgent.create_default",
        classmethod(lambda cls: _FakeOrchestrator()),
    )

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        queued_task_execution_host.run_generation_in_host(
            GenerationMode.QUICK,
            task=task,
            input_data={"user_prompt": "test prompt"},
            db=db,
            route="orchestrator_mainline",
            execution_order=1,
        )
    finally:
        db.close()

    assert seen == {"has_context": True, "has_keepalive": True}
    assert execution_host_lease.get_current_execution_host_lease_context() is None


def test_attempt_lease_keepalive_controller_heartbeats_with_host_owned_session():
    events = []

    class _FakeDb:
        def close(self):
            events.append(("close",))

    fake_session = SimpleNamespace(id=77)

    def _session_factory():
        events.append(("open",))
        return _FakeDb()

    def _load_session(db, session_id):
        events.append(("load", session_id))
        return fake_session

    def _heartbeat_attempt(db, runtime_session, *, attempt_id, lease_token):
        events.append(("heartbeat", runtime_session.id, attempt_id, lease_token))

    controller = execution_host_lease.AttemptLeaseKeepaliveController(
        session_factory=_session_factory,
        load_session=_load_session,
        heartbeat_attempt=_heartbeat_attempt,
        interval_seconds=0.05,
    )

    try:
        controller.activate(runtime_session_id=77, attempt_id=11, lease_token="lease-11")
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if any(event[0] == "heartbeat" for event in events):
                break
            time.sleep(0.02)
    finally:
        controller.close()

    assert ("heartbeat", 77, 11, "lease-11") in events
    assert ("open",) in events
    assert ("load", 77) in events
    assert ("close",) in events


def test_attempt_lease_keepalive_controller_marks_unhealthy_on_heartbeat_error():
    published = []

    class _FakeDb:
        def close(self):
            return None

    fake_session = SimpleNamespace(id=77)

    def _session_factory():
        return _FakeDb()

    def _load_session(db, session_id):
        return fake_session

    def _heartbeat_attempt(db, runtime_session, *, attempt_id, lease_token):
        raise RuntimeError("db write failed")

    controller = execution_host_lease.AttemptLeaseKeepaliveController(
        session_factory=_session_factory,
        load_session=_load_session,
        heartbeat_attempt=_heartbeat_attempt,
        interval_seconds=0.05,
        publish_diagnostic=lambda **payload: published.append(payload),
    )

    try:
        controller.activate(runtime_session_id=77, attempt_id=11, lease_token="lease-11")
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if published:
                break
            time.sleep(0.02)

        with pytest.raises(execution_host_lease.ExecutionHostKeepaliveLostError) as excinfo:
            controller.assert_healthy()
    finally:
        controller.close()

    assert published
    diagnostic = published[0]["diagnostic"]
    assert diagnostic["reason_code"] == "heartbeat_error"
    assert excinfo.value.diagnostic["reason_code"] == "heartbeat_error"


def test_attempt_lease_keepalive_controller_publishes_diagnostic_when_validation_stops():
    events = []
    published = []

    class _FakeDb:
        def close(self):
            events.append(("close",))

    fake_session = SimpleNamespace(id=77)

    def _session_factory():
        events.append(("open",))
        return _FakeDb()

    def _load_session(db, session_id):
        events.append(("load", session_id))
        return fake_session

    def _heartbeat_attempt(db, runtime_session, *, attempt_id, lease_token):
        raise ValueError("lease expired")

    controller = execution_host_lease.AttemptLeaseKeepaliveController(
        session_factory=_session_factory,
        load_session=_load_session,
        heartbeat_attempt=_heartbeat_attempt,
        interval_seconds=0.05,
        publish_diagnostic=lambda **payload: published.append(payload),
    )

    try:
        controller.activate(runtime_session_id=77, attempt_id=11, lease_token="lease-11")
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if published:
                break
            time.sleep(0.02)
    finally:
        controller.close()

    assert published
    assert ("open",) in events
    assert ("load", 77) in events
    event = published[0]
    diagnostic = event["diagnostic"]
    assert event["runtime_session_id"] == 77
    assert event["attempt_id"] == 11
    assert diagnostic["code"] == "execution_host_keepalive"
    assert diagnostic["state"] == "stopped"
    assert diagnostic["reason_code"] == "heartbeat_validation_failed"
    assert diagnostic["message"] == "lease expired"


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

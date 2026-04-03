import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.database as core_database
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


def _build_threaded_sqlite_session_factory(tmp_path, name: str):
    engine = create_engine(
        f"sqlite:///{(tmp_path / name).as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


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


def test_run_generation_in_host_renews_leased_attempt_and_emits_lifecycle_receipts(monkeypatch, tmp_path):
    engine, session_factory = _build_threaded_sqlite_session_factory(
        tmp_path,
        "queued_host_keepalive.sqlite",
    )
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test prompt"},
    )
    probe = {}

    class _FakeOrchestrator:
        async def execute(self, *, task, input_data, db, execution_order=1):
            runtime_session = RuntimeSessionService.get_or_create_session_for_task_sync(
                db,
                task,
                mode="quick",
            )
            attempt = RuntimeSessionService.start_node_attempt_sync(
                db,
                runtime_session,
                node_key="video",
                task=task,
            )
            leased_attempt = RuntimeSessionService.grant_attempt_lease_sync(
                db,
                runtime_session,
                attempt_id=attempt.id,
                lease_owner="queued-host-test",
                lease_timeout_seconds=2,
            )
            activated = execution_host_lease.activate_current_attempt_keepalive(
                runtime_session_id=runtime_session.id,
                attempt_id=attempt.id,
                lease_token=str(leased_attempt.lease_token),
            )

            deadline = time.time() + 2.0
            advanced = False
            while time.time() < deadline:
                probe_db = session_factory()
                try:
                    fresh_attempt = RuntimeSessionService.get_attempt_by_id_sync(
                        probe_db,
                        runtime_session.id,
                        attempt.id,
                    )
                    if (
                        fresh_attempt is not None
                        and fresh_attempt.last_heartbeat_at is not None
                        and fresh_attempt.lease_expires_at is not None
                        and fresh_attempt.last_heartbeat_at > leased_attempt.last_heartbeat_at
                        and fresh_attempt.lease_expires_at > leased_attempt.lease_expires_at
                    ):
                        advanced = True
                        break
                finally:
                    probe_db.close()
                time.sleep(0.02)

            execution_host_lease.deactivate_current_attempt_keepalive(reason="test_done")
            probe.update(
                {
                    "activated": activated,
                    "runtime_session_id": runtime_session.id,
                    "attempt_id": attempt.id,
                    "initial_last_heartbeat_at": leased_attempt.last_heartbeat_at,
                    "initial_lease_expires_at": leased_attempt.lease_expires_at,
                    "advanced": advanced,
                }
            )
            return {"status": "completed"}

    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(queued_task_execution_host, "reset_event_bus", lambda: None)
    monkeypatch.setattr(queued_task_execution_host, "execution_host_lease_heartbeat_interval_seconds", lambda: 0.05)
    monkeypatch.setattr(core_database, "SessionLocal", session_factory)
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
            input_data={"user_prompt": "test prompt"},
            db=db,
            route="orchestrator_mainline",
            execution_order=1,
        )
    finally:
        db.close()

    verify_db = session_factory()
    try:
        refreshed_attempt = RuntimeSessionService.get_attempt_by_id_sync(
            verify_db,
            probe["runtime_session_id"],
            probe["attempt_id"],
        )
        node = RuntimeSessionService.get_node_by_key_sync(
            verify_db,
            probe["runtime_session_id"],
            "video",
        )
    finally:
        verify_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    assert result["status"] == "completed"
    assert probe["activated"] is True
    assert probe["advanced"] is True
    assert refreshed_attempt is not None
    assert refreshed_attempt.last_heartbeat_at > probe["initial_last_heartbeat_at"]
    assert refreshed_attempt.lease_expires_at > probe["initial_lease_expires_at"]

    receipt_codes = [
        item.get("code")
        for item in (getattr(node, "diagnostics", None) or [])
        if isinstance(item, dict)
    ]
    assert "execution_host_keepalive_activation_requested" in receipt_codes
    assert "execution_host_keepalive_heartbeat_begin" in receipt_codes
    assert "execution_host_keepalive_first_heartbeat_ack" in receipt_codes
    assert "execution_host_keepalive_deactivated" in receipt_codes


def test_run_generation_in_host_can_silently_expire_when_heartbeat_blocks(monkeypatch, tmp_path):
    engine, session_factory = _build_threaded_sqlite_session_factory(
        tmp_path,
        "queued_host_keepalive_blocked.sqlite",
    )
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test prompt"},
    )
    entered_heartbeat = threading.Event()
    release_heartbeat = threading.Event()
    original_heartbeat = RuntimeSessionService.heartbeat_attempt_lease_sync
    probe = {}

    def _blocked_heartbeat(db, runtime_session, *, attempt_id, lease_token, lease_timeout_seconds=None):
        entered_heartbeat.set()
        if not release_heartbeat.wait(timeout=5.0):
            raise RuntimeError("test heartbeat release timeout")
        return original_heartbeat(
            db,
            runtime_session,
            attempt_id=attempt_id,
            lease_token=lease_token,
            lease_timeout_seconds=lease_timeout_seconds,
        )

    class _FakeOrchestrator:
        async def execute(self, *, task, input_data, db, execution_order=1):
            runtime_session = RuntimeSessionService.get_or_create_session_for_task_sync(
                db,
                task,
                mode="quick",
            )
            attempt = RuntimeSessionService.start_node_attempt_sync(
                db,
                runtime_session,
                node_key="video",
                task=task,
            )
            leased_attempt = RuntimeSessionService.grant_attempt_lease_sync(
                db,
                runtime_session,
                attempt_id=attempt.id,
                lease_owner="queued-host-test",
                lease_timeout_seconds=1,
            )
            activated = execution_host_lease.activate_current_attempt_keepalive(
                runtime_session_id=runtime_session.id,
                attempt_id=attempt.id,
                lease_token=str(leased_attempt.lease_token),
            )
            assert entered_heartbeat.wait(timeout=1.0)
            time.sleep(1.2)

            mid_db = session_factory()
            try:
                mid_session = RuntimeSessionService.get_session_by_id_sync(
                    mid_db,
                    runtime_session.id,
                )
                mid_node = RuntimeSessionService.get_node_by_key_sync(
                    mid_db,
                    runtime_session.id,
                    "video",
                )
                expired = False
                try:
                    RuntimeSessionService.assert_attempt_lease_sync(
                        mid_db,
                        mid_session,
                        attempt_id=attempt.id,
                        lease_token=str(leased_attempt.lease_token),
                    )
                except ValueError as exc:
                    expired = "execution lease expired" in str(exc)

                try:
                    execution_host_lease.assert_current_execution_host_keepalive_healthy()
                    mid_unhealthy = False
                except execution_host_lease.ExecutionHostKeepaliveLostError:
                    mid_unhealthy = True

                probe.update(
                    {
                        "activated": activated,
                        "runtime_session_id": runtime_session.id,
                        "attempt_id": attempt.id,
                        "mid_expired": expired,
                        "mid_unhealthy": mid_unhealthy,
                        "mid_diagnostics": list(getattr(mid_node, "diagnostics", None) or []),
                    }
                )
            finally:
                mid_db.close()

            release_heartbeat.set()
            deadline = time.time() + 2.0
            late_unhealthy = False
            while time.time() < deadline:
                try:
                    execution_host_lease.assert_current_execution_host_keepalive_healthy()
                except execution_host_lease.ExecutionHostKeepaliveLostError:
                    late_unhealthy = True
                    break
                time.sleep(0.02)

            execution_host_lease.deactivate_current_attempt_keepalive(reason="test_done")
            probe["late_unhealthy"] = late_unhealthy
            return {"status": "completed"}

    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(queued_task_execution_host, "reset_event_bus", lambda: None)
    monkeypatch.setattr(queued_task_execution_host, "execution_host_lease_heartbeat_interval_seconds", lambda: 0.05)
    monkeypatch.setattr(core_database, "SessionLocal", session_factory)
    monkeypatch.setattr(
        RuntimeSessionService,
        "heartbeat_attempt_lease_sync",
        staticmethod(_blocked_heartbeat),
    )
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
            input_data={"user_prompt": "test prompt"},
            db=db,
            route="orchestrator_mainline",
            execution_order=1,
        )
    finally:
        db.close()

    verify_db = session_factory()
    try:
        node = RuntimeSessionService.get_node_by_key_sync(
            verify_db,
            probe["runtime_session_id"],
            "video",
        )
    finally:
        verify_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    keepalive_diagnostics = [
        item
        for item in (getattr(node, "diagnostics", None) or [])
        if isinstance(item, dict) and item.get("code") == "execution_host_keepalive"
    ]
    mid_keepalive_diagnostics = [
        item
        for item in (probe["mid_diagnostics"] or [])
        if isinstance(item, dict) and item.get("code") == "execution_host_keepalive"
    ]

    assert result["status"] == "completed"
    assert probe["activated"] is True
    assert probe["mid_expired"] is True
    assert probe["mid_unhealthy"] is False
    assert mid_keepalive_diagnostics == []
    assert probe["late_unhealthy"] is True
    assert len(keepalive_diagnostics) == 1
    assert keepalive_diagnostics[0]["reason_code"] == "heartbeat_validation_failed"


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


def test_attempt_lease_keepalive_controller_publishes_lifecycle_receipts():
    published = []
    heartbeat_state = {
        "count": 0,
        "started_at": datetime(2026, 4, 3, 2, 20, tzinfo=timezone.utc),
    }

    class _FakeDb:
        def close(self):
            return None

    fake_session = SimpleNamespace(id=77)

    def _session_factory():
        return _FakeDb()

    def _load_session(db, session_id):
        return fake_session

    def _heartbeat_attempt(db, runtime_session, *, attempt_id, lease_token):
        heartbeat_state["count"] += 1
        heartbeat_at = heartbeat_state["started_at"] + timedelta(seconds=heartbeat_state["count"])
        return SimpleNamespace(
            last_heartbeat_at=heartbeat_at,
            lease_expires_at=heartbeat_at + timedelta(seconds=60),
        )

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
        required_codes = {
            "execution_host_keepalive_activation_requested",
            "execution_host_keepalive_heartbeat_begin",
            "execution_host_keepalive_first_heartbeat_ack",
            "execution_host_keepalive_heartbeat_end",
        }
        while time.time() < deadline:
            seen_codes = {item["diagnostic"]["code"] for item in published}
            if required_codes.issubset(seen_codes):
                break
            time.sleep(0.02)
        controller.deactivate(reason="test_scope_exit")
    finally:
        controller.close()

    diagnostics_by_code = {
        item["diagnostic"]["code"]: item["diagnostic"]
        for item in published
    }

    assert diagnostics_by_code["execution_host_keepalive_activation_requested"]["attempt_id"] == 11
    assert diagnostics_by_code["execution_host_keepalive_first_heartbeat_ack"]["last_heartbeat_at"] is not None
    assert diagnostics_by_code["execution_host_keepalive_heartbeat_end"]["lease_expires_at"] is not None
    assert diagnostics_by_code["execution_host_keepalive_deactivated"]["reason_code"] == "test_scope_exit"


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

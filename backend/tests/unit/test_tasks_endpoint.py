import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from app.api.v1.endpoints import tasks as tasks_endpoint


def test_schedule_task_execution_queues_task_by_default(monkeypatch):
    background_tasks = BackgroundTasks()
    queue_events = {}

    class _FakeQueueService:
        def __init__(self):
            queue_events["created"] = queue_events.get("created", 0) + 1

        async def queue_task(self, task_id):
            queue_events["task_id"] = task_id

    class _ForbiddenThread:
        def __init__(self, *args, **kwargs):
            raise AssertionError("in-process runner should stay disabled by default")

    monkeypatch.setattr(tasks_endpoint.settings, "TASKS_API_ENABLE_IN_PROCESS_RUNNER", False)
    monkeypatch.setattr(tasks_endpoint, "TaskQueueService", _FakeQueueService)
    monkeypatch.setattr(tasks_endpoint.threading, "Thread", _ForbiddenThread)

    tasks_endpoint._schedule_task_execution(background_tasks, 42)

    assert queue_events["created"] == 1
    assert len(background_tasks.tasks) == 1
    scheduled = background_tasks.tasks[0]
    assert scheduled.args == (42,)


def test_schedule_task_execution_uses_in_process_runner_only_when_enabled(monkeypatch):
    background_tasks = BackgroundTasks()
    thread_events = {}

    def _fake_sync_process_video_task(task_id):
        thread_events["task_id"] = task_id
        return {"status": "completed"}

    class _ForbiddenQueueService:
        def __init__(self):
            raise AssertionError("queue service should not be used when in-process runner is explicitly enabled")

    class _FakeThread:
        def __init__(self, *, target, daemon):
            thread_events["daemon"] = daemon
            self._target = target

        def start(self):
            thread_events["started"] = True
            self._target()

    monkeypatch.setattr(tasks_endpoint.settings, "TASKS_API_ENABLE_IN_PROCESS_RUNNER", True)
    monkeypatch.setattr(tasks_endpoint, "TaskQueueService", _ForbiddenQueueService)
    monkeypatch.setattr(tasks_endpoint.threading, "Thread", _FakeThread)
    monkeypatch.setattr("app.services.task_queue.sync_process_video_task", _fake_sync_process_video_task)

    tasks_endpoint._schedule_task_execution(background_tasks, 7)

    assert len(background_tasks.tasks) == 0
    assert thread_events["daemon"] is True
    assert thread_events["started"] is True
    assert thread_events["task_id"] == 7


def test_task_runtime_is_the_authoritative_projection(monkeypatch):
    runtime_view = {
        "session_id": 11,
        "status": "waiting_gate",
        "current_node_key": "script",
        "nodes": [{"node_key": "script", "status": "pending_gate"}],
    }
    task = SimpleNamespace(
        id=7,
        task_id="task-7",
        status="in_progress",
        progress_percentage=35,
        current_step="Waiting for script approval",
        error_message=None,
        total_steps=5,
    )

    class _FakeQueryResult:
        def scalar_one_or_none(self):
            return task

    class _FakeDb:
        async def execute(self, query):
            return _FakeQueryResult()

    async def _fake_runtime_view(db, task_obj):
        assert task_obj is task
        return runtime_view

    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "build_runtime_view_for_task", _fake_runtime_view)
    runtime_payload = asyncio.run(tasks_endpoint.get_task_runtime("task-7", db=_FakeDb()))

    assert runtime_payload == runtime_view


def test_task_runtime_returns_404_when_runtime_session_is_absent(monkeypatch):
    task = SimpleNamespace(
        id=8,
        task_id="task-8",
    )

    class _FakeQueryResult:
        def scalar_one_or_none(self):
            return task

    class _FakeDb:
        async def execute(self, query):
            return _FakeQueryResult()

    async def _fake_runtime_view(db, task_obj):
        assert task_obj is task
        return None

    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "build_runtime_view_for_task", _fake_runtime_view)

    with pytest.raises(tasks_endpoint.HTTPException) as exc_info:
        asyncio.run(tasks_endpoint.get_task_runtime("task-8", db=_FakeDb()))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Runtime session not found"


def test_get_current_quick_run_returns_existing_task_and_runtime(monkeypatch):
    now = datetime.now(timezone.utc)
    task = SimpleNamespace(
        id=12,
        task_id="task-12",
        title="Video: demo...",
        description="demo prompt",
        status="waiting_gate",
        session_id="quick-session-1",
        input_parameters={"user_prompt": "Demo\n\nRun"},
        created_at=now,
        updated_at=now,
        error_message=None,
    )
    runtime_view = {"session_id": 88, "status": "waiting_gate", "current_node_key": "script"}

    async def _fake_find(db, session_id):
        assert session_id == "quick-session-1"
        return task, runtime_view

    monkeypatch.setattr(tasks_endpoint, "_find_current_quick_run_for_session", _fake_find)

    payload = asyncio.run(tasks_endpoint.get_current_quick_run("quick-session-1", db=object()))

    assert payload.task.task_id == "task-12"
    assert payload.task.session_id == "quick-session-1"
    assert payload.runtime == runtime_view


def test_get_current_quick_run_suppresses_task_without_runtime_truth(monkeypatch):
    now = datetime.now(timezone.utc)
    task = SimpleNamespace(
        id=13,
        task_id="task-13",
        title="Video: missing runtime...",
        description="demo prompt",
        status="in_progress",
        session_id="quick-session-2",
        input_parameters={"user_prompt": "Demo\n\nRun"},
        created_at=now,
        updated_at=now,
        error_message=None,
    )

    async def _fake_find(db, session_id):
        assert session_id == "quick-session-2"
        return task, None

    monkeypatch.setattr(tasks_endpoint, "_find_current_quick_run_for_session", _fake_find)

    payload = asyncio.run(tasks_endpoint.get_current_quick_run("quick-session-2", db=object()))

    assert payload is None


def test_get_current_quick_run_suppresses_terminal_runtime_after_reconciliation(monkeypatch):
    now = datetime.now(timezone.utc)
    task = SimpleNamespace(
        id=30,
        task_id="task-30",
        title="Video: stale runtime...",
        description="demo prompt",
        status="in_progress",
        session_id="quick-session-30",
        input_parameters={"user_prompt": "Demo\n\nRun"},
        created_at=now,
        updated_at=now,
        error_message=None,
    )

    async def _fake_find(db, session_id):
        assert session_id == "quick-session-30"
        return task, {
            "session_id": 90,
            "status": "failed",
            "error_message": "Stale quick runtime detected",
            "resume_control": None,
        }

    monkeypatch.setattr(tasks_endpoint, "_find_current_quick_run_for_session", _fake_find)

    payload = asyncio.run(tasks_endpoint.get_current_quick_run("quick-session-30", db=object()))

    assert payload is None


def test_find_current_quick_run_surfaces_projection_integrity_error(monkeypatch):
    now = datetime.now(timezone.utc)
    task = SimpleNamespace(
        id=14,
        task_id="task-14",
        title="Video: broken runtime...",
        description="demo prompt",
        status="in_progress",
        session_id="quick-session-3",
        input_parameters={"user_prompt": "Demo\n\nRun"},
        created_at=now,
        updated_at=now,
        error_message=None,
    )

    class _FakeScalarResult:
        def all(self):
            return [task]

    class _FakeQueryResult:
        def scalars(self):
            return _FakeScalarResult()

    class _FakeDb:
        async def execute(self, query):
            return _FakeQueryResult()

    async def _broken_runtime_view(db, task_obj):
        assert task_obj is task
        raise ValueError("Workflow session 93 missing current attempt anchor for continuation")

    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "build_runtime_view_for_task", _broken_runtime_view)

    with pytest.raises(ValueError, match="missing current attempt anchor"):
        asyncio.run(tasks_endpoint._find_current_quick_run_for_session(_FakeDb(), "quick-session-3"))


def test_get_current_quick_run_surfaces_selector_runtime_integrity_error(monkeypatch):
    async def _fake_find(db, session_id):
        assert session_id == "quick-session-3"
        raise ValueError("Workflow session 93 missing current attempt anchor for continuation")

    monkeypatch.setattr(tasks_endpoint, "_find_current_quick_run_for_session", _fake_find)

    with pytest.raises(tasks_endpoint.HTTPException) as exc_info:
        asyncio.run(tasks_endpoint.get_current_quick_run("quick-session-3", db=object()))

    assert exc_info.value.status_code == 500
    assert "missing current attempt anchor" in str(exc_info.value.detail)


def test_create_task_replaces_existing_unfinished_quick_run(monkeypatch):
    existing_task = SimpleNamespace(id=7, task_id="task-old")
    created_runtime_session = SimpleNamespace(id=55)
    queue_calls = {}

    class _FakeDb:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            return None

        async def refresh(self, obj):
            now = datetime.now(timezone.utc)
            if getattr(obj, "id", None) is None:
                obj.id = 101
            if not getattr(obj, "task_id", None):
                obj.task_id = "task-new"
            if getattr(obj, "created_at", None) is None:
                obj.created_at = now
            obj.updated_at = now
            if getattr(obj, "progress_percentage", None) is None:
                obj.progress_percentage = 0
            if not hasattr(obj, "current_step"):
                obj.current_step = None
            if not hasattr(obj, "error_message"):
                obj.error_message = None

    async def _fake_find(db, session_id):
        assert session_id == "quick-session-2"
        return existing_task, {"session_id": 23, "status": "running"}

    async def _fake_cancel(db, task, *, reason):
        queue_calls["cancelled_task_id"] = task.id
        queue_calls["cancel_reason"] = reason

    async def _fake_create_session(db, task, mode="quick"):
        queue_calls["created_task_id"] = task.id
        queue_calls["created_task_session_id"] = task.session_id
        queue_calls["created_mode"] = mode
        return created_runtime_session

    def _fake_schedule(background_tasks, task_db_id):
        queue_calls["scheduled_task_id"] = task_db_id

    monkeypatch.setattr(tasks_endpoint, "_find_current_quick_run_for_session", _fake_find)
    monkeypatch.setattr(tasks_endpoint, "_cancel_task_for_replacement", _fake_cancel)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "create_session_for_task", _fake_create_session)
    monkeypatch.setattr(tasks_endpoint, "_schedule_task_execution", _fake_schedule)

    request = tasks_endpoint.TaskCreateRequest(
        user_prompt="Demo\n\nCreate a rerun",
        duration=30,
        resolution="720p",
        aspect_ratio="16:9",
        session_id="quick-session-2",
    )

    response = asyncio.run(
        tasks_endpoint.create_task(
            request=request,
            background_tasks=BackgroundTasks(),
            db=_FakeDb(),
        )
    )

    assert queue_calls["cancelled_task_id"] == 7
    assert queue_calls["cancel_reason"] == "superseded_by_new_run"
    assert queue_calls["created_mode"] == "quick"
    assert queue_calls["created_task_session_id"] == "quick-session-2"
    assert queue_calls["scheduled_task_id"] == 101
    assert response.task_id == "task-new"


def test_resume_task_runtime_marks_session_resuming_and_requeues(monkeypatch):
    task = SimpleNamespace(id=21, task_id="task-21")
    runtime_session = SimpleNamespace(id=91, mode="quick")
    runtime_view = {
        "session_id": 91,
        "status": "resuming",
        "resume_control": {
            "state": "view_only_running",
            "can_resume": False,
            "reason_code": "resume_scheduled",
        },
    }
    events = {}

    class _FakeQueryResult:
        def scalar_one_or_none(self):
            return task

    class _FakeDb:
        async def execute(self, query):
            return _FakeQueryResult()

        async def run_sync(self, fn):
            return fn(self)

        async def refresh(self, obj):
            events["refreshed"] = obj

        def query(self, model):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return task

    async def _fake_get_latest_session(db, task_db_id):
        assert task_db_id == 21
        return runtime_session

    def _fake_get_latest_session_sync(sync_db, task_db_id):
        assert task_db_id == 21
        return runtime_session

    def _fake_get_resume_control_sync(sync_db, task_obj, session_obj):
        assert task_obj is task
        assert session_obj is runtime_session
        return {
            "state": "resume_available",
            "can_resume": True,
            "reason_code": "checkpoint_available",
        }

    def _fake_mark_session_resuming_sync(sync_db, session_obj, *, task=None):
        events["marked_session"] = session_obj
        events["marked_task"] = task
        return session_obj

    def _fake_load_active_continuation_sync(
        sync_db,
        session_obj,
        *,
        expected_anchor_type,
        require_decision_id,
        require_resuming,
    ):
        events["loaded_session"] = session_obj
        events["loaded_anchor_type"] = expected_anchor_type
        events["loaded_require_decision_id"] = require_decision_id
        events["loaded_require_resuming"] = require_resuming
        return {
            "anchor_type": "runtime_checkpoint",
            "node_key": "image",
            "attempt_id": 17,
            "decision_id": None,
        }

    def _fake_schedule(background_tasks, task_db_id):
        events["scheduled_task_id"] = task_db_id

    async def _fake_build_runtime_view(db, task_obj):
        assert task_obj is task
        return runtime_view

    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "get_latest_session_for_task", _fake_get_latest_session)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "get_latest_session_for_task_sync", _fake_get_latest_session_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "get_resume_control_sync", _fake_get_resume_control_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "load_active_continuation_sync", _fake_load_active_continuation_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "mark_session_resuming_sync", _fake_mark_session_resuming_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "build_runtime_view_for_task", _fake_build_runtime_view)
    monkeypatch.setattr(tasks_endpoint, "_schedule_task_execution", _fake_schedule)

    response = asyncio.run(
        tasks_endpoint.resume_task_runtime(
            "task-21",
            background_tasks=BackgroundTasks(),
            db=_FakeDb(),
        )
    )

    assert events["marked_session"] is runtime_session
    assert events["marked_task"] is task
    assert events["loaded_session"] is runtime_session
    assert events["loaded_anchor_type"] == "runtime_checkpoint"
    assert events["loaded_require_decision_id"] is False
    assert events["loaded_require_resuming"] is False
    assert events["scheduled_task_id"] == 21
    assert events["refreshed"] is task
    assert response.message == "Runtime resume accepted"
    assert response.task_id == "task-21"
    assert response.runtime == runtime_view


def test_resume_task_runtime_rejects_when_resume_control_is_not_available(monkeypatch):
    task = SimpleNamespace(id=22, task_id="task-22")
    runtime_session = SimpleNamespace(id=92, mode="quick")
    events = {"marked": 0, "scheduled": 0}

    class _FakeQueryResult:
        def scalar_one_or_none(self):
            return task

    class _FakeDb:
        async def execute(self, query):
            return _FakeQueryResult()

        async def run_sync(self, fn):
            return fn(self)

        async def refresh(self, obj):
            raise AssertionError("refresh should not run when resume is rejected")

        def query(self, model):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return task

    async def _fake_get_latest_session(db, task_db_id):
        assert task_db_id == 22
        return runtime_session

    def _fake_get_latest_session_sync(sync_db, task_db_id):
        assert task_db_id == 22
        return runtime_session

    def _fake_get_resume_control_sync(sync_db, task_obj, session_obj):
        assert task_obj is task
        assert session_obj is runtime_session
        return {
            "state": "view_only_running",
            "can_resume": False,
            "reason_code": "active_execution_lease",
        }

    def _forbidden_mark_session_resuming_sync(sync_db, session_obj, *, task=None):
        events["marked"] += 1
        raise AssertionError("resume should not mutate runtime state when not resumable")

    def _forbidden_load_active_continuation_sync(
        sync_db,
        session_obj,
        *,
        expected_anchor_type,
        require_decision_id,
        require_resuming,
    ):
        raise AssertionError("resume should not load continuation when resume_control rejects it")

    def _forbidden_schedule(background_tasks, task_db_id):
        events["scheduled"] += 1
        raise AssertionError("resume should not queue dispatch when not resumable")

    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "get_latest_session_for_task", _fake_get_latest_session)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "get_latest_session_for_task_sync", _fake_get_latest_session_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "get_resume_control_sync", _fake_get_resume_control_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "load_active_continuation_sync", _forbidden_load_active_continuation_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "mark_session_resuming_sync", _forbidden_mark_session_resuming_sync)
    monkeypatch.setattr(tasks_endpoint, "_schedule_task_execution", _forbidden_schedule)

    with pytest.raises(tasks_endpoint.HTTPException) as exc_info:
        asyncio.run(
            tasks_endpoint.resume_task_runtime(
                "task-22",
                background_tasks=BackgroundTasks(),
                db=_FakeDb(),
            )
        )

    assert exc_info.value.status_code == 409
    assert "state=view_only_running" in str(exc_info.value.detail)


def test_resume_task_runtime_rejects_when_checkpoint_validation_fails(monkeypatch):
    task = SimpleNamespace(id=23, task_id="task-23")
    runtime_session = SimpleNamespace(id=93, mode="quick")
    events = {"marked": 0, "scheduled": 0}

    class _FakeQueryResult:
        def scalar_one_or_none(self):
            return task

    class _FakeDb:
        async def execute(self, query):
            return _FakeQueryResult()

        async def run_sync(self, fn):
            return fn(self)

        async def refresh(self, obj):
            raise AssertionError("refresh should not run when checkpoint load fails")

        def query(self, model):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return task

    async def _fake_get_latest_session(db, task_db_id):
        assert task_db_id == 23
        return runtime_session

    def _fake_get_latest_session_sync(sync_db, task_db_id):
        assert task_db_id == 23
        return runtime_session

    def _fake_get_resume_control_sync(sync_db, task_obj, session_obj):
        return {
            "state": "resume_available",
            "can_resume": True,
            "reason_code": "checkpoint_available",
        }

    def _failing_load_active_continuation_sync(
        sync_db,
        session_obj,
        *,
        expected_anchor_type,
        require_decision_id,
        require_resuming,
    ):
        raise ValueError("Workflow session 93 missing current attempt anchor for continuation")

    def _forbidden_mark_session_resuming_sync(sync_db, session_obj, *, task=None):
        events["marked"] += 1
        raise AssertionError("resume should not mutate runtime state when checkpoint validation fails")

    def _forbidden_schedule(background_tasks, task_db_id):
        events["scheduled"] += 1
        raise AssertionError("resume should not queue dispatch when checkpoint validation fails")

    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "get_latest_session_for_task", _fake_get_latest_session)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "get_latest_session_for_task_sync", _fake_get_latest_session_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "get_resume_control_sync", _fake_get_resume_control_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "load_active_continuation_sync", _failing_load_active_continuation_sync)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "mark_session_resuming_sync", _forbidden_mark_session_resuming_sync)
    monkeypatch.setattr(tasks_endpoint, "_schedule_task_execution", _forbidden_schedule)

    with pytest.raises(tasks_endpoint.HTTPException) as exc_info:
        asyncio.run(
            tasks_endpoint.resume_task_runtime(
                "task-23",
                background_tasks=BackgroundTasks(),
                db=_FakeDb(),
            )
    )

    assert exc_info.value.status_code == 409
    assert "missing current attempt anchor" in str(exc_info.value.detail)
    assert events == {"marked": 0, "scheduled": 0}

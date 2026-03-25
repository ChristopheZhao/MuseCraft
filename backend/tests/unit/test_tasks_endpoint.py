import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

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


def test_task_status_returns_coarse_projection_and_runtime_stays_runtime_sot(monkeypatch):
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

    status_payload = asyncio.run(tasks_endpoint.get_task_status("task-7", db=_FakeDb()))
    async def _fake_runtime_view(db, task_obj):
        assert task_obj is task
        return runtime_view

    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "build_runtime_view_for_task", _fake_runtime_view)
    runtime_payload = asyncio.run(tasks_endpoint.get_task_runtime("task-7", db=_FakeDb()))

    assert status_payload["task_id"] == "task-7"
    assert status_payload["status"] == "in_progress"
    assert status_payload["projection_role"] == "compatibility_coarse_task_status"
    assert status_payload["runtime_authoritative"] is False
    assert "workflow_status" not in status_payload
    assert runtime_payload == runtime_view


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
        return task, SimpleNamespace(id=88, status="waiting_gate", mode="quick")

    async def _fake_runtime_view(db, task_obj):
        assert task_obj is task
        return runtime_view

    monkeypatch.setattr(tasks_endpoint, "_find_unfinished_quick_task_for_session", _fake_find)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "build_runtime_view_for_task", _fake_runtime_view)

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

    async def _fake_runtime_view(db, task_obj):
        assert task_obj is task
        return None

    monkeypatch.setattr(tasks_endpoint, "_find_unfinished_quick_task_for_session", _fake_find)
    monkeypatch.setattr(tasks_endpoint.RuntimeSessionService, "build_runtime_view_for_task", _fake_runtime_view)

    payload = asyncio.run(tasks_endpoint.get_current_quick_run("quick-session-2", db=object()))

    assert payload is None


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
        return existing_task, SimpleNamespace(id=23, mode="quick", status="running")

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

    monkeypatch.setattr(tasks_endpoint, "_find_unfinished_quick_task_for_session", _fake_find)
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

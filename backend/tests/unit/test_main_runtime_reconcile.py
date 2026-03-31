import asyncio

from app import main as main_module
from app.core import database as database_module
from app.services.runtime_session_service import RuntimeSessionService


def test_run_quick_runtime_reconcile_once_uses_control_plane_service(monkeypatch):
    events = {}

    class _FakeDb:
        def close(self):
            events["closed"] = True

    fake_db = _FakeDb()

    def _fake_session_local():
        events["opened"] = True
        return fake_db

    def _fake_reconcile(db, *, limit):
        events["db"] = db
        events["limit"] = limit
        return {"inspected": 2, "failed": 1, "skipped": 1}

    monkeypatch.setattr(database_module, "SessionLocal", _fake_session_local)
    monkeypatch.setattr(
        RuntimeSessionService,
        "reconcile_irrecoverable_quick_runtimes_sync",
        staticmethod(_fake_reconcile),
    )
    monkeypatch.setattr(main_module.settings, "QUICK_RUNTIME_RECONCILER_BATCH_LIMIT", 25)

    summary = main_module.run_quick_runtime_reconcile_once()

    assert summary == {"inspected": 2, "failed": 1, "skipped": 1}
    assert events["opened"] is True
    assert events["db"] is fake_db
    assert events["limit"] == 25
    assert events["closed"] is True


def test_lifespan_does_not_schedule_runtime_reconcile_loop_even_when_flag_enabled(monkeypatch):
    scheduled = []

    class _FakeTask:
        def __init__(self, name):
            self.name = name
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

        def __await__(self):
            async def _done():
                return None

            return _done().__await__()

    async def fake_cleanup():
        return None

    async def fake_runtime_reconcile():
        return None

    def _fake_create_task(coro):
        scheduled.append(coro.cr_code.co_name)
        coro.close()
        return _FakeTask(coro.cr_code.co_name)

    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr("app.events.provider.get_event_bus", lambda: object())
    monkeypatch.setattr("app.services.event_handlers.handle_persistence_event", lambda event: None)
    monkeypatch.setattr(main_module, "setup_event_listeners", lambda **kwargs: object())
    monkeypatch.setattr(main_module.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "periodic_websocket_cleanup", fake_cleanup)
    monkeypatch.setattr(main_module, "periodic_runtime_reconcile", fake_runtime_reconcile)
    monkeypatch.setattr(main_module.asyncio, "create_task", _fake_create_task)
    monkeypatch.setattr(main_module.settings, "QUICK_RUNTIME_RECONCILER_ENABLED", True)

    async def _run_lifespan():
        async with main_module.lifespan(main_module.app):
            return None

    asyncio.run(_run_lifespan())

    assert scheduled == ["fake_cleanup"]

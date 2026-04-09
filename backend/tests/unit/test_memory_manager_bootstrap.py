import asyncio
import logging

from app.agents.memory.long_term.manager import LongTermMemoryManager


def test_long_term_memory_manager_skips_loop_probe_when_background_tasks_disabled(monkeypatch):
    loop_probe_calls = []

    def _unexpected_probe():
        loop_probe_calls.append("called")
        raise AssertionError("get_running_loop should not be called when background tasks are disabled")

    monkeypatch.setattr(asyncio, "get_running_loop", _unexpected_probe)

    manager = LongTermMemoryManager(
        stores={},
        retrievers={},
        config={"enable_consolidation": False, "enable_cleanup": False},
    )

    assert manager._consolidation_task is None
    assert manager._cleanup_task is None
    assert loop_probe_calls == []


def test_long_term_memory_manager_degrades_when_logger_fails_in_no_loop_path(monkeypatch):
    class _BrokenLogger:
        def info(self, _message, *args, **kwargs):
            raise OSError(5, "Input/output error")

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError("no running event loop")))
    monkeypatch.setattr(logging, "getLogger", lambda _name: _BrokenLogger())

    manager = LongTermMemoryManager(
        stores={},
        retrievers={},
        config={"enable_consolidation": True, "enable_cleanup": True},
    )

    assert manager._consolidation_task is None
    assert manager._cleanup_task is None

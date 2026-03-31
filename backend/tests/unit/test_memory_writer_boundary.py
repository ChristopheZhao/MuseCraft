import importlib
import sys
from enum import Enum
from types import ModuleType, SimpleNamespace

import pytest

from app.models.task import TaskType


class _DummyMonitoringService:
    async def record_metric(self, *args, **kwargs):
        return None


class _DummyMetricType(str, Enum):
    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"
    TIMER = "timer"


class _FakeLongTermService:
    def __init__(self):
        self.calls = []

    async def store_memory(self, **kwargs):
        self.calls.append(kwargs)
        return f"mem-{len(self.calls)}"


@pytest.fixture
def memory_writer_module(monkeypatch):
    stub_module = ModuleType("app.services.monitoring_service")
    stub_module.MonitoringService = _DummyMonitoringService
    stub_module.MetricType = _DummyMetricType
    monkeypatch.setitem(sys.modules, "app.services.monitoring_service", stub_module)
    sys.modules.pop("app.services.memory_writer", None)
    module = importlib.import_module("app.services.memory_writer")
    return importlib.reload(module)


@pytest.mark.asyncio
async def test_memory_writer_ignores_runtime_and_planning_fields(memory_writer_module):
    long_term = _FakeLongTermService()
    writer = memory_writer_module.MemoryWriter(
        SimpleNamespace(
            global_service=object(),
            long_term=long_term,
        )
    )

    result = await writer.write(
        TaskType.VIDEO_GENERATION,
        workflow_id="wf-boundary-ignore",
        scene_number=3,
        output={
            "status": "running",
            "resume_control": {"state": "resume_available"},
            "task_specs": {"video_generator": {"priority": "high"}},
            "queue_handle": "celery-task-123",
            "metadata": {},
        },
    )

    assert result is None
    assert long_term.calls == []


@pytest.mark.asyncio
async def test_memory_writer_persists_only_generation_metadata_for_media_outputs(memory_writer_module):
    long_term = _FakeLongTermService()
    writer = memory_writer_module.MemoryWriter(
        SimpleNamespace(
            global_service=object(),
            long_term=long_term,
        )
    )

    result = await writer.write(
        TaskType.VIDEO_GENERATION,
        workflow_id="wf-boundary-meta",
        scene_number=7,
        output={
            "metadata": {"provider": "seedance", "duration": 10},
            "status": "running",
            "task_specs": {"video_generator": {"priority": "high"}},
        },
    )

    assert result == "mem-1"
    assert len(long_term.calls) == 1
    persisted = long_term.calls[0]
    assert persisted["content"] == {
        "agent_role": "Generation Metadata",
        "workflow_id": "wf-boundary-meta",
        "scene_number": 7,
        "generation_metadata": {"provider": "seedance", "duration": 10},
    }
    assert persisted["metadata"]["content_type"] == "generation_metadata"

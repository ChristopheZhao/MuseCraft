from types import SimpleNamespace

import pytest

from app.domain import TaskType
from app.services.memory_writer import (
    MemoryWriteError,
    MemoryWriter,
    MemoryWriteReason,
    MemoryWriteStatus,
)


class _FakeLongTermService:
    def __init__(self, *, error: Exception | None = None):
        self.calls = []
        self.error = error

    async def store_memory(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return f"mem-{len(self.calls)}"


def _writer(long_term, *, failure_policy="degrade"):
    return MemoryWriter(
        SimpleNamespace(long_term=long_term),
        failure_policy=failure_policy,
    )


@pytest.mark.asyncio
async def test_memory_writer_returns_typed_skip_for_unrecognized_runtime_fields():
    long_term = _FakeLongTermService()

    receipt = await _writer(long_term).write(
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

    assert receipt.status is MemoryWriteStatus.SKIPPED
    assert receipt.reason_code is MemoryWriteReason.NO_MATCHING_FACT
    assert receipt.memory_id is None
    assert long_term.calls == []


@pytest.mark.asyncio
async def test_memory_writer_returns_typed_receipt_for_generation_metadata():
    long_term = _FakeLongTermService()

    receipt = await _writer(long_term).write(
        TaskType.VIDEO_GENERATION,
        workflow_id="wf-boundary-meta",
        scene_number=7,
        output={
            "metadata": {"provider": "seedance", "duration": 10},
            "status": "running",
            "task_specs": {"video_generator": {"priority": "high"}},
        },
    )

    assert receipt.status is MemoryWriteStatus.WRITTEN
    assert receipt.reason_code is MemoryWriteReason.STORED
    assert receipt.memory_id == "mem-1"
    assert len(long_term.calls) == 1
    persisted = long_term.calls[0]
    assert persisted["content"] == {
        "agent_role": "Generation Metadata",
        "workflow_id": "wf-boundary-meta",
        "scene_number": 7,
        "generation_metadata": {"provider": "seedance", "duration": 10},
    }
    assert persisted["metadata"]["content_type"] == "generation_metadata"


@pytest.mark.asyncio
async def test_optional_memory_failure_degrades_with_typed_reason():
    receipt = await _writer(_FakeLongTermService(error=RuntimeError("memory unavailable"))).write(
        TaskType.VIDEO_GENERATION,
        workflow_id="wf-memory-degrade",
        output={"metadata": {"provider": "configured-provider"}},
    )

    assert receipt.status is MemoryWriteStatus.DEGRADED
    assert receipt.reason_code is MemoryWriteReason.OPTIONAL_WRITE_FAILED
    assert "memory unavailable" in str(receipt.diagnostic)


@pytest.mark.asyncio
async def test_required_memory_failure_raises_typed_error():
    with pytest.raises(MemoryWriteError) as caught:
        await _writer(
            _FakeLongTermService(error=RuntimeError("memory unavailable")),
            failure_policy="fail",
        ).write(
            TaskType.VIDEO_GENERATION,
            workflow_id="wf-memory-fail",
            output={"metadata": {"provider": "configured-provider"}},
        )

    assert caught.value.reason_code is MemoryWriteReason.OPTIONAL_WRITE_FAILED

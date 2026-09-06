"""Typed, storage-agnostic writeback for optional Agent memory facts."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Protocol

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

from ..agents.memory.long_term.stores import MemoryImportance, MemoryType
from ..domain import TaskType
from .memory_provider import MemoryServices

_logger = logging.getLogger("memory_writer")


class MemoryWriteStatus(str, Enum):
    WRITTEN = "written"
    SKIPPED = "skipped"
    DEGRADED = "degraded"


class MemoryWriteReason(str, Enum):
    STORED = "memory_stored"
    DISABLED = "memory_write_disabled"
    NO_MATCHING_FACT = "no_matching_memory_fact"
    OPTIONAL_WRITE_FAILED = "optional_memory_write_failed"


@dataclass(frozen=True, slots=True)
class MemoryWriteReceipt:
    status: MemoryWriteStatus
    reason_code: MemoryWriteReason
    memory_id: Optional[str] = None
    diagnostic: Optional[str] = None


class MemoryWriteError(RuntimeError):
    def __init__(self, *, reason_code: MemoryWriteReason, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


class MemoryMetricPort(Protocol):
    async def record_metric(
        self,
        name: str,
        value: int,
        metric_type: str,
        *,
        labels: Dict[str, str],
    ) -> None:
        ...


class NoOpMemoryMetricPort:
    async def record_metric(
        self,
        name: str,
        value: int,
        metric_type: str,
        *,
        labels: Dict[str, str],
    ) -> None:
        return None


def _load_yaml(path: str) -> Optional[Dict[str, Any]]:
    if not yaml:
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except FileNotFoundError:
        return None
    except Exception as exc:
        _logger.warning("Memory writer policy load failed: path=%s error=%s", path, exc)
        return None


class MemoryWriter:
    def __init__(
        self,
        memory_services: MemoryServices,
        *,
        metric_port: MemoryMetricPort | None = None,
        failure_policy: str | None = None,
    ) -> None:
        if memory_services is None:
            raise ValueError("memory_services is required for MemoryWriter")
        self._long_term = memory_services.long_term
        if self._long_term is None:
            raise ValueError("long_term memory service is required for MemoryWriter")
        self._metrics = metric_port or NoOpMemoryMetricPort()
        policy = (
            str(failure_policy or os.getenv("MEMORY_WRITE_FAILURE_POLICY", "degrade"))
            .strip()
            .lower()
        )
        if policy not in {"degrade", "fail"}:
            raise ValueError("MEMORY_WRITE_FAILURE_POLICY must be 'degrade' or 'fail'")
        self._failure_policy = policy
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config",
            "mas",
        )
        self._policies = _load_yaml(os.path.join(base_dir, "writer_policies.yaml")) or {}

    async def write(
        self,
        task_type: TaskType,
        *,
        workflow_id: str,
        scene_number: Optional[int] = None,
        output: Dict[str, Any],
    ) -> MemoryWriteReceipt:
        """Persist recognized memory facts and always return a typed outcome."""

        if os.getenv("MEMORY_WRITE_ENABLED", "true").lower() == "false":
            return MemoryWriteReceipt(
                status=MemoryWriteStatus.SKIPPED,
                reason_code=MemoryWriteReason.DISABLED,
            )

        start_ts = datetime.now().timestamp()
        try:
            memory_id = await self._write_recognized_fact(
                task_type,
                workflow_id=workflow_id,
                scene_number=scene_number,
                output=output,
            )
            if memory_id is None:
                return MemoryWriteReceipt(
                    status=MemoryWriteStatus.SKIPPED,
                    reason_code=MemoryWriteReason.NO_MATCHING_FACT,
                )
            await self._record_success(task_type, start_ts=start_ts)
            return MemoryWriteReceipt(
                status=MemoryWriteStatus.WRITTEN,
                reason_code=MemoryWriteReason.STORED,
                memory_id=str(memory_id),
            )
        except Exception as exc:
            await self._record_failure(task_type)
            diagnostic = f"{type(exc).__name__}: {exc}"
            if self._failure_policy == "fail":
                raise MemoryWriteError(
                    reason_code=MemoryWriteReason.OPTIONAL_WRITE_FAILED,
                    message=f"Optional memory write failed: {diagnostic}",
                ) from exc
            _logger.warning(
                "Optional memory write degraded: reason_code=%s diagnostic=%s",
                MemoryWriteReason.OPTIONAL_WRITE_FAILED.value,
                diagnostic,
            )
            return MemoryWriteReceipt(
                status=MemoryWriteStatus.DEGRADED,
                reason_code=MemoryWriteReason.OPTIONAL_WRITE_FAILED,
                diagnostic=diagnostic,
            )

    async def _write_recognized_fact(
        self,
        task_type: TaskType,
        *,
        workflow_id: str,
        scene_number: Optional[int],
        output: Dict[str, Any],
    ) -> Optional[str]:
        if task_type is TaskType.SCRIPT_WRITING and any(
            key in output for key in ("script_text", "voice_over_text", "content_development_arc")
        ):
            return await self._long_term.store_memory(
                content={
                    "agent_role": "Script Writer - Scene References",
                    "workflow_id": workflow_id,
                    "scene_number": scene_number,
                    "script_text": output.get("script_text") or output.get("script") or "",
                    "voice_over_text": output.get("voice_over_text")
                    or output.get("voice_over")
                    or "",
                    "content_development_arc": output.get("content_development_arc") or {},
                },
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.MEDIUM,
                tags=[
                    "scene_references",
                    f"scene_{scene_number}" if scene_number is not None else "scene_unknown",
                ],
                agent_id="script_writer",
                task_id=workflow_id,
                metadata={
                    "workflow_id": workflow_id,
                    "scene_number": scene_number,
                    "content_type": "scene_references",
                },
            )

        if task_type is TaskType.SCRIPT_WRITING and any(
            key in output for key in ("roles", "per_scene_roles")
        ):
            return await self._long_term.store_memory(
                content={
                    "agent_role": "Role Consistency - Roles Snapshot",
                    "workflow_id": workflow_id,
                    "scene_number": scene_number,
                    "roles": output.get("roles", []),
                    "per_scene_roles": output.get("per_scene_roles", {}),
                    "timestamp": datetime.now().isoformat(),
                },
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.HIGH,
                tags=["role_consistency", "roles_snapshot"],
                agent_id="script_writer",
                task_id=workflow_id,
                metadata={
                    "workflow_id": workflow_id,
                    "content_type": "roles_snapshot",
                },
            )

        if task_type in {TaskType.IMAGE_GENERATION, TaskType.VIDEO_GENERATION}:
            metadata = output.get("metadata") or {}
            if metadata:
                return await self._long_term.store_memory(
                    content={
                        "agent_role": "Generation Metadata",
                        "workflow_id": workflow_id,
                        "scene_number": scene_number,
                        "generation_metadata": metadata,
                    },
                    memory_type=MemoryType.WORKING,
                    importance=MemoryImportance.LOW,
                    tags=[
                        "generation_metadata",
                        f"scene_{scene_number}" if scene_number is not None else "scene_unknown",
                    ],
                    agent_id="generator",
                    task_id=workflow_id,
                    metadata={
                        "workflow_id": workflow_id,
                        "scene_number": scene_number,
                        "content_type": "generation_metadata",
                    },
                )
        return None

    async def _record_success(self, task_type: TaskType, *, start_ts: float) -> None:
        labels = {"task_type": task_type.value}
        duration_ms = int((datetime.now().timestamp() - start_ts) * 1000)
        try:
            await self._metrics.record_metric("memory_write_total", 1, "counter", labels=labels)
            await self._metrics.record_metric(
                "memory_write_duration_ms", duration_ms, "histogram", labels=labels
            )
        except Exception as exc:
            _logger.warning("Memory write metrics failed: %s", exc)

    async def _record_failure(self, task_type: TaskType) -> None:
        try:
            await self._metrics.record_metric(
                "memory_write_failed_total",
                1,
                "counter",
                labels={"task_type": task_type.value},
            )
        except Exception as exc:
            _logger.warning("Memory write failure metrics failed: %s", exc)


memory_writer: Optional[MemoryWriter] = None

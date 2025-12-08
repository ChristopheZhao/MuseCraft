"""
Memory Writer - Standardized write-back of agent outputs into shared memory

Phase 1 keeps this minimal: it writes known fields according to lightweight
defaults and optional writer policies. It avoids coupling agents to storage
details and enforces consistent tags/metadata.
"""
from __future__ import annotations

import os
from datetime import datetime
import logging
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

from ..models.task import TaskType
from ..agents.memory.long_term.stores import MemoryType, MemoryImportance
from .memory_provider import MemoryServices
from .monitoring_service import MonitoringService, MetricType


_logger = logging.getLogger("memory_writer")


def _load_yaml(path: str) -> Optional[Dict[str, Any]]:
    if not yaml:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return None
    except Exception as e:
        _logger.warning(f"Failed to load YAML {path}: {e}")
        return None


class MemoryWriter:
    def __init__(self, memory_services: MemoryServices):
        if memory_services is None:
            raise ValueError("memory_services is required for MemoryWriter")
        self._gms = memory_services.global_service
        self._long_term = memory_services.long_term
        if self._long_term is None:
            raise ValueError("long_term memory service is required for MemoryWriter")
        self._mon = MonitoringService()
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "mas")
        self._policy_path = os.path.join(base_dir, "writer_policies.yaml")
        self._policies = _load_yaml(self._policy_path) or {}

    async def write(
        self,
        task_type: TaskType,
        *,
        workflow_id: str,
        scene_number: Optional[int] = None,
        output: Dict[str, Any],
    ) -> Optional[str]:
        """Write agent outputs back into memory following simple rules/policies.

        Returns memory_id when a new item is stored; None otherwise.
        """
        if os.getenv("MEMORY_WRITE_ENABLED", "true").lower() == "false":
            return None

        policy = self._policies.get(task_type.value, {}) if self._policies else {}
        start_ts = datetime.now().timestamp()

        try:
            # Heuristic mapping for Phase 1
            if task_type == TaskType.SCRIPT_WRITING:
                # Write scene references (script/voice-over/etc.) as EPISODIC
                if (
                    "script_text" in output
                    or "voice_over_text" in output
                    or "content_development_arc" in output
                ):
                    payload = {
                        "agent_role": "Script Writer - Scene References",
                        "workflow_id": workflow_id,
                        "scene_number": scene_number,
                        "script_text": output.get("script_text") or output.get("script") or "",
                        "voice_over_text": output.get("voice_over_text") or output.get("voice_over") or "",
                        "content_development_arc": output.get("content_development_arc") or {},
                    }
                    mem_id = await self._long_term.store_memory(
                        content=payload,
                        memory_type=MemoryType.EPISODIC,
                        importance=MemoryImportance.MEDIUM,
                        tags=["scene_references", f"scene_{scene_number}" if scene_number is not None else "scene_unknown"],
                        agent_id="script_writer",
                        task_id=workflow_id,
                        metadata={"workflow_id": workflow_id, "scene_number": scene_number, "content_type": "scene_references"},
                    )
                    # metrics
                    try:
                        dur_ms = int((datetime.now().timestamp() - start_ts) * 1000)
                        await self._mon.record_metric("memory_write_total", 1, MetricType.COUNTER, labels={"task_type": task_type.value})
                        await self._mon.record_metric("memory_write_duration_ms", dur_ms, MetricType.HISTOGRAM, labels={"task_type": task_type.value})
                    except Exception:
                        pass
                    return mem_id

                # Write role consistency snapshot (global/per-scene) as EPISODIC when provided
                if ("roles" in output) or ("per_scene_roles" in output):
                    payload = {
                        "agent_role": "Role Consistency - Roles Snapshot",
                        "workflow_id": workflow_id,
                        "scene_number": scene_number,
                        "roles": output.get("roles", []),
                        "per_scene_roles": output.get("per_scene_roles", {}),
                        "timestamp": datetime.now().isoformat(),
                    }
                    mem_id = await self._long_term.store_memory(
                        content=payload,
                        memory_type=MemoryType.EPISODIC,
                        importance=MemoryImportance.HIGH,
                        tags=["role_consistency", "roles_snapshot"],
                        agent_id="script_writer",
                        task_id=workflow_id,
                        metadata={"workflow_id": workflow_id, "content_type": "roles_snapshot"},
                    )
                    try:
                        dur_ms = int((datetime.now().timestamp() - start_ts) * 1000)
                        await self._mon.record_metric("memory_write_total", 1, MetricType.COUNTER, labels={"task_type": task_type.value})
                        await self._mon.record_metric("memory_write_duration_ms", dur_ms, MetricType.HISTOGRAM, labels={"task_type": task_type.value})
                    except Exception:
                        pass
                    return mem_id

            if task_type == TaskType.IMAGE_GENERATION or task_type == TaskType.VIDEO_GENERATION:
                # Persist lightweight execution metadata if present
                meta = output.get("metadata") or {}
                if meta:
                    payload = {
                        "agent_role": "Generation Metadata",
                        "workflow_id": workflow_id,
                        "scene_number": scene_number,
                        "generation_metadata": meta,
                    }
                    mem_id = await self._long_term.store_memory(
                        content=payload,
                        memory_type=MemoryType.WORKING,
                        importance=MemoryImportance.LOW,
                        tags=["generation_metadata", f"scene_{scene_number}" if scene_number is not None else "scene_unknown"],
                        agent_id="generator",
                        task_id=workflow_id,
                        metadata={"workflow_id": workflow_id, "scene_number": scene_number, "content_type": "generation_metadata"},
                    )
                    try:
                        dur_ms = int((datetime.now().timestamp() - start_ts) * 1000)
                        await self._mon.record_metric("memory_write_total", 1, MetricType.COUNTER, labels={"task_type": task_type.value})
                        await self._mon.record_metric("memory_write_duration_ms", dur_ms, MetricType.HISTOGRAM, labels={"task_type": task_type.value})
                    except Exception:
                        pass
                    return mem_id

            # Default: do nothing
            return None

        except Exception as e:
            _logger.warning(f"Memory write failed: {e}")
            try:
                await self._mon.record_metric("memory_write_failed_total", 1, MetricType.COUNTER, labels={"task_type": task_type.value})
            except Exception:
                pass
            return None


memory_writer: Optional[MemoryWriter] = None

"""
Context Assembler - Centralized context retrieval and assembly for agent execution

This module assembles required context from the shared memory layer based on
task type and lightweight policies. It is intentionally simple and non-invasive:
- Reads declarative policies from config/mas/context_policies.yaml if present
- Falls back to sane defaults when config is missing
- Uses GlobalMemoryService + SceneContinuityMemory (if applicable)

This keeps agents decoupled from memory internals while allowing the
SupervisorOrchestrator to inject consistent context before execution.
"""
from __future__ import annotations

import os
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None

from ..models.task import TaskType
from ..agents.memory.base_memory import MemoryType, MemoryImportance
from .global_memory_service import GlobalMemoryService
from ..core.scene_continuity_memory import get_scene_continuity_memory
from .monitoring_service import MonitoringService, MetricType


_logger = logging.getLogger("context_assembler")


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


class ContextAssembler:
    def __init__(self):
        self._gms = GlobalMemoryService()
        self._mon = MonitoringService()
        # Optional external policy files
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "mas")
        self._policy_path = os.path.join(base_dir, "context_policies.yaml")
        self._policies = _load_yaml(self._policy_path) or {}

    async def assemble(
        self,
        task_type: TaskType,
        *,
        workflow_id: str,
        scene_number: Optional[int] = None,
        token_budget: int = 2000,
    ) -> Dict[str, Any]:
        """
        Assemble context for a given task type and scope.

        Returns a dict with keys like: overall_guidance, scene_guidance, continuity
        """
        # Fast opt-out
        if os.getenv("MEMORY_CONTEXT_ENABLED", "true").lower() == "false":
            return {}

        start_ts = datetime.now().timestamp()
        context: Dict[str, Any] = {
            "has_context": False,
            "overall_guidance": {},
            "scene_guidance": {},
            "continuity": {},
        }

        # Policy-driven minimal requirements (fallback to defaults if missing)
        policy = self._policies.get(task_type.value, {}) if self._policies else {}

        # 1) Overall concept guidance (CONCEPTUAL)
        overall_ok = False
        scene_ok = False
        cont_ok = False
        try:
            concept = await self._gms.retrieve_creative_guidance(workflow_id=workflow_id, agent_name="context_assembler")
            if concept.get("overall_guidance"):
                context["overall_guidance"] = concept["overall_guidance"]
                context["has_context"] = True
                overall_ok = True
        except Exception as e:
            _logger.warning(f"Concept retrieval failed: {e}")

        # 2) Scene guidance (EPISODIC)
        if scene_number is not None:
            try:
                scene_ctx = await self._gms.retrieve_creative_guidance(
                    workflow_id=workflow_id, scene_number=scene_number, agent_name="context_assembler"
                )
                if scene_ctx.get("scene_guidance"):
                    context["scene_guidance"] = scene_ctx["scene_guidance"]
                    context["has_context"] = True
                    scene_ok = True
            except Exception as e:
                _logger.warning(f"Scene guidance retrieval failed: {e}")

        # 3) Continuity (previous scene final frame)
        if scene_number is not None:
            try:
                cont_mem = get_scene_continuity_memory()
                info = await cont_mem.get_scene_continuity_info(scene_number)
                if info.get("requires_continuity"):
                    context["continuity"] = info
                    context["has_context"] = True
                    cont_ok = True
            except Exception as e:
                _logger.warning(f"Continuity retrieval failed: {e}")

        # 4) Conservative trimming by token budget (placeholder)
        # We keep it simple for Phase 1; policies can refine this later.
        context["token_budget"] = token_budget

        # metrics
        try:
            dur_ms = int((datetime.now().timestamp() - start_ts) * 1000)
            await self._mon.record_metric(
                name="context_assembled_total",
                value=1,
                metric_type=MetricType.COUNTER,
                labels={"task_type": task_type.value}
            )
            await self._mon.record_metric(
                name="context_assembled_duration_ms",
                value=dur_ms,
                metric_type=MetricType.HISTOGRAM,
                labels={"task_type": task_type.value}
            )
            await self._mon.record_metric(
                name="context_component_hits",
                value=int(overall_ok) + int(scene_ok) + int(cont_ok),
                metric_type=MetricType.GAUGE,
                labels={"task_type": task_type.value, "overall": str(overall_ok), "scene": str(scene_ok), "continuity": str(cont_ok)}
            )
        except Exception:
            pass
        return context


# Singleton
context_assembler = ContextAssembler()

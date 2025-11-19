from __future__ import annotations

"""Helpers for logging and querying episodic (per-iteration) memory."""

import json
import logging
from typing import Any, Dict, List, Optional

from ....services.memory_provider import get_memory_services, MemoryServices
from .stores import MemoryType, MemoryImportance


def _json_safe(payload: Any) -> Any:
    """Best-effort conversion of arbitrary payloads into JSON-serializable data."""
    try:
        return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        try:
            return json.loads(json.dumps(str(payload), ensure_ascii=False))
        except Exception:
            return str(payload)


async def log_react_iteration(
    *,
    workflow_id: str,
    agent_name: str,
    iteration: int,
    observation: Dict[str, Any],
    action_plan: Dict[str, Any],
    action_result: Dict[str, Any],
    act_log: Optional[List[Dict[str, Any]]] = None,
    react_metrics: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist a single ReAct iteration trace as episodic memory."""
    services = get_memory_services()
    manager = getattr(services.global_service, "memory_manager", None)
    if manager is None:
        return
    content = {
        "observation": _json_safe(observation),
        "action_plan": _json_safe(action_plan),
        "action_result": _json_safe(action_result),
        "act_log": _json_safe(act_log or []),
        "react_metrics": _json_safe(react_metrics or {}),
    }
    tags = [
        f"workflow:{workflow_id}",
        f"agent:{agent_name}",
        "react_iteration",
    ]
    metadata = {
        "iteration": int(iteration),
        "record_type": "react_iteration",
    }
    try:
        await manager.store_memory(
            content=content,
            memory_type=MemoryType.EPISODIC,
            importance=MemoryImportance.MEDIUM,
            tags=tags,
            agent_id=agent_name,
            task_id=workflow_id,
            metadata=metadata,
        )
    except Exception:
        # episodic logging should never interrupt agent execution
        logging = getattr(services.global_service, "logger", None)
        if logging:
            logging.warning("Failed to log episodic memory", exc_info=True)


async def query_react_iterations(
    *,
    workflow_id: str,
    agent_name: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch recent episodic entries for debugging/inspection."""
    services = get_memory_services()
    manager = getattr(services.global_service, "memory_manager", None)
    if manager is None:
        return []
    try:
        memories = await manager.search_memories(
            query=None,
            tags=[f"workflow:{workflow_id}"],
            memory_types=[MemoryType.EPISODIC],
            agent_id=agent_name,
            task_id=workflow_id,
            limit=limit,
        )
        return [m.content for m in memories if m and m.content]
    except Exception:
        return []


__all__ = ["log_react_iteration", "query_react_iterations"]

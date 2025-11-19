"""
MemoryTool - Unified memory read/write/search capability exposed as a Tool.

This provides agents with a controlled interface to shared memory without
binding them to a specific backend. It routes through GlobalMemoryService and
enforces scope and simple quotas if needed.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from ...services.memory_provider import get_memory_services, MemoryServices
from ...core.scene_continuity_memory import get_scene_continuity_memory
from ...agents.memory.long_term.stores import MemoryType, MemoryImportance
from ...services.monitoring_service import MonitoringService, MetricType


class MemoryTool(AsyncTool):
    def __init__(self, memory_services: Optional[MemoryServices] = None):
        super().__init__()
        self._memory_services = memory_services or get_memory_services()

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="memory_tool",
            version="0.1.0",
            description="Shared memory access (search/write/continuity) with scope control",
            tool_type=ToolType.UTILITY,
            author="system",
            tags=["memory", "context", "state"],
            capabilities=["search_memories", "get_recent", "write_memory", "get_continuity"],
            limitations=["scope_required", "non_persistent_if_dict_backend"],
        )

    def _initialize(self):
        self.gms = self._memory_services.global_service
        self._max_items = int(os.getenv("MEMORY_TOOL_MAX_ITEMS", "5"))
        self._mon = MonitoringService()

    def get_available_actions(self) -> List[str]:
        return ["search_memories", "get_recent", "write_memory", "get_continuity"]

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "search_memories":
            return {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string"},
                    "scene_number": {"type": ["integer", "null"]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "memory_type": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["workflow_id"],
            }
        if action == "get_recent":
            return {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["workflow_id"],
            }
        if action == "write_memory":
            return {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string"},
                    "scene_number": {"type": ["integer", "null"]},
                    "content": {"type": "object"},
                    "memory_type": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "string"},
                },
                "required": ["workflow_id", "content"],
            }
        if action == "get_continuity":
            return {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer"},
                },
                "required": ["scene_number"],
            }
        return {}

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        action = tool_input.action
        p = tool_input.parameters

        start_ts = datetime.now().timestamp()
        if action == "search_memories":
            res = await self._act_search_memories(p)
        elif action == "get_recent":
            res = await self._act_get_recent(p)
        elif action == "write_memory":
            res = await self._act_write_memory(p)
        elif action == "get_continuity":
            res = await self._act_get_continuity(p)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)

        # metrics
        try:
            dur_ms = int((datetime.now().timestamp() - start_ts) * 1000)
            await self._mon.record_metric("memory_tool_calls_total", 1, MetricType.COUNTER, labels={"action": action})
            await self._mon.record_metric("memory_tool_duration_ms", dur_ms, MetricType.HISTOGRAM, labels={"action": action})
        except Exception:
            pass
        return res

    async def _act_search_memories(self, p: Dict[str, Any]) -> Dict[str, Any]:
        workflow_id = p["workflow_id"]
        tags = p.get("tags") or []
        limit = int(p.get("limit") or self._max_items)
        mtype = p.get("memory_type")

        memory_type = None
        if mtype:
            try:
                memory_type = MemoryType(mtype)
            except Exception:
                memory_type = None

        items = await self.gms.memory_manager.retrieve_memories(
            tags=tags or None,
            memory_type=memory_type,
            task_id=workflow_id,
            limit=limit,
        )
        return {"results": [it.to_dict() for it in items]}

    async def _act_get_recent(self, p: Dict[str, Any]) -> Dict[str, Any]:
        workflow_id = p["workflow_id"]
        limit = int(p.get("limit") or self._max_items)
        items = await self.gms.memory_manager.retrieve_memories(
            task_id=workflow_id, limit=limit
        )
        return {"results": [it.to_dict() for it in items]}

    async def _act_write_memory(self, p: Dict[str, Any]) -> Dict[str, Any]:
        workflow_id = p["workflow_id"]
        scene_number = p.get("scene_number")
        content = p["content"]
        tags = p.get("tags") or []
        mtype = p.get("memory_type") or MemoryType.WORKING.value
        importance = p.get("importance") or MemoryImportance.MEDIUM.name

        try:
            memory_type = MemoryType(mtype)
        except Exception:
            memory_type = MemoryType.WORKING
        try:
            importance_val = MemoryImportance[importance]
        except Exception:
            importance_val = MemoryImportance.MEDIUM

        mem_id = await self.gms.memory_manager.store_memory(
            content=content,
            memory_type=memory_type,
            importance=importance_val,
            tags=tags,
            agent_id="memory_tool",
            task_id=workflow_id,
            metadata={"workflow_id": workflow_id, "scene_number": scene_number},
        )
        return {"memory_id": mem_id}

    async def _act_get_continuity(self, p: Dict[str, Any]) -> Dict[str, Any]:
        scene_number = int(p["scene_number"])
        mem = get_scene_continuity_memory()
        info = await mem.get_scene_continuity_info(scene_number)
        return info

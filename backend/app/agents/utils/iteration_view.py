from __future__ import annotations

"""Agent-level iteration/state view builder.

提供只读的统计/汇总视图，便于上下文注入和诊断，不重复载入 WM 明细。
"""

from typing import Any, Dict, Optional, Iterable

from ..memory.short_term.service import WorkingMemoryService, MemoryNotInitializedError
from ..utils.memory_helpers import agent_scope
from ..adapters.video.memory_adapter import VideoMemoryAdapter


def _count_events(event_streams: Dict[str, Iterable[Dict[str, Any]]]) -> tuple[int, int]:
    total = 0
    errors = 0
    for dq in (event_streams or {}).values():
        for event in dq or []:
            if not isinstance(event, dict):
                continue
            total += 1
            try:
                if not bool(event.get("success", True)):
                    errors += 1
            except Exception:
                pass
    return total, errors


def build_agent_iteration_view(
    workflow_id: str,
    agent_name: str,
    *,
    service: WorkingMemoryService,
    create_if_absent: bool = False,
) -> Dict[str, Any]:
    """
    从 agent-scope WorkingMemory 构建迭代状态视图（统计/汇总）。

    - 只包含计数/汇总，不重复 action/obs/事件明细。
    - 若 create_if_absent=True，则在缺失时创建空 WM（不带 shared_view）。
    """
    scope = agent_scope(workflow_id, agent_name)
    try:
        wm = service.get(workflow_id, scope)
    except MemoryNotInitializedError:
        if not create_if_absent:
            raise
        wm = service.create_or_get(workflow_id, scope, owner_agent=agent_name)

    total_events, error_events = _count_events(getattr(wm, "event_streams", {}) or {})
    notes_count = len(getattr(wm, "notes", []) or [])
    artifacts_count = len(getattr(wm, "iteration_artifacts", []) or [])

    scene_stats: Optional[Dict[str, Any]] = None
    try:
        adapter = VideoMemoryAdapter(wm)
        stats = adapter.classify_scenes()
        scene_stats = {
            "summary": stats.get("summary", {}),
            "retry_hotspots": (stats.get("global_stats") or {}).get("retry_hotspots", []),
            "failures": stats.get("failures", []),
        }
    except Exception:
        # 可能不是视频域，忽略
        scene_stats = None

    view: Dict[str, Any] = {
        "workflow_id": str(workflow_id),
        "agent": agent_name,
        "iteration_count": total_events,
        "error_events": error_events,
        "notes_count": notes_count,
        "artifacts_count": artifacts_count,
    }
    if scene_stats:
        view["scene_stats"] = scene_stats
    return view


__all__ = ["build_agent_iteration_view"]

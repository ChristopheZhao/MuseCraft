from __future__ import annotations

"""WorkingMemoryBuilder - 构建/同步短期工作记忆容器。"""

from copy import deepcopy
from typing import Any, Dict, Optional

from .working_memory import WorkingMemory
from ..storage.in_memory import ShortTermMemoryStore, InMemoryShortTermStore


class WorkingMemoryBuilder:
    """Factory responsible for creating/syncing WorkingMemory instances."""

    def __init__(
        self,
        journal_max_events: int = 5,
        *,
        store_factory: Optional[callable[[], ShortTermMemoryStore]] = None,
    ) -> None:
        self._journal_max_events = int(journal_max_events)
        self._store_factory = store_factory or (lambda: InMemoryShortTermStore())

    def build(
        self,
        task_id: str,
        scope: str,
        shared_view: Optional[WorkingMemory] = None,
        *,
        owner_agent: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkingMemory:
        """Construct a domain-neutral WorkingMemory for the workflow scope."""
        goal_text = ""
        if isinstance(context, dict):
            goal_text = str(context.get("goal_text") or "")
        wm = WorkingMemory(
            workflow_state_id=str(task_id),
            scope=str(scope),
            goal_text=goal_text,
            journal_max_events=self._journal_max_events,
            store=self._store_factory(),
        )
        if shared_view is not None:
            self.sync(wm, shared_view, owner_agent=owner_agent)
        return wm

    def sync(
        self,
        target: WorkingMemory,
        shared_view: WorkingMemory,
        *,
        owner_agent: Optional[str] = None,
    ) -> WorkingMemory:
        """Synchronize agent-scoped memory with the MAS-level shared view."""
        if target is None or shared_view is None:
            return target
        # 1) 同步基础存储键值（facts）；确保缺失键被删除，list_keys 不可用时回退到旧 facts 属性
        shared_keys: Optional[list[str]] = None
        try:
            shared_keys = list(shared_view.list_keys())
        except Exception:
            shared_keys = None

        if shared_keys is not None:
            # 删除在目标中但不在源中的键，避免残留陈旧值
            try:
                for k in list(target.list_keys()):
                    if k not in shared_keys:
                        target.delete(k)
            except Exception:
                pass
            # 复制源键
            for k in shared_keys:
                try:
                    target.put(k, deepcopy(shared_view.get(k)))
                except Exception:
                    continue
        else:
            # 回退：尝试深拷贝 legacy facts 属性
            try:
                facts_attr = getattr(shared_view, "facts", None)
                if isinstance(facts_attr, dict):
                    try:
                        for k in list(target.list_keys()):
                            target.delete(k)
                    except Exception:
                        pass
                    for k, v in facts_attr.items():
                        try:
                            target.put(str(k), deepcopy(v))
                        except Exception:
                            continue
            except Exception:
                pass
        # 2) notes / workflow_facts 等显式字段
        target.notes = list(getattr(shared_view, "notes", []) or [])
        target.workflow_facts = deepcopy(getattr(shared_view, "workflow_facts", {}))
        target.event_streams = deepcopy(getattr(shared_view, "event_streams", {}))
        artifacts = list(getattr(shared_view, "iteration_artifacts", []) or [])
        target.iteration_artifacts.clear()
        for record in artifacts:
            if isinstance(record, dict):
                target.iteration_artifacts.append(record)
        return target


__all__ = ["WorkingMemoryBuilder"]

from __future__ import annotations

"""WorkingMemoryBuilder - 构建/同步短期工作记忆容器。"""

from copy import deepcopy
from typing import Any, Dict, Optional

from .working_memory import WorkingMemory


class WorkingMemoryBuilder:
    """Factory responsible for creating/syncing WorkingMemory instances."""

    def __init__(self, journal_max_events: int = 5) -> None:
        self._journal_max_events = int(journal_max_events)

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
        target.facts = deepcopy(getattr(shared_view, "facts", {}))
        target.notes = list(getattr(shared_view, "notes", []) or [])
        target.workflow_facts = deepcopy(getattr(shared_view, "workflow_facts", {}))
        target.facts_slots = deepcopy(getattr(shared_view, "facts_slots", {}))
        target.event_streams = deepcopy(getattr(shared_view, "event_streams", {}))
        artifacts = list(getattr(shared_view, "iteration_artifacts", []) or [])
        target.iteration_artifacts.clear()
        for record in artifacts:
            if isinstance(record, dict):
                target.iteration_artifacts.append(record)
        return target


__all__ = ["WorkingMemoryBuilder"]

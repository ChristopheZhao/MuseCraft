"""
Explicit owner for orchestration queue / standby ordering artifacts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..models import AgentType


class OrchestrationQueuePolicy:
    """Pure policy object for internal orchestrator <-> control-plane queue shaping."""

    @staticmethod
    def _agent_pool_order(
        *,
        task_specs: Dict[AgentType, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]] = None,
    ) -> List[AgentType]:
        if isinstance(candidate_agents, list) and candidate_agents:
            return [agent for agent in candidate_agents if isinstance(agent, AgentType)]
        return [
            agent_type
            for agent_type in (task_specs or {}).keys()
            if isinstance(agent_type, AgentType)
        ]

    @staticmethod
    def _rank_agent_spec(
        *,
        agent_type: AgentType,
        task_specs: Dict[AgentType, Dict[str, Any]],
        fallback_index: int,
    ) -> Tuple[int, int]:
        spec = task_specs.get(agent_type) if isinstance(task_specs, dict) else None
        raw_order = spec.get("order") if isinstance(spec, dict) else None
        try:
            return int(raw_order), fallback_index
        except Exception:
            return fallback_index, fallback_index

    @classmethod
    def build_execution_queue(
        cls,
        *,
        task_specs: Dict[AgentType, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]] = None,
    ) -> List[AgentType]:
        ranked: List[Tuple[int, int, AgentType]] = []
        for index, agent_type in enumerate(
            cls._agent_pool_order(
                task_specs=task_specs,
                candidate_agents=candidate_agents,
            )
        ):
            spec = task_specs.get(agent_type) if isinstance(task_specs, dict) else None
            if not isinstance(spec, dict):
                continue
            if spec.get("run") is False:
                continue
            order, fallback_index = cls._rank_agent_spec(
                agent_type=agent_type,
                task_specs=task_specs,
                fallback_index=index,
            )
            ranked.append((order, fallback_index, agent_type))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [agent_type for _, _, agent_type in ranked]

    @classmethod
    def build_standby_agents(
        cls,
        *,
        task_specs: Dict[AgentType, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]] = None,
    ) -> List[AgentType]:
        standby: List[AgentType] = []
        for agent_type in cls._agent_pool_order(
            task_specs=task_specs,
            candidate_agents=candidate_agents,
        ):
            spec = task_specs.get(agent_type) if isinstance(task_specs, dict) else None
            if isinstance(spec, dict) and spec.get("run") is False:
                standby.append(agent_type)
        return standby

    @classmethod
    def insert_agent_into_execution_queue(
        cls,
        execution_queue: List[AgentType],
        *,
        current_index: int,
        agent_type: AgentType,
        task_specs: Dict[AgentType, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]] = None,
    ) -> bool:
        updated_queue = list(execution_queue or [])
        for pending in updated_queue[max(0, int(current_index)) + 1:]:
            if pending == agent_type:
                execution_queue[:] = updated_queue
                return False

        order_index = {
            atype: idx
            for idx, atype in enumerate(
                cls._agent_pool_order(
                    task_specs=task_specs,
                    candidate_agents=candidate_agents,
                )
            )
        }
        target_order, target_fallback = cls._rank_agent_spec(
            agent_type=agent_type,
            task_specs=task_specs,
            fallback_index=order_index.get(agent_type, len(order_index) + 100),
        )
        insert_at = len(updated_queue)
        for idx in range(max(0, int(current_index)) + 1, len(updated_queue)):
            pending_agent = updated_queue[idx]
            pending_order, pending_fallback = cls._rank_agent_spec(
                agent_type=pending_agent,
                task_specs=task_specs,
                fallback_index=order_index.get(pending_agent, len(order_index) + 100),
            )
            if (pending_order, pending_fallback) > (target_order, target_fallback):
                insert_at = idx
                break
        updated_queue.insert(insert_at, agent_type)
        execution_queue[:] = updated_queue
        return True

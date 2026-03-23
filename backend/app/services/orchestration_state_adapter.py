"""
Control-plane state adapter for orchestration context and runtime traces.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..agents.utils.memory_helpers import read_shared_fact, write_shared_fact
from ..models import AgentType
from .memory_provider import MemoryServices


class OrchestrationStateAdapter:
    """Owns deterministic orchestration state normalization and persistence."""

    _FORBIDDEN_WORKFLOW_CONTROL_PREFIXES = (
        "workflow.session.",
        "workflow.node.",
        "workflow.attempt.",
        "workflow.gate_decision.",
    )

    def __init__(self, memory_services: Optional[MemoryServices] = None):
        if memory_services is None:
            raise ValueError("memory_services is required for OrchestrationStateAdapter")
        self._memory_services = memory_services

    def _write_workflow_projection(
        self,
        workflow_state_id: str,
        key: str,
        value: Any,
    ) -> None:
        normalized_key = str(key or "")
        if any(
            normalized_key.startswith(prefix)
            for prefix in self._FORBIDDEN_WORKFLOW_CONTROL_PREFIXES
        ):
            raise ValueError(
                f"Forbidden runtime control state projection key: {normalized_key}"
            )
        write_shared_fact(
            str(workflow_state_id),
            normalized_key,
            value,
            service=self._memory_services.short_term,
        )

    @staticmethod
    def normalize_audio_policy(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"adaptive", "provider_only", "mas_only"}:
            return raw
        alias_map = {
            "auto": "adaptive",
            "prefer_native": "adaptive",
            "native_only": "provider_only",
            "agent_only": "mas_only",
        }
        return alias_map.get(raw, "adaptive")

    def build_audio_contract(
        self,
        *,
        workflow_state_id: str,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(input_data or {})
        provided = payload.get("audio_contract")
        if isinstance(provided, dict) and provided:
            raw_policy = provided.get("policy")
            source = "input.audio_contract"
        else:
            raw_policy = payload.get("audio_policy")
            source = "input.audio_policy"

        if raw_policy is None:
            raw_policy = "adaptive"
            source = "orchestrator.default"

        contract = {
            "version": 1,
            "policy": self.normalize_audio_policy(raw_policy),
            "allow_silence": bool(payload.get("allow_silence", True)),
            "need_global_bgm": bool(payload.get("need_global_bgm", False)),
            "need_voiceover": bool(payload.get("need_voiceover", False)),
            "source": source,
            "workflow_state_id": str(workflow_state_id or ""),
        }
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.contract.audio",
            dict(contract),
        )
        return contract

    def persist_llm_planning_context(
        self,
        *,
        workflow_state_id: str,
        registered_agents: List[AgentType],
        candidate_agents: List[AgentType],
        audio_contract: Dict[str, Any],
        capability_snapshot: Optional[Dict[str, Any]] = None,
        selection_rationale: Optional[str] = None,
    ) -> Dict[str, Any]:
        capability = dict(capability_snapshot or {})
        registered = [agent.value for agent in registered_agents if isinstance(agent, AgentType)]
        available_agents = [agent.value for agent in candidate_agents if isinstance(agent, AgentType)]
        plan = {
            "source": "orchestrator.llm_planning_context",
            "workflow_state_id": str(workflow_state_id or ""),
            "contract": {"audio": dict(audio_contract or {})},
            "registered_agents": registered,
            "capability_snapshot": {
                "provider": capability.get("provider"),
                "supports_native_audio": bool(capability.get("supports_native_audio")),
                "native_audio_param_name": capability.get("native_audio_param_name"),
                "native_audio_default_enabled": capability.get("native_audio_default_enabled"),
            },
            "available_agents": available_agents,
        }
        if isinstance(selection_rationale, str) and selection_rationale.strip():
            plan["selection_rationale"] = selection_rationale.strip()
        activation_payload = {
            "route_source": "orchestrator.llm_task_spec",
            "workflow_state_id": str(workflow_state_id or ""),
            "available_agents": available_agents,
        }
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.plan",
            dict(plan),
        )
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.activation_pool",
            activation_payload,
        )
        return plan

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

    @staticmethod
    def build_execution_queue(
        *,
        task_specs: Dict[AgentType, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]] = None,
    ) -> List[AgentType]:
        ranked: List[Tuple[int, int, AgentType]] = []
        for index, agent_type in enumerate(
            OrchestrationStateAdapter._agent_pool_order(
                task_specs=task_specs,
                candidate_agents=candidate_agents,
            )
        ):
            spec = task_specs.get(agent_type) if isinstance(task_specs, dict) else None
            if not isinstance(spec, dict):
                continue
            if isinstance(spec, dict) and spec.get("run") is False:
                continue
            order, fallback_index = OrchestrationStateAdapter._rank_agent_spec(
                agent_type=agent_type,
                task_specs=task_specs,
                fallback_index=index,
            )
            ranked.append((order, fallback_index, agent_type))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [agent_type for _, _, agent_type in ranked]

    @staticmethod
    def build_standby_agents(
        *,
        task_specs: Dict[AgentType, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]] = None,
    ) -> List[AgentType]:
        standby: List[AgentType] = []
        for agent_type in OrchestrationStateAdapter._agent_pool_order(
            task_specs=task_specs,
            candidate_agents=candidate_agents,
        ):
            spec = task_specs.get(agent_type) if isinstance(task_specs, dict) else None
            if isinstance(spec, dict) and spec.get("run") is False:
                standby.append(agent_type)
        return standby

    @staticmethod
    def insert_agent_into_execution_queue(
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
                OrchestrationStateAdapter._agent_pool_order(
                    task_specs=task_specs,
                    candidate_agents=candidate_agents,
                )
            )
        }
        target_order, target_fallback = OrchestrationStateAdapter._rank_agent_spec(
            agent_type=agent_type,
            task_specs=task_specs,
            fallback_index=order_index.get(agent_type, len(order_index) + 100),
        )
        insert_at = len(updated_queue)
        for idx in range(max(0, int(current_index)) + 1, len(updated_queue)):
            pending_agent = updated_queue[idx]
            pending_order, pending_fallback = OrchestrationStateAdapter._rank_agent_spec(
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

    def persist_task_specs(
        self,
        *,
        workflow_state_id: str,
        task_specs: Dict[AgentType, Dict[str, Any]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]] = None,
    ) -> None:
        serialized = {
            atype.value: dict(spec or {})
            for atype, spec in (task_specs or {}).items()
            if isinstance(spec, dict)
        }
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.task_specs",
            serialized,
        )
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.conditional_tasks",
            dict(conditional_task_specs or {}),
        )
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.activation_pool",
            {
                "route_source": "orchestrator.llm_task_spec",
                "active_agents": [
                    atype.value
                    for atype in self.build_execution_queue(
                        task_specs=task_specs,
                        candidate_agents=candidate_agents,
                    )
                ],
                "standby_agents": [
                    atype.value
                    for atype in self.build_standby_agents(
                        task_specs=task_specs,
                        candidate_agents=candidate_agents,
                    )
                ],
            },
        )

    def persist_runtime_activation(
        self,
        *,
        workflow_state_id: str,
        agent_type: AgentType,
        reason: str,
        active_agents: Optional[List[AgentType]] = None,
        standby_agents: Optional[List[AgentType]] = None,
    ) -> Dict[str, Any]:
        route = {
            "route_source": "control_plane.runtime_activation",
            "workflow_state_id": str(workflow_state_id or ""),
            "decision_reason": str(reason or "adaptive_replan"),
            "activated_agent": agent_type.value,
        }
        activation_payload = {
            "route_source": "control_plane.runtime_activation",
            "workflow_state_id": str(workflow_state_id or ""),
            "decision_reason": str(reason or "adaptive_replan"),
            "active_agents": [agent.value for agent in (active_agents or [])],
            "standby_agents": [agent.value for agent in (standby_agents or [])],
        }
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.audio_route",
            dict(route),
        )
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.activation_pool",
            activation_payload,
        )
        return {
            "route_payload": dict(route),
            "activation_payload": activation_payload,
        }

    def append_replan_trace(self, *, workflow_state_id: str, record: Dict[str, Any]) -> None:
        trace = read_shared_fact(
            workflow_state_id,
            "workflow.replan_trace",
            [],
            service=self._memory_services.short_term,
        ) or []
        if not isinstance(trace, list):
            trace = []
        trace.append(dict(record or {}))
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.replan_trace",
            trace,
        )

"""
Control-plane owner for runtime decision requests and explicit apply payloads.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import AgentType
from .audio_delivery_gate_evaluator import AudioDeliveryGateEvaluator
from .memory_provider import MemoryServices, build_memory_services
from .orchestration_observation_adapter import OrchestrationObservationAdapter
from .orchestration_protocol import OrchestrationProtocol
from .orchestration_runtime_controller import OrchestrationRuntimeController
from .orchestration_state_adapter import OrchestrationStateAdapter


class OrchestrationControlPlaneError(RuntimeError):
    """Raised when runtime control-plane inputs violate explicit contracts."""


_GATE_AUTHORITY = {
    "workflow_video_audio_delivery": {
        (AgentType.VIDEO_GENERATOR, "scene_video_completed"),
    },
    "workflow_global_bgm_mix_delivery": {
        (AgentType.VIDEO_COMPOSER, "compose_completed"),
    },
}


class OrchestrationControlPlane:
    """Owns boundary-triggered gate collection and explicit apply payload assembly."""

    def __init__(
        self,
        *,
        memory_services: Optional[MemoryServices] = None,
        protocol: Optional[OrchestrationProtocol] = None,
        orchestration_state: Optional[OrchestrationStateAdapter] = None,
        audio_delivery_gate: Optional[AudioDeliveryGateEvaluator] = None,
        observation_adapter: Optional[OrchestrationObservationAdapter] = None,
        runtime_controller: Optional[OrchestrationRuntimeController] = None,
    ) -> None:
        self._memory_services = memory_services or build_memory_services()
        self._protocol = protocol or OrchestrationProtocol()
        self._orchestration_state = orchestration_state or OrchestrationStateAdapter(
            self._memory_services
        )
        self._audio_delivery_gate = audio_delivery_gate or AudioDeliveryGateEvaluator(
            memory_services=self._memory_services
        )
        self._observation_adapter = observation_adapter or OrchestrationObservationAdapter(
            self._memory_services
        )
        self._runtime_controller = runtime_controller or OrchestrationRuntimeController(
            memory_services=self._memory_services,
            orchestration_state=self._orchestration_state,
        )
        self._gate_handlers = {
            "workflow_video_audio_delivery": self._evaluate_workflow_video_audio_delivery,
            "workflow_global_bgm_mix_delivery": self._evaluate_workflow_global_bgm_mix_delivery,
        }

    def _collect_boundary_gate_events(
        self,
        *,
        workflow_state_id: str,
        current_agent: AgentType,
        report: Dict[str, Any],
        audio_contract: Optional[Dict[str, Any]],
        execution_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        gate_events: List[Dict[str, Any]] = []
        contract = dict(audio_contract or {})
        requested_gates = (report or {}).get("gate_triggers")
        if not isinstance(requested_gates, list):
            requested_gates = []
        boundary_event_raw = (report or {}).get("boundary_event")
        boundary_event = boundary_event_raw if isinstance(boundary_event_raw, str) else ""

        for gate_name in requested_gates:
            gate_key = str(gate_name or "").strip()
            handler = self._gate_handlers.get(gate_key)
            if handler is None:
                raise OrchestrationControlPlaneError(
                    f"Unknown gate trigger: {gate_key or '<empty>'}"
                )
            allowed_contexts = _GATE_AUTHORITY.get(gate_key) or set()
            if (current_agent, boundary_event) not in allowed_contexts:
                raise OrchestrationControlPlaneError(
                    "Unauthorized gate trigger: "
                    f"{gate_key} for agent={current_agent.value} "
                    f"boundary_event={boundary_event or '<empty>'}"
                )
            gate_result = handler(
                workflow_state_id=workflow_state_id,
                report=report,
                audio_contract=contract,
                execution_id=execution_id,
            )
            if isinstance(gate_result, dict) and gate_result:
                gate_events.append(gate_result)

        return gate_events

    def _evaluate_workflow_video_audio_delivery(
        self,
        *,
        workflow_state_id: str,
        report: Dict[str, Any],
        audio_contract: Dict[str, Any],
        execution_id: Optional[str],
    ) -> Dict[str, Any]:
        route_payload = self._observation_adapter.build_audio_route_payload(
            workflow_state_id=workflow_state_id,
            route={},
            contract=audio_contract,
            should_run=True,
            decision_basis="boundary_trigger",
            execution_id=execution_id,
        )
        gate_result = self._audio_delivery_gate.evaluate_workflow_video_audio(
            workflow_state_id
        )
        self._observation_adapter.persist_audio_gate_observation(
            workflow_state_id=workflow_state_id,
            route_payload=route_payload,
            gate_result=gate_result,
        )
        return gate_result

    def _evaluate_workflow_global_bgm_mix_delivery(
        self,
        *,
        workflow_state_id: str,
        report: Dict[str, Any],
        audio_contract: Dict[str, Any],
        execution_id: Optional[str],
    ) -> Dict[str, Any]:
        if not bool(audio_contract.get("need_global_bgm")):
            return {}
        return self._audio_delivery_gate.evaluate_global_bgm_mix_delivery(workflow_state_id)

    def open_runtime_decision(
        self,
        *,
        workflow_state_id: str,
        current_agent: AgentType,
        standby_agents: List[AgentType],
        report: Dict[str, Any],
        audio_contract: Optional[Dict[str, Any]],
        replan_count: int,
        max_replans: int,
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        gate_events = self._collect_boundary_gate_events(
            workflow_state_id=workflow_state_id,
            current_agent=current_agent,
            report=report,
            audio_contract=audio_contract,
            execution_id=execution_id,
        )
        if not gate_events:
            return {
                "status": "no_gate",
                "reason": "no_boundary_gate_event",
                "apply_result": {
                    "status": "continue",
                    "reason": "no_boundary_gate_event",
                    "replan_count": int(replan_count),
                },
                "decision_ack": {},
            }
        return {
            "status": "ready",
            "decision_request": self._protocol.build_runtime_decision_request(
                workflow_state_id=workflow_state_id,
                current_agent=current_agent,
                standby_agents=standby_agents,
                report=report,
                gate_events=gate_events,
                replan_count=replan_count,
                max_replans=max_replans,
            ),
        }

    def _build_apply_payload(
        self,
        *,
        runtime_decision: Dict[str, Any],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        current_index: int,
        execution_queue: List[AgentType],
        task_specs: Dict[AgentType, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]],
        standby_agents: List[AgentType],
        replan_count: int,
    ) -> Dict[str, Any]:
        if not isinstance(runtime_decision, dict):
            raise OrchestrationControlPlaneError("runtime_decision must be a dict")

        action_raw = runtime_decision.get("action")
        if not isinstance(action_raw, str) or not action_raw.strip():
            raise OrchestrationControlPlaneError("runtime_decision missing action")
        action = action_raw.strip()
        reason = str(runtime_decision.get("reason") or "none").strip()
        facts = runtime_decision.get("facts")
        apply_payload: Dict[str, Any] = {
            "action": action,
            "reason": reason,
            "facts": facts if isinstance(facts, dict) else {},
            "replan_count": int(replan_count),
        }

        if action not in {"continue", "activate_from_standby", "abort"}:
            raise OrchestrationControlPlaneError(f"Unsupported runtime action: {action}")

        if action != "activate_from_standby":
            return apply_payload

        target_agent = runtime_decision.get("target_agent")
        if not isinstance(target_agent, AgentType):
            raise OrchestrationControlPlaneError(
                "activate_from_standby requires target_agent as AgentType"
            )

        current_spec = task_specs.get(target_agent)
        if not isinstance(current_spec, dict):
            raise OrchestrationControlPlaneError(
                f"Target agent {target_agent.value} missing preplanned task_spec"
            )

        updated_queue = list(execution_queue or [])
        queue_changed = self._orchestration_state.insert_agent_into_execution_queue(
            updated_queue,
            current_index=current_index,
            agent_type=target_agent,
            task_specs=task_specs,
            candidate_agents=candidate_agents,
        )
        updated_task_specs: Dict[AgentType, Dict[str, Any]] = {
            atype: dict(spec or {})
            for atype, spec in (task_specs or {}).items()
            if isinstance(spec, dict)
        }
        conditional_spec = self._resolve_conditional_task_spec(
            target_agent=target_agent,
            runtime_decision=runtime_decision,
            conditional_task_specs=conditional_task_specs,
        )
        target_spec = dict(updated_task_specs.get(target_agent) or {})
        if isinstance(conditional_spec, dict):
            for key in (
                "mission",
                "deliverable",
                "constraints",
                "runtime_hints",
            ):
                if conditional_spec.get(key) is not None:
                    target_spec[key] = conditional_spec.get(key)
            if conditional_spec.get("task_id") is not None:
                target_spec["conditional_task_id"] = conditional_spec.get("task_id")
            if conditional_spec.get("trigger") is not None:
                target_spec["trigger"] = conditional_spec.get("trigger")
        target_spec["run"] = True
        updated_task_specs[target_agent] = target_spec
        updated_standby_agents = [
            candidate for candidate in (standby_agents or []) if candidate != target_agent
        ]
        apply_payload.update(
            {
                "target_agent": target_agent,
                "task_specs": updated_task_specs,
                "candidate_agents": list(candidate_agents or []),
                "execution_queue": updated_queue,
                "standby_agents": updated_standby_agents,
                "queue_changed": bool(queue_changed),
                "replan_count": int(replan_count) + 1,
            }
        )
        return apply_payload

    def _resolve_conditional_task_spec(
        self,
        *,
        target_agent: AgentType,
        runtime_decision: Dict[str, Any],
        conditional_task_specs: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(conditional_task_specs, dict) or not conditional_task_specs:
            return None

        requested_task_id = runtime_decision.get("task_id")
        if not isinstance(requested_task_id, str) or not requested_task_id.strip():
            facts = runtime_decision.get("facts")
            if isinstance(facts, dict):
                llm_output = facts.get("llm_output")
                if isinstance(llm_output, dict):
                    requested_task_id = llm_output.get("task_id")
        selected_task_id = (
            str(requested_task_id).strip()
            if isinstance(requested_task_id, str) and requested_task_id.strip()
            else ""
        )

        if selected_task_id:
            selected_spec = conditional_task_specs.get(selected_task_id)
            if not isinstance(selected_spec, dict):
                raise OrchestrationControlPlaneError(
                    f"Conditional task {selected_task_id} not found for runtime activation"
                )
            selected_agent = str(selected_spec.get("agent") or "").strip().lower()
            if selected_agent != target_agent.value:
                raise OrchestrationControlPlaneError(
                    "Conditional task agent mismatch: "
                    f"{selected_task_id} targets {selected_agent or '<empty>'}, "
                    f"expected {target_agent.value}"
                )
            merged = dict(selected_spec)
            merged["task_id"] = selected_task_id
            return merged

        matching_specs = []
        for task_id, spec in conditional_task_specs.items():
            if not isinstance(spec, dict):
                continue
            if str(spec.get("agent") or "").strip().lower() != target_agent.value:
                continue
            merged = dict(spec)
            merged["task_id"] = str(task_id)
            matching_specs.append(merged)

        if not matching_specs:
            return None
        if len(matching_specs) > 1:
            raise OrchestrationControlPlaneError(
                f"Multiple conditional task_specs found for target agent {target_agent.value}; "
                "runtime_decision must include task_id"
            )
        return matching_specs[0]

    def apply_runtime_decision(
        self,
        *,
        workflow_state_id: str,
        current_agent: AgentType,
        current_index: int,
        runtime_decision: Dict[str, Any],
        execution_queue: List[AgentType],
        task_specs: Dict[AgentType, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        standby_agents: List[AgentType],
        replan_count: int,
    ) -> Dict[str, Any]:
        apply_payload = self._build_apply_payload(
            runtime_decision=runtime_decision,
            conditional_task_specs=conditional_task_specs,
            current_index=current_index,
            execution_queue=execution_queue,
            task_specs=task_specs,
            candidate_agents=candidate_agents,
            standby_agents=standby_agents,
            replan_count=replan_count,
        )
        apply_result = self._runtime_controller.apply_runtime_decision(
            workflow_state_id=workflow_state_id,
            current_agent=current_agent,
            conditional_task_specs=conditional_task_specs,
            apply_payload=apply_payload,
        )
        return {
            "apply_result": apply_result,
            "decision_ack": self._protocol.build_runtime_decision_ack(
                workflow_state_id=workflow_state_id,
                current_agent=current_agent,
                runtime_decision=runtime_decision,
                apply_result=apply_result,
            ),
        }

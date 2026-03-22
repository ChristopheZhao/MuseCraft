"""
Control-plane owner for applying orchestrator runtime decisions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..models import AgentType
from .memory_provider import MemoryServices, build_memory_services
from .orchestration_state_adapter import OrchestrationStateAdapter


class OrchestrationRuntimeControllerError(RuntimeError):
    """Raised when explicit runtime apply payloads violate controller contracts."""


class OrchestrationRuntimeController:
    """Applies runtime decisions outside orchestrator main-loop ownership."""

    def __init__(
        self,
        memory_services: Optional[MemoryServices] = None,
        orchestration_state: Optional[OrchestrationStateAdapter] = None,
    ) -> None:
        self._memory_services = memory_services or build_memory_services()
        self._orchestration_state = orchestration_state or OrchestrationStateAdapter(
            self._memory_services
        )

    def apply_runtime_decision(
        self,
        *,
        workflow_state_id: str,
        current_agent: AgentType,
        conditional_task_specs: Dict[str, Dict[str, Any]],
        apply_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(apply_payload, dict):
            raise OrchestrationRuntimeControllerError("apply_payload must be a dict")

        action_raw = apply_payload.get("action")
        if not isinstance(action_raw, str) or not action_raw.strip():
            raise OrchestrationRuntimeControllerError("apply_payload missing action")
        action = action_raw.strip()
        reason = str(apply_payload.get("reason") or "none").strip()
        facts = apply_payload.get("facts") if isinstance(apply_payload, dict) else {}
        replan_count = int(apply_payload.get("replan_count") or 0)

        if action not in {"continue", "activate_from_standby", "abort"}:
            raise OrchestrationRuntimeControllerError(f"Unsupported apply action: {action}")

        if action == "activate_from_standby":
            target_agent = apply_payload.get("target_agent")
            if not isinstance(target_agent, AgentType):
                raise OrchestrationRuntimeControllerError(
                    "activate_from_standby requires target_agent as AgentType"
                )

            task_specs = apply_payload.get("task_specs")
            candidate_agents = apply_payload.get("candidate_agents")
            execution_queue = apply_payload.get("execution_queue")
            standby_agents = apply_payload.get("standby_agents")
            queue_changed = bool(apply_payload.get("queue_changed"))

            if not isinstance(task_specs, dict):
                raise OrchestrationRuntimeControllerError(
                    "activate_from_standby requires explicit task_specs payload"
                )
            if not isinstance(execution_queue, list):
                raise OrchestrationRuntimeControllerError(
                    "activate_from_standby requires explicit execution_queue payload"
                )
            if not isinstance(standby_agents, list):
                raise OrchestrationRuntimeControllerError(
                    "activate_from_standby requires explicit standby_agents payload"
                )

            self._orchestration_state.persist_task_specs(
                workflow_state_id=workflow_state_id,
                task_specs=task_specs,
                conditional_task_specs=conditional_task_specs,
                candidate_agents=(
                    candidate_agents if isinstance(candidate_agents, list) else None
                ),
            )
            self._orchestration_state.persist_runtime_activation(
                workflow_state_id=workflow_state_id,
                agent_type=target_agent,
                reason=reason,
                active_agents=execution_queue,
                standby_agents=standby_agents,
            )
            trace_record = {
                "at": datetime.now(timezone.utc).isoformat(),
                "trigger_agent": current_agent.value,
                "action": "activate_from_standby",
                "target_agent": target_agent.value,
                "reason": reason,
                "replan_count": replan_count,
                "queue_changed": bool(queue_changed),
                "facts": facts if isinstance(facts, dict) else {},
            }
            self._orchestration_state.append_replan_trace(
                workflow_state_id=workflow_state_id,
                record=trace_record,
            )
            return {
                "status": "activated",
                "target_agent": target_agent,
                "execution_queue": execution_queue,
                "task_specs": task_specs,
                "queue_changed": bool(queue_changed),
                "standby_agents": standby_agents,
                "replan_count": replan_count,
                "trace_record": trace_record,
            }

        if action == "abort":
            trace_record = {
                "at": datetime.now(timezone.utc).isoformat(),
                "trigger_agent": current_agent.value,
                "action": "abort",
                "reason": reason,
                "replan_count": replan_count,
                "facts": facts if isinstance(facts, dict) else {},
            }
            self._orchestration_state.append_replan_trace(
                workflow_state_id=workflow_state_id,
                record=trace_record,
            )
            return {
                "status": "abort",
                "reason": reason,
                "replan_count": replan_count,
                "trace_record": trace_record,
            }

        return {
            "status": "continue",
            "reason": reason,
            "replan_count": replan_count,
        }

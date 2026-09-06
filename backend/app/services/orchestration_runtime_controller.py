"""
Control-plane owner for applying orchestrator runtime decisions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..domain import AgentType
from .memory_provider import MemoryServices
from .orchestration_runtime_decision import RuntimeAction
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
        if memory_services is None:
            raise ValueError("memory_services is required for OrchestrationRuntimeController")
        self._memory_services = memory_services
        self._orchestration_state = orchestration_state or OrchestrationStateAdapter(
            memory_services=self._memory_services
        )

    def apply_runtime_decision(
        self,
        *,
        workflow_state_id: str,
        current_agent: AgentType,
        apply_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(apply_payload, dict):
            raise OrchestrationRuntimeControllerError("apply_payload must be a dict")

        action = apply_payload.get("action")
        if not isinstance(action, RuntimeAction):
            raise OrchestrationRuntimeControllerError("apply_payload.action must be RuntimeAction")
        reason = apply_payload.get("reason")
        if type(reason) is not str or not reason or reason != reason.strip():
            raise OrchestrationRuntimeControllerError(
                "apply_payload.reason must be a canonical non-empty string"
            )
        facts = apply_payload.get("facts")
        if not isinstance(facts, dict):
            raise OrchestrationRuntimeControllerError("apply_payload.facts must be a JSON object")
        replan_count = apply_payload.get("replan_count")
        if type(replan_count) is not int or replan_count < 0:
            raise OrchestrationRuntimeControllerError(
                "apply_payload.replan_count must be a non-negative integer"
            )

        if action is RuntimeAction.ACTIVATE_FROM_STANDBY:
            target_agent = apply_payload.get("target_agent")
            if not isinstance(target_agent, AgentType):
                raise OrchestrationRuntimeControllerError(
                    "activate_from_standby requires target_agent as AgentType"
                )

            task_specs = apply_payload.get("task_specs")
            candidate_agents = apply_payload.get("candidate_agents")
            execution_queue = apply_payload.get("execution_queue")
            standby_agents = apply_payload.get("standby_agents")
            queue_changed = apply_payload.get("queue_changed")

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
            if type(queue_changed) is not bool:
                raise OrchestrationRuntimeControllerError(
                    "activate_from_standby requires queue_changed as boolean"
                )

            trace_record = {
                "at": datetime.now(timezone.utc).isoformat(),
                "trigger_agent": current_agent.value,
                "action": RuntimeAction.ACTIVATE_FROM_STANDBY.value,
                "target_agent": target_agent.value,
                "reason": reason,
                "replan_count": replan_count,
                "queue_changed": queue_changed,
                "facts": dict(facts),
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
                "queue_changed": queue_changed,
                "standby_agents": standby_agents,
                "replan_count": replan_count,
                "trace_record": trace_record,
            }

        if action in {
            RuntimeAction.RETRY_CURRENT,
            RuntimeAction.ACCEPT_WITH_GAPS,
            RuntimeAction.ABORT,
        }:
            trace_record = {
                "at": datetime.now(timezone.utc).isoformat(),
                "trigger_agent": current_agent.value,
                "action": action.value,
                "reason": reason,
                "replan_count": replan_count,
                "facts": dict(facts),
            }
            self._orchestration_state.append_replan_trace(
                workflow_state_id=workflow_state_id,
                record=trace_record,
            )
            status_by_action = {
                RuntimeAction.RETRY_CURRENT: "retry",
                RuntimeAction.ACCEPT_WITH_GAPS: "accepted_with_gaps",
                RuntimeAction.ABORT: "abort",
            }
            return {
                "status": status_by_action[action],
                "reason": reason,
                "replan_count": replan_count,
                "trace_record": trace_record,
            }

        if action is RuntimeAction.CONTINUE:
            return {
                "status": "continue",
                "reason": reason,
                "replan_count": replan_count,
            }
        raise OrchestrationRuntimeControllerError(
            f"apply_payload.action is not executable: {action.value}"
        )

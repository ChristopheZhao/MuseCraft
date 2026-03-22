"""
Master-worker communication protocol for orchestrator runtime decisions.

This module defines protocol message envelopes between:
- orchestrator -> subagent dispatch
- subagent -> orchestrator report
- orchestrator -> control-plane runtime decision request
- control-plane -> orchestrator/runtime apply acknowledgement

It deliberately does not trigger gates or make orchestration decisions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import AgentType


class OrchestrationProtocolError(ValueError):
    """Raised when a subagent violates the explicit orchestration protocol."""


class OrchestrationProtocol:
    """Owns protocol envelopes, not orchestration policy or gate execution."""

    @staticmethod
    def _require_report_field(
        explicit_report: Dict[str, Any],
        *,
        field_name: str,
        agent_type: AgentType,
    ) -> Any:
        if field_name not in explicit_report:
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report missing field: {field_name}"
            )
        return explicit_report.get(field_name)

    @staticmethod
    def _validate_reflection(
        reflection: Dict[str, Any],
        *,
        agent_type: AgentType,
    ) -> Dict[str, Any]:
        completion_state = OrchestrationProtocol._require_report_field(
            reflection,
            field_name="completion_state",
            agent_type=agent_type,
        )
        if not isinstance(completion_state, str) or not completion_state.strip():
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report reflection.completion_state "
                "must be a non-empty string"
            )

        reported_gaps = OrchestrationProtocol._require_report_field(
            reflection,
            field_name="reported_gaps",
            agent_type=agent_type,
        )
        if not isinstance(reported_gaps, list) or any(
            not isinstance(item, str) for item in reported_gaps
        ):
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report reflection.reported_gaps "
                "must be list[str]"
            )

        reported_hints = OrchestrationProtocol._require_report_field(
            reflection,
            field_name="reported_hints",
            agent_type=agent_type,
        )
        if not isinstance(reported_hints, list) or any(
            not isinstance(item, str) for item in reported_hints
        ):
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report reflection.reported_hints "
                "must be list[str]"
            )

        if "summary" in reflection and not isinstance(reflection.get("summary"), str):
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report reflection.summary "
                "must be a string when present"
            )

        return dict(reflection)

    @staticmethod
    def _default_reflection(agent_output: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        output = dict(agent_output or {})
        reflection: Dict[str, Any] = {
            "completion_state": "completed",
            "reported_gaps": [],
            "reported_hints": [],
        }
        if isinstance(output.get("subtask_state"), str) and output.get("subtask_state"):
            reflection["completion_state"] = str(output.get("subtask_state"))
        if isinstance(output.get("completed_reason"), str) and output.get("completed_reason"):
            reflection["completed_reason"] = str(output.get("completed_reason"))
        if isinstance(output.get("reflection_summary"), str) and output.get("reflection_summary"):
            reflection["summary"] = str(output.get("reflection_summary"))
        return reflection

    def build_dispatch(
        self,
        *,
        workflow_state_id: str,
        agent_type: AgentType,
        task_spec: Optional[Dict[str, Any]],
        execution_contract: Optional[Dict[str, Any]],
        execution_order: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {
            "contract_version": "v1",
            "workflow_state_id": str(workflow_state_id or ""),
            "agent_type": agent_type.value,
            "task_spec": dict(task_spec or {}),
            "execution_contract": dict(execution_contract or {}),
            "execution_order": execution_order,
        }

    def build_subagent_report(
        self,
        *,
        workflow_state_id: str,
        agent_type: AgentType,
        agent_output: Optional[Dict[str, Any]],
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        output = dict(agent_output or {})
        explicit_report = output.get("orchestration_report")
        if not isinstance(explicit_report, dict) or not explicit_report:
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} must return explicit orchestration_report"
            )
        report: Dict[str, Any] = {
            "contract_version": "v1",
            "workflow_state_id": str(workflow_state_id or ""),
            "agent_type": agent_type.value,
            "execution_id": execution_id,
            "status": "completed" if output.get("success", True) else "partial",
            "boundary_event": "",
            "gate_triggers": [],
            "artifacts": [],
            "reflection": self._default_reflection(output),
        }

        status = self._require_report_field(
            explicit_report,
            field_name="status",
            agent_type=agent_type,
        )
        if not isinstance(status, str) or not status.strip():
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report field status "
                "must be a non-empty string"
            )
        report["status"] = status.strip()

        boundary_event = self._require_report_field(
            explicit_report,
            field_name="boundary_event",
            agent_type=agent_type,
        )
        if not isinstance(boundary_event, str):
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report field boundary_event "
                "must be a string"
            )
        report["boundary_event"] = boundary_event.strip()

        gate_triggers = self._require_report_field(
            explicit_report,
            field_name="gate_triggers",
            agent_type=agent_type,
        )
        if not isinstance(gate_triggers, list):
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report field gate_triggers "
                "must be list[str]"
            )
        normalized_gate_triggers: List[str] = []
        for index, item in enumerate(gate_triggers):
            if not isinstance(item, str) or not item.strip():
                raise OrchestrationProtocolError(
                    f"Subagent {agent_type.value} orchestration_report gate_triggers[{index}] "
                    "must be a non-empty string"
                )
            normalized_gate_triggers.append(item.strip())
        report["gate_triggers"] = normalized_gate_triggers

        artifacts = self._require_report_field(
            explicit_report,
            field_name="artifacts",
            agent_type=agent_type,
        )
        if not isinstance(artifacts, list):
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report field artifacts "
                "must be list[dict]"
            )
        normalized_artifacts: List[Dict[str, Any]] = []
        for index, item in enumerate(artifacts):
            if not isinstance(item, dict):
                raise OrchestrationProtocolError(
                    f"Subagent {agent_type.value} orchestration_report artifacts[{index}] "
                    "must be a dict"
                )
            normalized_artifacts.append(dict(item))
        report["artifacts"] = normalized_artifacts

        reflection = self._require_report_field(
            explicit_report,
            field_name="reflection",
            agent_type=agent_type,
        )
        if not isinstance(reflection, dict):
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report field reflection "
                "must be a dict"
            )
        merged_reflection = dict(report["reflection"])
        merged_reflection.update(
            self._validate_reflection(reflection, agent_type=agent_type)
        )
        report["reflection"] = merged_reflection
        return report

    def build_runtime_decision_request(
        self,
        *,
        workflow_state_id: str,
        current_agent: AgentType,
        standby_agents: List[AgentType],
        report: Optional[Dict[str, Any]],
        gate_events: List[Dict[str, Any]],
        replan_count: int,
        max_replans: int,
    ) -> Dict[str, Any]:
        return {
            "contract_version": "v1",
            "workflow_state_id": str(workflow_state_id or ""),
            "current_agent": current_agent.value,
            "report": dict(report or {}),
            "standby_candidates": [agent.value for agent in standby_agents],
            "gate_events": list(gate_events or []),
            "replan_budget": {
                "used": int(replan_count),
                "max": int(max_replans),
            },
        }

    def build_runtime_decision_ack(
        self,
        *,
        workflow_state_id: str,
        current_agent: AgentType,
        runtime_decision: Dict[str, Any],
        apply_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "contract_version": "v1",
            "workflow_state_id": str(workflow_state_id or ""),
            "current_agent": current_agent.value,
            "decision": dict(runtime_decision or {}),
            "apply_result": dict(apply_result or {}),
        }

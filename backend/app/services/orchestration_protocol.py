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

from ..domain import AgentExecutionContractError, AgentExecutionResult, AgentType


class OrchestrationProtocolError(ValueError):
    """Raised when a subagent violates the explicit orchestration protocol."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "orchestration_report_invalid",
        field_path: str = "orchestration_report",
    ) -> None:
        self.reason_code = str(reason_code)
        self.field_path = str(field_path)
        super().__init__(message)


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
        agent_result: AgentExecutionResult,
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(agent_result, AgentExecutionResult):
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} must return AgentExecutionResult"
            )
        try:
            explicit_report = agent_result.require_orchestration_report().to_dict()
        except AgentExecutionContractError as exc:
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} must return explicit orchestration_report: {exc}",
                reason_code=exc.reason_code.value,
                field_path=exc.field_path,
            ) from exc
        report: Dict[str, Any] = {
            "contract_version": "v1",
            "workflow_state_id": str(workflow_state_id or ""),
            "agent_type": agent_type.value,
            "execution_id": execution_id,
        }

        status = self._require_report_field(
            explicit_report,
            field_name="status",
            agent_type=agent_type,
        )
        if not isinstance(status, str):
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report field status "
                "must be a string",
                reason_code="orchestration_report_status_invalid",
                field_path="orchestration_report.status",
            )
        if status not in {"completed", "partial", "failed"}:
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report field status "
                "must be a canonical outcome value",
                reason_code="orchestration_report_status_invalid",
                field_path="orchestration_report.status",
            )
        if status != "completed":
            raise OrchestrationProtocolError(
                f"Subagent {agent_type.value} orchestration_report status must be completed "
                "before runtime success finalization",
                reason_code="orchestration_report_not_successful",
                field_path="orchestration_report.status",
            )
        report["status"] = status

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
        report["boundary_event"] = boundary_event

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
            if not isinstance(item, str) or not item:
                raise OrchestrationProtocolError(
                    f"Subagent {agent_type.value} orchestration_report gate_triggers[{index}] "
                    "must be a non-empty string"
                )
            normalized_gate_triggers.append(item)
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
        normalized_reflection = dict(reflection)
        normalized_reflection.pop("completion_state", None)
        report["reflection"] = normalized_reflection
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

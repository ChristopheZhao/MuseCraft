"""Thin validation shared by agent-specific execution-contract consumers."""

from __future__ import annotations

from typing import Any, Collection, Dict, Mapping

from ..domain import (
    AgentExecutionContractError,
    AgentExecutionContractReason,
    JsonObjectPayload,
)


_RETIRED_REDUNDANT_FIELDS = ("scope", "inputs", "storage")


def require_agent_execution_contract(
    payload: Any,
    *,
    expected_agent: str,
    expected_workflow_state_id: str,
    allowed_fields: Collection[str],
) -> Dict[str, Any]:
    """Return a JSON-safe execution envelope without inventing missing intent."""
    if not isinstance(payload, Mapping) or not isinstance(
        payload.get("execution_contract"), Mapping
    ):
        raise AgentExecutionContractError(
            reason_code=AgentExecutionContractReason.EXECUTION_CONTRACT_MISSING,
            field_path="execution_contract",
            message="execution_contract is required",
        )

    contract = JsonObjectPayload.from_mapping(
        payload["execution_contract"],
        field_path="execution_contract",
    ).to_dict()
    if contract.get("contract_version") != "v1":
        _invalid("execution_contract.contract_version", "expected contract_version 'v1'")
    if contract.get("agent") != expected_agent:
        _invalid(
            "execution_contract.agent",
            f"expected agent {expected_agent!r}",
        )
    expected_workflow_id = expected_workflow_state_id
    if (
        type(expected_workflow_id) is not str
        or not expected_workflow_id
        or expected_workflow_id != expected_workflow_id.strip()
    ):
        _invalid(
            "workflow_state_id",
            "expected_workflow_state_id must be a canonical non-empty string",
        )
    contract_workflow_id = contract.get("workflow_state_id")
    if (
        type(contract_workflow_id) is not str
        or not contract_workflow_id
        or contract_workflow_id != contract_workflow_id.strip()
    ):
        _invalid(
            "execution_contract.workflow_state_id",
            "expected a canonical non-empty workflow_state_id",
        )
    if contract_workflow_id != expected_workflow_id:
        _invalid(
            "execution_contract.workflow_state_id",
            "workflow_state_id does not match the active execution boundary",
        )
    operation = contract.get("operation")
    if type(operation) is not str or not operation or operation != operation.strip():
        _invalid("execution_contract.operation", "expected a canonical operation string")
    for field_name in _RETIRED_REDUNDANT_FIELDS:
        if field_name in contract:
            _invalid(
                f"execution_contract.{field_name}",
                f"redundant execution contract field {field_name!r} is not supported",
            )
    unexpected_fields = sorted(set(contract).difference(allowed_fields))
    if unexpected_fields:
        _invalid(
            f"execution_contract.{unexpected_fields[0]}",
            f"unexpected execution contract field {unexpected_fields[0]!r}",
        )
    if "constraints" in contract and not isinstance(contract.get("constraints"), dict):
        _invalid(
            "execution_contract.constraints",
            "constraints must be a JSON object when provided",
        )
    return contract


def _invalid(field_path: str, message: str) -> None:
    raise AgentExecutionContractError(
        reason_code=AgentExecutionContractReason.EXECUTION_CONTRACT_INVALID,
        field_path=field_path,
        message=message,
    )

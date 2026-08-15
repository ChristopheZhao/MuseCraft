"""Thin validation shared by agent-specific execution-contract consumers."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from ..domain import (
    AgentExecutionContractError,
    AgentExecutionContractReason,
    JsonObjectPayload,
)


_REQUIRED_OBJECT_FIELDS = ("scope", "inputs", "constraints", "storage")


def require_agent_execution_contract(
    payload: Any,
    *,
    expected_agent: str,
) -> Dict[str, Any]:
    """Return a JSON-safe execution envelope without inventing missing intent."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("execution_contract"), Mapping):
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
    operation = contract.get("operation")
    if type(operation) is not str or not operation or operation != operation.strip():
        _invalid("execution_contract.operation", "expected a canonical operation string")
    for field_name in _REQUIRED_OBJECT_FIELDS:
        if not isinstance(contract.get(field_name), dict):
            _invalid(
                f"execution_contract.{field_name}",
                f"expected {field_name} to be a JSON object",
            )
    return contract


def _invalid(field_path: str, message: str) -> None:
    raise AgentExecutionContractError(
        reason_code=AgentExecutionContractReason.EXECUTION_CONTRACT_INVALID,
        field_path=field_path,
        message=message,
    )

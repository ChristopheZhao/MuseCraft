"""Application-side assembly for persistence-free Agent execution requests."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from ..domain import (
    AgentExecutionContractError,
    AgentExecutionContractReason,
    AgentExecutionRequest,
    AgentTaskReference,
    AgentType,
    JsonObjectPayload,
)
from ..models import Task


def build_agent_execution_request(
    *,
    task: Task,
    agent_type: AgentType,
    input_data: Mapping[str, object],
    execution_order: int,
) -> AgentExecutionRequest:
    task_type = getattr(task.task_type, "value", task.task_type)
    workflow_state_id = str(input_data.get("workflow_state_id") or task.task_id)
    return AgentExecutionRequest(
        task=AgentTaskReference(
            task_id=str(task.task_id),
            task_type=str(task_type),
            user_id=(str(task.user_id) if task.user_id is not None else None),
            session_id=(str(task.session_id) if task.session_id is not None else None),
        ),
        agent_type=agent_type.value,
        input_data=JsonObjectPayload.from_mapping(
            input_data,
            field_path="agent_execution.input_data",
        ),
        workflow_state_id=workflow_state_id,
        execution_order=execution_order,
    )


def require_canonical_execution_status(
    payload: Mapping[str, object],
    *,
    field_path: str,
    allowed_statuses: Collection[str],
) -> str:
    """Validate an explicit execution status without inferring completion."""

    if not isinstance(payload, Mapping):
        raise AgentExecutionContractError(
            reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
            field_path=field_path,
            message="execution result must be a JSON object",
        )
    status = payload.get("status")
    if type(status) is not str or not status or status != status.strip():
        raise AgentExecutionContractError(
            reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
            field_path=field_path,
            message="execution status must be an explicit canonical string",
        )
    allowed = frozenset(allowed_statuses)
    if status not in allowed:
        raise AgentExecutionContractError(
            reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
            field_path=field_path,
            message=f"unsupported execution status {status!r}",
        )
    return status

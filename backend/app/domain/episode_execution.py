"""Persistence-independent port for executing one project episode workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .agent_execution import (
    AgentExecutionContractError,
    AgentExecutionContractReason,
    AgentExecutionResult,
    AgentTaskReference,
    JsonObjectPayload,
)


@dataclass(frozen=True, slots=True)
class EpisodeWorkflowExecutionReceipt:
    task_id: str
    result: AgentExecutionResult

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_IDENTIFIER,
                field_path="episode_execution.task_id",
                message="expected a non-empty string",
            )
        if not isinstance(self.result, AgentExecutionResult):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
                field_path="episode_execution.result",
                message="expected AgentExecutionResult",
            )
        object.__setattr__(self, "task_id", self.task_id.strip())


class EpisodeWorkflowExecutionPort(Protocol):
    async def execute_episode(
        self,
        *,
        parent_task: AgentTaskReference,
        title: str,
        description: str,
        input_data: JsonObjectPayload,
        execution_order: int,
    ) -> EpisodeWorkflowExecutionReceipt:
        ...

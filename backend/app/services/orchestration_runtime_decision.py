"""Canonical runtime disposition produced once at the LLM JSON boundary."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..domain import AgentExecutionContractError, AgentType, JsonObjectPayload


class RuntimeAction(str, Enum):
    CONTINUE = "continue"
    RETRY_CURRENT = "retry_current"
    ACTIVATE_FROM_STANDBY = "activate_from_standby"
    ACCEPT_WITH_GAPS = "accept_with_gaps"
    ABORT = "abort"


class RuntimeDecisionContractError(ValueError):
    """Raised when the single parsed runtime decision is not canonical."""


@dataclass(frozen=True)
class RuntimeDecision(Mapping[str, Any]):
    """Thin internal representation of one validated LLM disposition."""

    action: RuntimeAction
    reason: str
    facts: dict[str, Any]
    target_agent: AgentType | None = None
    task_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, RuntimeAction):
            raise RuntimeDecisionContractError("runtime decision action must be RuntimeAction")
        if type(self.reason) is not str or not self.reason or self.reason != self.reason.strip():
            raise RuntimeDecisionContractError(
                "runtime decision reason must be a canonical non-empty string"
            )
        if not isinstance(self.facts, dict):
            raise RuntimeDecisionContractError("runtime decision facts must be a JSON object")
        try:
            normalized_facts = JsonObjectPayload.from_mapping(
                self.facts,
                field_path="runtime_decision.facts",
            ).to_dict()
        except AgentExecutionContractError as exc:
            raise RuntimeDecisionContractError(str(exc)) from exc
        object.__setattr__(self, "facts", normalized_facts)

        activation = self.action is RuntimeAction.ACTIVATE_FROM_STANDBY
        if activation and not isinstance(self.target_agent, AgentType):
            raise RuntimeDecisionContractError(
                "standby activation requires target_agent as AgentType"
            )
        if not activation and self.target_agent is not None:
            raise RuntimeDecisionContractError("target_agent is only valid for standby activation")
        if self.task_id is not None and (
            type(self.task_id) is not str
            or not self.task_id
            or self.task_id != self.task_id.strip()
        ):
            raise RuntimeDecisionContractError(
                "runtime decision task_id must be a canonical string when provided"
            )
        if not activation and self.task_id is not None:
            raise RuntimeDecisionContractError("task_id is only valid for standby activation")

    def _mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": self.action.value,
            "reason": self.reason,
            "facts": dict(self.facts),
        }
        if self.target_agent is not None:
            payload["target_agent"] = self.target_agent
        if self.task_id is not None:
            payload["task_id"] = self.task_id
        return payload

    def to_json_dict(self) -> dict[str, Any]:
        payload = self._mapping()
        if self.target_agent is not None:
            payload["target_agent"] = self.target_agent.value
        return payload

    def __getitem__(self, key: str) -> Any:
        return self._mapping()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping())

    def __len__(self) -> int:
        return len(self._mapping())


__all__ = [
    "RuntimeAction",
    "RuntimeDecision",
    "RuntimeDecisionContractError",
]

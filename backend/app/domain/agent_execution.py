"""Database-independent contracts for invoking and observing an Agent."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias, cast

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class AgentExecutionContractReason(str, Enum):
    INVALID_IDENTIFIER = "agent_contract_invalid_identifier"
    INVALID_EXECUTION_ORDER = "agent_contract_invalid_execution_order"
    INVALID_JSON_OBJECT = "agent_contract_invalid_json_object"
    INVALID_JSON_VALUE = "agent_contract_invalid_json_value"
    NON_FINITE_JSON_NUMBER = "agent_contract_non_finite_json_number"
    INVALID_CONTRACT_MEMBER = "agent_contract_invalid_member"
    RESERVED_OUTPUT_FIELD = "agent_contract_reserved_output_field"
    ORCHESTRATION_REPORT_MISSING = "agent_contract_orchestration_report_missing"
    EXECUTION_CONTRACT_MISSING = "agent_execution_contract_missing"
    EXECUTION_CONTRACT_INVALID = "agent_execution_contract_invalid"


class AgentExecutionContractError(ValueError):
    """Raised when a value cannot cross the Agent execution boundary."""

    def __init__(
        self,
        *,
        reason_code: AgentExecutionContractReason,
        field_path: str,
        message: str,
    ) -> None:
        self.reason_code = reason_code
        self.field_path = field_path
        super().__init__(f"{reason_code.value}: {message} (field={field_path})")


def _require_identifier(value: object, *, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentExecutionContractError(
            reason_code=AgentExecutionContractReason.INVALID_IDENTIFIER,
            field_path=field_path,
            message="expected a non-empty string",
        )
    return value.strip()


def _optional_identifier(value: object, *, field_path: str) -> str | None:
    if value is None:
        return None
    return _require_identifier(value, field_path=field_path)


def _normalize_json_value(value: object, *, field_path: str) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return cast(JsonScalar, value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.NON_FINITE_JSON_NUMBER,
                field_path=field_path,
                message="JSON numbers must be finite",
            )
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AgentExecutionContractError(
                    reason_code=AgentExecutionContractReason.INVALID_JSON_OBJECT,
                    field_path=field_path,
                    message="JSON object keys must be strings",
                )
            child_path = f"{field_path}.{key}" if field_path else key
            normalized[key] = _normalize_json_value(item, field_path=child_path)
        return normalized
    if isinstance(value, list):
        return [
            _normalize_json_value(item, field_path=f"{field_path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise AgentExecutionContractError(
        reason_code=AgentExecutionContractReason.INVALID_JSON_VALUE,
        field_path=field_path,
        message=f"unsupported runtime value {type(value).__name__}",
    )


@dataclass(frozen=True, slots=True)
class JsonObjectPayload:
    """Immutable snapshot of a strict JSON object.

    The encoded representation prevents a caller from mutating a validated payload
    after it crosses the contract boundary. ``to_dict`` always returns a fresh copy.
    """

    _encoded: str = field(repr=False)

    def __post_init__(self) -> None:
        try:
            decoded = json.loads(self._encoded)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_JSON_OBJECT,
                field_path="json_payload",
                message="encoded payload must be valid JSON",
            ) from exc
        normalized = _normalize_json_value(decoded, field_path="json_payload")
        if not isinstance(normalized, dict):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_JSON_OBJECT,
                field_path="json_payload",
                message="encoded payload must contain a JSON object",
            )
        object.__setattr__(
            self,
            "_encoded",
            json.dumps(
                normalized,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, object],
        *,
        field_path: str,
    ) -> "JsonObjectPayload":
        if not isinstance(value, Mapping):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_JSON_OBJECT,
                field_path=field_path,
                message="expected a JSON object",
            )
        normalized = _normalize_json_value(value, field_path=field_path)
        if not isinstance(normalized, dict):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_JSON_OBJECT,
                field_path=field_path,
                message="expected a JSON object",
            )
        return cls(json.dumps(normalized, allow_nan=False, ensure_ascii=False))

    @classmethod
    def empty(cls) -> "JsonObjectPayload":
        return cls("{}")

    def to_dict(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._encoded))


@dataclass(frozen=True, slots=True)
class AgentTaskReference:
    """Stable task identity and correlation values exposed to an Agent."""

    task_id: str
    task_type: str
    user_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "task_id",
            _require_identifier(self.task_id, field_path="task.task_id"),
        )
        object.__setattr__(
            self,
            "task_type",
            _require_identifier(self.task_type, field_path="task.task_type"),
        )
        object.__setattr__(
            self,
            "user_id",
            _optional_identifier(self.user_id, field_path="task.user_id"),
        )
        object.__setattr__(
            self,
            "session_id",
            _optional_identifier(self.session_id, field_path="task.session_id"),
        )

    def to_payload(self) -> dict[str, str | None]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "user_id": self.user_id,
            "session_id": self.session_id,
        }


@dataclass(frozen=True, slots=True)
class AgentExecutionRequest:
    """Immutable, persistence-free input for one Agent execution."""

    task: AgentTaskReference
    agent_type: str
    input_data: JsonObjectPayload
    workflow_state_id: str | None = None
    execution_order: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.task, AgentTaskReference):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
                field_path="task",
                message="expected AgentTaskReference",
            )
        object.__setattr__(
            self,
            "agent_type",
            _require_identifier(self.agent_type, field_path="agent_type"),
        )
        object.__setattr__(
            self,
            "workflow_state_id",
            _optional_identifier(
                self.workflow_state_id,
                field_path="workflow_state_id",
            ),
        )
        if type(self.execution_order) is not int or self.execution_order < 0:
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_EXECUTION_ORDER,
                field_path="execution_order",
                message="expected a non-negative integer",
            )
        if not isinstance(self.input_data, JsonObjectPayload):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
                field_path="input_data",
                message="expected JsonObjectPayload",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "task": self.task.to_payload(),
            "agent_type": self.agent_type,
            "workflow_state_id": self.workflow_state_id,
            "execution_order": self.execution_order,
            "input_data": self.input_data.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class AgentBoundaryEvent:
    """Agent-owned boundary fact; persistence and routing remain external."""

    event_kind: str
    reason_code: str
    payload: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "event_kind",
            _require_identifier(self.event_kind, field_path="boundary_event.event_kind"),
        )
        object.__setattr__(
            self,
            "reason_code",
            _require_identifier(self.reason_code, field_path="boundary_event.reason_code"),
        )
        if not isinstance(self.payload, JsonObjectPayload):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
                field_path="boundary_event.payload",
                message="expected JsonObjectPayload",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "event_kind": self.event_kind,
            "reason_code": self.reason_code,
            "payload": self.payload.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class AgentExecutionResult:
    """Agent output before application/control-plane persistence handlers run."""

    output_data: JsonObjectPayload
    orchestration_report: JsonObjectPayload | None = None
    boundary_events: tuple[AgentBoundaryEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.output_data, JsonObjectPayload):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
                field_path="output_data",
                message="expected JsonObjectPayload",
            )
        if "orchestration_report" in self.output_data.to_dict():
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.RESERVED_OUTPUT_FIELD,
                field_path="output_data.orchestration_report",
                message="orchestration_report must use the explicit result field",
            )
        if self.orchestration_report is not None and not isinstance(
            self.orchestration_report,
            JsonObjectPayload,
        ):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
                field_path="orchestration_report",
                message="expected JsonObjectPayload or None",
            )
        if not isinstance(self.boundary_events, tuple) or any(
            not isinstance(event, AgentBoundaryEvent) for event in self.boundary_events
        ):
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.INVALID_CONTRACT_MEMBER,
                field_path="boundary_events",
                message="expected tuple[AgentBoundaryEvent, ...]",
            )

    def require_orchestration_report(self) -> JsonObjectPayload:
        if self.orchestration_report is None:
            raise AgentExecutionContractError(
                reason_code=AgentExecutionContractReason.ORCHESTRATION_REPORT_MISSING,
                field_path="orchestration_report",
                message="Agent must explicitly report this orchestration boundary",
            )
        return self.orchestration_report

    def to_payload(self) -> dict[str, object]:
        return {
            "output_data": self.output_data.to_dict(),
            "orchestration_report": (
                self.orchestration_report.to_dict()
                if self.orchestration_report is not None
                else None
            ),
            "boundary_events": [event.to_payload() for event in self.boundary_events],
        }

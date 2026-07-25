"""Ports for preparing external references before read-only context assembly."""

from __future__ import annotations

from typing import Any, Dict, Protocol

from ..domain import AgentType


class SceneInfoReferencePreparationError(RuntimeError):
    def __init__(self, *, reason_code: str, message: str) -> None:
        self.reason_code = str(reason_code or "scene_info_reference_preparation_failed")
        super().__init__(message)


class SceneInfoReferencePreparationPort(Protocol):
    def prepare(
        self,
        *,
        workflow_state_id: str,
        agent_type: AgentType,
        runtime_input_payload: Dict[str, Any],
    ) -> str:
        ...

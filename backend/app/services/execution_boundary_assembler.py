"""
Execution-boundary assembly for leaf-agent inputs.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..agents.base import AgentError
from ..agents.utils.memory_helpers import read_shared_fact
from ..models import AgentType
from .memory_provider import MemoryServices
from .video_composer_execution_contract import (
    build_video_composer_execution_contract,
    get_video_composer_compose_mode,
)
from .video_execution_contract import build_video_generation_execution_contract


class ExecutionBoundaryAssembler:
    """Builds explicit execution boundaries outside orchestrator core."""

    def __init__(self, memory_services: MemoryServices):
        self._memory_services = memory_services

    def resolve_runtime_overrides(
        self,
        *,
        workflow_state_id: str,
        agent_type: AgentType,
    ) -> Dict[str, Any]:
        task_specs = read_shared_fact(
            workflow_state_id,
            "workflow.task_specs",
            {},
            service=self._memory_services.short_term,
        ) or {}
        if not isinstance(task_specs, dict):
            return {}
        spec = task_specs.get(agent_type.value)
        if not isinstance(spec, dict):
            return {}
        params = spec.get("runtime_hints")
        if not isinstance(params, dict):
            params = spec.get("runtime_overrides")
        return dict(params) if isinstance(params, dict) else {}

    def build_execution_contract(
        self,
        *,
        agent_type: AgentType,
        workflow_state_id: str,
        runtime_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if agent_type == AgentType.VIDEO_GENERATOR:
            generate_audio = None
            if isinstance(runtime_overrides, dict):
                candidate = runtime_overrides.get("generate_audio")
                if isinstance(candidate, bool):
                    generate_audio = bool(candidate)
            return build_video_generation_execution_contract(
                workflow_state_id=workflow_state_id,
                generate_audio=generate_audio,
            )

        if agent_type == AgentType.VIDEO_COMPOSER:
            try:
                if isinstance(runtime_overrides, dict):
                    legacy_keys = [
                        key for key in ("add_bgm", "add_voiceover", "compose_requested")
                        if runtime_overrides.get(key) is not None
                    ]
                    if legacy_keys:
                        raise AgentError(
                            "Legacy video_composer runtime overrides are no longer supported; "
                            f"use compose_mode instead (got: {', '.join(legacy_keys)})"
                        )
                compose_mode = "compose"
                if isinstance(runtime_overrides, dict) and runtime_overrides.get("compose_mode") is not None:
                    compose_mode = str(runtime_overrides.get("compose_mode"))
                return build_video_composer_execution_contract(
                    workflow_state_id=workflow_state_id,
                    compose_mode=compose_mode,
                )
            except ValueError as exc:
                raise AgentError(f"Invalid video_composer execution boundary: {exc}") from exc

        return {}

    def apply_execution_boundary(
        self,
        *,
        agent_type: AgentType,
        agent_input: Dict[str, Any],
        execution_contract: Dict[str, Any],
    ) -> Dict[str, Any]:
        if agent_type != AgentType.VIDEO_COMPOSER or not isinstance(agent_input, dict):
            return agent_input

        normalized = dict(agent_input)
        normalized.pop("add_bgm", None)
        normalized.pop("add_voiceover", None)
        normalized.pop("compose_requested", None)
        static_context = normalized.get("static_context")
        if isinstance(static_context, dict) and "requests" in static_context:
            static_context = dict(static_context)
            static_context.pop("requests", None)
            normalized["static_context"] = static_context
        return normalized

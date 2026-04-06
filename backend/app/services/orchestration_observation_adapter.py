"""
Observation/trace adapter for orchestration-related diagnostics.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..agents.utils.memory_helpers import write_shared_fact
from .memory_provider import MemoryServices


class OrchestrationObservationAdapter:
    """Owns orchestration trace payloads and gate observation persistence."""

    AUDIO_GATE_DIAGNOSTIC_KEY = "workflow.diagnostics.audio_delivery_gate"
    AUDIO_ROUTE_DIAGNOSTIC_KEY = "workflow.diagnostics.audio_route"

    def __init__(self, memory_services: Optional[MemoryServices] = None):
        if memory_services is None:
            raise ValueError("memory_services is required for OrchestrationObservationAdapter")
        self._memory_services = memory_services

    @staticmethod
    def _normalize_audio_policy(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"adaptive", "provider_only", "mas_only"}:
            return raw
        alias_map = {
            "auto": "adaptive",
            "prefer_native": "adaptive",
            "native_only": "provider_only",
            "agent_only": "mas_only",
        }
        return alias_map.get(raw, "adaptive")

    def build_audio_route_payload(
        self,
        *,
        workflow_state_id: str,
        route: Optional[Dict[str, Any]],
        contract: Optional[Dict[str, Any]],
        should_run: bool,
        decision_basis: str,
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        route_payload = dict(route or {})
        contract_obj = dict(contract or {})
        policy = self._normalize_audio_policy(contract_obj.get("policy"))
        if not str(route_payload.get("route_source") or "").strip():
            if decision_basis == "llm_task_spec":
                route_payload["route_source"] = "orchestrator.llm_task_spec"
            elif decision_basis == "boundary_trigger":
                route_payload["route_source"] = "control_plane.boundary_trigger"
            elif decision_basis == "runtime_activation":
                route_payload["route_source"] = "control_plane.runtime_activation"
            else:
                route_payload["route_source"] = "control_plane.runtime"
        if not str(route_payload.get("route_id") or "").strip():
            route_payload["route_id"] = (
                f"{workflow_state_id}:audio:{policy}:{'run' if should_run else 'skip'}"
            )
        route_payload["workflow_state_id"] = str(workflow_state_id or "")
        route_payload["policy"] = policy
        route_payload["execution_id"] = execution_id
        return route_payload

    def persist_audio_gate_observation(
        self,
        *,
        workflow_state_id: str,
        route_payload: Dict[str, Any],
        gate_result: Dict[str, Any],
    ) -> None:
        write_shared_fact(
            str(workflow_state_id),
            self.AUDIO_GATE_DIAGNOSTIC_KEY,
            gate_result,
            service=self._memory_services.short_term,
        )
        write_shared_fact(
            str(workflow_state_id),
            self.AUDIO_ROUTE_DIAGNOSTIC_KEY,
            {
                "workflow_state_id": str(workflow_state_id or ""),
                "route_payload": dict(route_payload or {}),
                "gate_result": dict(gate_result or {}),
            },
            service=self._memory_services.short_term,
        )

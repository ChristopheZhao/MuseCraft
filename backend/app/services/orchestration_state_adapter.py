"""
Control-plane state adapter for orchestration context and runtime traces.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..agents.utils.memory_helpers import read_shared_fact, write_shared_fact
from ..models import AgentType
from .memory_provider import MemoryServices


class OrchestrationStateAdapter:
    """Owns deterministic orchestration state normalization and persistence."""

    CONTINUATION_CHECKPOINT_VERSION = 2
    CONTINUATION_ANCHOR_GATE_DECISION = "gate_decision"
    CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT = "runtime_checkpoint"
    _CONTINUATION_ALLOWED_SPEC_FIELDS = (
        "agent",
        "mission",
        "deliverable",
        "constraints",
        "order",
        "runtime_hints",
        "run",
        "conditional_task_id",
        "trigger",
    )
    _FORBIDDEN_WORKFLOW_CONTROL_PREFIXES = (
        "workflow.session.",
        "workflow.node.",
        "workflow.attempt.",
        "workflow.gate_decision.",
    )

    def __init__(self, memory_services: Optional[MemoryServices] = None):
        if memory_services is None:
            raise ValueError("memory_services is required for OrchestrationStateAdapter")
        self._memory_services = memory_services

    def _write_workflow_projection(
        self,
        workflow_state_id: str,
        key: str,
        value: Any,
    ) -> None:
        normalized_key = str(key or "")
        if any(
            normalized_key.startswith(prefix)
            for prefix in self._FORBIDDEN_WORKFLOW_CONTROL_PREFIXES
        ):
            raise ValueError(f"Forbidden runtime control state projection key: {normalized_key}")
        write_shared_fact(
            str(workflow_state_id),
            normalized_key,
            value,
            service=self._memory_services.short_term,
        )

    def project_script_revision_facts(
        self,
        *,
        workflow_state_id: str,
        payload: Dict[str, Any],
        source: str,
    ) -> Dict[str, Any]:
        """Project validated script-revision facts into MAS working memory."""

        if not isinstance(payload, dict):
            raise ValueError("script_revision_context_missing: payload_not_dict")

        concept_plan = payload.get("concept_plan")
        if not isinstance(concept_plan, dict) or not concept_plan:
            raise ValueError("script_revision_concept_plan_missing")

        scene_overview = payload.get("scene_overview")
        scenes = scene_overview.get("scenes") if isinstance(scene_overview, dict) else None
        if not isinstance(scene_overview, dict) or not isinstance(scenes, list) or not scenes:
            raise ValueError("script_revision_scene_overview_missing")

        scene_scripts = payload.get("scene_scripts")
        if not isinstance(scene_scripts, dict) or not scene_scripts:
            raise ValueError("script_revision_scene_scripts_missing")

        self._write_workflow_projection(
            str(workflow_state_id),
            "project.concept_plan",
            dict(concept_plan),
        )
        self._write_workflow_projection(
            str(workflow_state_id),
            "scene_overview",
            dict(scene_overview),
        )
        self._write_workflow_projection(
            str(workflow_state_id),
            "project.scene_scripts",
            dict(scene_scripts),
        )

        receipt = {
            "status": "resolved",
            "source": str(source or "script_revision_candidate"),
            "scene_count": len(scenes),
            "scene_script_count": len(scene_scripts),
        }
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.script_revision_context",
            dict(receipt),
        )
        return receipt

    @staticmethod
    def normalize_audio_policy(value: Any) -> str:
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

    @classmethod
    def _normalize_spec_payload(
        cls,
        *,
        spec: Dict[str, Any],
        default_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            raise ValueError("Continuation spec must be a dict")

        normalized: Dict[str, Any] = {}
        agent_value = spec.get("agent")
        if agent_value is None:
            agent_value = default_agent
        if agent_value is not None:
            normalized["agent"] = str(agent_value)

        if spec.get("mission") is not None:
            normalized["mission"] = str(spec.get("mission"))
        if spec.get("deliverable") is not None:
            normalized["deliverable"] = str(spec.get("deliverable"))
        if "constraints" in spec:
            raw_constraints = spec.get("constraints")
            if raw_constraints is None:
                normalized["constraints"] = []
            elif isinstance(raw_constraints, list):
                normalized["constraints"] = [
                    str(item) for item in raw_constraints if str(item or "").strip()
                ]
            else:
                raise ValueError("Continuation spec constraints must be a list")
        if spec.get("order") is not None:
            normalized["order"] = int(spec.get("order"))
        if "runtime_hints" in spec:
            raw_runtime_hints = spec.get("runtime_hints")
            if raw_runtime_hints is None:
                normalized["runtime_hints"] = {}
            elif isinstance(raw_runtime_hints, dict):
                normalized["runtime_hints"] = dict(raw_runtime_hints)
            else:
                raise ValueError("Continuation spec runtime_hints must be a dict")
        if "run" in spec:
            normalized["run"] = bool(spec.get("run"))
        if spec.get("conditional_task_id") is not None:
            normalized["conditional_task_id"] = str(spec.get("conditional_task_id"))
        if spec.get("trigger") is not None:
            normalized["trigger"] = str(spec.get("trigger"))

        unknown_keys = set(spec.keys()) - set(cls._CONTINUATION_ALLOWED_SPEC_FIELDS)
        if unknown_keys:
            # Ignore extra keys at the checkpoint boundary to keep the stored contract minimal.
            pass
        return normalized

    @classmethod
    def build_continuation_checkpoint(
        cls,
        *,
        task_specs: Dict[AgentType, Dict[str, Any]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        candidate_agents: Optional[List[AgentType]] = None,
        anchor_type: str,
        node_key: str,
        attempt_id: int,
        decision_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized_anchor_type = str(anchor_type or "").strip().lower()
        if normalized_anchor_type not in {
            cls.CONTINUATION_ANCHOR_GATE_DECISION,
            cls.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        }:
            raise ValueError(f"Unsupported continuation anchor_type: {anchor_type!r}")
        normalized_node_key = str(node_key or "").strip().lower()
        if not normalized_node_key:
            raise ValueError("Continuation checkpoint node_key cannot be empty")
        normalized_attempt_id = int(attempt_id)
        if normalized_attempt_id <= 0:
            raise ValueError("Continuation checkpoint attempt_id must be positive")
        normalized_decision_id = int(decision_id) if decision_id is not None else None
        if (
            normalized_anchor_type == cls.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT
            and normalized_decision_id is not None
        ):
            raise ValueError("Runtime continuation checkpoints cannot bind a decision_id")

        ordered_candidates: List[AgentType] = []
        seen_agents = set()
        for raw_agent in candidate_agents or list((task_specs or {}).keys()):
            if isinstance(raw_agent, AgentType) and raw_agent not in seen_agents:
                ordered_candidates.append(raw_agent)
                seen_agents.add(raw_agent)

        serialized_task_specs: Dict[str, Dict[str, Any]] = {}
        for agent_type, spec in (task_specs or {}).items():
            if not isinstance(agent_type, AgentType):
                raise ValueError(f"Unsupported continuation agent key: {agent_type!r}")
            if not isinstance(spec, dict):
                raise ValueError(f"Continuation task spec for {agent_type.value} must be a dict")
            serialized_task_specs[agent_type.value] = cls._normalize_spec_payload(
                spec=dict(spec),
                default_agent=agent_type.value,
            )
            if agent_type not in seen_agents:
                ordered_candidates.append(agent_type)
                seen_agents.add(agent_type)

        serialized_conditional_specs: Dict[str, Dict[str, Any]] = {}
        for raw_task_id, spec in (conditional_task_specs or {}).items():
            task_id = str(raw_task_id or "").strip()
            if not task_id:
                raise ValueError("Continuation conditional task id cannot be empty")
            if not isinstance(spec, dict):
                raise ValueError(f"Continuation conditional task spec for {task_id} must be a dict")
            serialized_conditional_specs[task_id] = cls._normalize_spec_payload(spec=dict(spec))

        return {
            "version": cls.CONTINUATION_CHECKPOINT_VERSION,
            "anchor_type": normalized_anchor_type,
            "node_key": normalized_node_key,
            "attempt_id": normalized_attempt_id,
            "decision_id": normalized_decision_id,
            "candidate_agents": [agent_type.value for agent_type in ordered_candidates],
            "task_specs": serialized_task_specs,
            "conditional_task_specs": serialized_conditional_specs,
        }

    @classmethod
    def validate_continuation_checkpoint(
        cls,
        checkpoint: Any,
        *,
        require_decision_id: bool,
    ) -> Dict[str, Any]:
        if not isinstance(checkpoint, dict):
            raise ValueError("Continuation checkpoint must be a dict")

        raw_version = checkpoint.get("version")
        if raw_version != cls.CONTINUATION_CHECKPOINT_VERSION:
            raise ValueError(f"Unsupported continuation checkpoint version: {raw_version!r}")

        normalized_anchor_type = str(checkpoint.get("anchor_type") or "").strip().lower()
        if normalized_anchor_type not in {
            cls.CONTINUATION_ANCHOR_GATE_DECISION,
            cls.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        }:
            raise ValueError(
                f"Unsupported continuation checkpoint anchor_type: {checkpoint.get('anchor_type')!r}"
            )

        normalized_node_key = str(checkpoint.get("node_key") or "").strip().lower()
        if not normalized_node_key:
            raise ValueError("Continuation checkpoint node_key is required")

        raw_attempt_id = checkpoint.get("attempt_id")
        if raw_attempt_id is None:
            raise ValueError("Continuation checkpoint attempt_id is required")
        normalized_attempt_id = int(raw_attempt_id)
        if normalized_attempt_id <= 0:
            raise ValueError("Continuation checkpoint attempt_id must be positive")

        raw_decision_id = checkpoint.get("decision_id")
        if raw_decision_id is None:
            if (
                normalized_anchor_type == cls.CONTINUATION_ANCHOR_GATE_DECISION
                and require_decision_id
            ):
                raise ValueError("Continuation checkpoint decision_id is not bound")
            normalized_decision_id = None
        else:
            normalized_decision_id = int(raw_decision_id)
            if normalized_anchor_type == cls.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT:
                raise ValueError("Runtime continuation checkpoint decision_id must be null")

        raw_candidate_agents = checkpoint.get("candidate_agents")
        if not isinstance(raw_candidate_agents, list) or not raw_candidate_agents:
            raise ValueError("Continuation checkpoint candidate_agents must be a non-empty list")
        normalized_candidate_agents: List[str] = []
        for item in raw_candidate_agents:
            normalized_candidate_agents.append(AgentType(str(item)).value)

        raw_task_specs = checkpoint.get("task_specs")
        if not isinstance(raw_task_specs, dict) or not raw_task_specs:
            raise ValueError("Continuation checkpoint task_specs must be a non-empty dict")
        normalized_task_specs: Dict[str, Dict[str, Any]] = {}
        for raw_agent, spec in raw_task_specs.items():
            agent_type = AgentType(str(raw_agent))
            normalized_task_specs[agent_type.value] = cls._normalize_spec_payload(
                spec=dict(spec),
                default_agent=agent_type.value,
            )

        raw_conditional_specs = checkpoint.get("conditional_task_specs")
        if raw_conditional_specs is None:
            raw_conditional_specs = {}
        if not isinstance(raw_conditional_specs, dict):
            raise ValueError("Continuation checkpoint conditional_task_specs must be a dict")
        normalized_conditional_specs: Dict[str, Dict[str, Any]] = {}
        for raw_task_id, spec in raw_conditional_specs.items():
            task_id = str(raw_task_id or "").strip()
            if not task_id:
                raise ValueError("Continuation checkpoint conditional task id cannot be empty")
            if not isinstance(spec, dict):
                raise ValueError(f"Continuation conditional task spec for {task_id} must be a dict")
            normalized_conditional_specs[task_id] = cls._normalize_spec_payload(spec=dict(spec))

        return {
            "version": cls.CONTINUATION_CHECKPOINT_VERSION,
            "anchor_type": normalized_anchor_type,
            "node_key": normalized_node_key,
            "attempt_id": normalized_attempt_id,
            "decision_id": normalized_decision_id,
            "candidate_agents": normalized_candidate_agents,
            "task_specs": normalized_task_specs,
            "conditional_task_specs": normalized_conditional_specs,
        }

    @classmethod
    def checkpoint_to_task_specs(
        cls,
        checkpoint: Any,
        *,
        require_decision_id: bool,
    ) -> Tuple[Dict[AgentType, Dict[str, Any]], Dict[str, Dict[str, Any]], List[AgentType]]:
        normalized = cls.validate_continuation_checkpoint(
            checkpoint,
            require_decision_id=require_decision_id,
        )

        task_specs: Dict[AgentType, Dict[str, Any]] = {}
        for raw_agent, spec in normalized.get("task_specs", {}).items():
            agent_type = AgentType(str(raw_agent))
            task_specs[agent_type] = dict(spec)

        conditional_task_specs: Dict[str, Dict[str, Any]] = {
            str(task_id): dict(spec)
            for task_id, spec in (normalized.get("conditional_task_specs") or {}).items()
        }
        candidate_agents = [
            AgentType(str(raw_agent)) for raw_agent in (normalized.get("candidate_agents") or [])
        ]
        return task_specs, conditional_task_specs, candidate_agents

    def build_audio_contract(
        self,
        *,
        workflow_state_id: str,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(input_data or {})
        provided = payload.get("audio_contract")
        if isinstance(provided, dict) and provided:
            raw_policy = provided.get("policy")
            source = "input.audio_contract"
        else:
            raw_policy = payload.get("audio_policy")
            source = "input.audio_policy"

        if raw_policy is None:
            raw_policy = "adaptive"
            source = "orchestrator.default"

        contract = {
            "version": 1,
            "policy": self.normalize_audio_policy(raw_policy),
            "allow_silence": bool(payload.get("allow_silence", True)),
            "need_global_bgm": bool(payload.get("need_global_bgm", False)),
            "need_voiceover": bool(payload.get("need_voiceover", False)),
            "source": source,
            "workflow_state_id": str(workflow_state_id or ""),
        }
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.contract.audio",
            dict(contract),
        )
        return contract

    def append_replan_trace(self, *, workflow_state_id: str, record: Dict[str, Any]) -> None:
        trace = (
            read_shared_fact(
                workflow_state_id,
                "workflow.replan_trace",
                [],
                service=self._memory_services.short_term,
            )
            or []
        )
        if not isinstance(trace, list):
            trace = []
        trace.append(dict(record or {}))
        self._write_workflow_projection(
            str(workflow_state_id),
            "workflow.replan_trace",
            trace,
        )

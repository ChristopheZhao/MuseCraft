"""
Control-plane state adapter for orchestration context and runtime traces.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ..agents.utils.memory_helpers import read_shared_fact, write_shared_fact
from ..domain import AgentExecutionContractError, AgentType, JsonObjectPayload
from .memory_provider import MemoryServices


class ContinuationCheckpointContractReason(str, Enum):
    SPEC_NOT_OBJECT = "continuation_spec_not_object"
    SPEC_UNKNOWN_KEYS = "continuation_spec_unknown_keys"
    SPEC_BOOLEAN_INVALID = "continuation_spec_boolean_invalid"
    SPEC_FIELD_TYPE_INVALID = "continuation_spec_field_type_invalid"
    SPEC_AGENT_INVALID = "continuation_spec_agent_invalid"
    SPEC_AGENT_MISMATCH = "continuation_spec_agent_mismatch"
    CHECKPOINT_NOT_OBJECT = "continuation_checkpoint_not_object"
    CHECKPOINT_UNKNOWN_KEYS = "continuation_checkpoint_unknown_keys"
    CHECKPOINT_VERSION_UNSUPPORTED = "continuation_checkpoint_version_unsupported"
    CHECKPOINT_ANCHOR_INVALID = "continuation_checkpoint_anchor_invalid"
    CHECKPOINT_NODE_INVALID = "continuation_checkpoint_node_invalid"
    CHECKPOINT_ATTEMPT_INVALID = "continuation_checkpoint_attempt_invalid"
    CHECKPOINT_DECISION_INVALID = "continuation_checkpoint_decision_invalid"
    CHECKPOINT_CANDIDATES_INVALID = "continuation_checkpoint_candidates_invalid"
    CHECKPOINT_TASK_SPECS_INVALID = "continuation_checkpoint_task_specs_invalid"
    CHECKPOINT_CONDITIONAL_SPECS_INVALID = "continuation_checkpoint_conditional_specs_invalid"
    CHECKPOINT_AGENT_INVALID = "continuation_checkpoint_agent_invalid"


class ContinuationCheckpointContractError(ValueError):
    """Typed failure raised when a continuation contract is not canonical."""

    def __init__(
        self,
        *,
        reason_code: ContinuationCheckpointContractReason,
        message: str,
        field_path: str,
    ) -> None:
        self.reason_code = reason_code
        self.field_path = str(field_path or "continuation_checkpoint")
        self.message = str(message)
        super().__init__(f"{reason_code.value}: {self.message}")


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
        "scope",
        "fallback_used",
    )
    _CONTINUATION_ALLOWED_CHECKPOINT_FIELDS = (
        "version",
        "anchor_type",
        "node_key",
        "attempt_id",
        "decision_id",
        "candidate_agents",
        "task_specs",
        "conditional_task_specs",
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
    def parse_task_spec_payload(
        cls,
        *,
        spec: Dict[str, Any],
        default_agent: Optional[str] = None,
        require_explicit_agent: bool = False,
        field_path: str = "continuation_checkpoint.task_specs",
    ) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.SPEC_NOT_OBJECT,
                message="Continuation spec must be a dict",
                field_path=field_path,
            )

        unknown_keys = set(spec.keys()) - set(cls._CONTINUATION_ALLOWED_SPEC_FIELDS)
        if unknown_keys:
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.SPEC_UNKNOWN_KEYS,
                message=",".join(sorted(str(key) for key in unknown_keys)),
                field_path=field_path,
            )

        parsed: Dict[str, Any] = {}
        expected_agent: Optional[AgentType] = None
        if default_agent is not None:
            try:
                expected_agent = AgentType(default_agent)
            except (TypeError, ValueError) as exc:
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.SPEC_AGENT_INVALID,
                    message=f"Unsupported continuation spec owner agent: {default_agent!r}",
                    field_path=f"{field_path}.agent",
                ) from exc
        if "agent" not in spec:
            if require_explicit_agent:
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.SPEC_AGENT_INVALID,
                    message="Continuation spec agent is required",
                    field_path=f"{field_path}.agent",
                )
            agent_type = expected_agent
        else:
            agent_value = spec.get("agent")
            if (
                type(agent_value) is not str
                or not agent_value
                or agent_value != agent_value.strip()
            ):
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.SPEC_AGENT_INVALID,
                    message="Continuation spec agent must be a canonical AgentType value",
                    field_path=f"{field_path}.agent",
                )
            try:
                agent_type = AgentType(agent_value)
            except ValueError as exc:
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.SPEC_AGENT_INVALID,
                    message=f"Unsupported continuation spec agent: {agent_value!r}",
                    field_path=f"{field_path}.agent",
                ) from exc
        if expected_agent is not None and agent_type is not expected_agent:
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.SPEC_AGENT_MISMATCH,
                message=(
                    f"Continuation spec agent {agent_type.value if agent_type else None!r} "
                    f"does not match owner {expected_agent.value!r}"
                ),
                field_path=f"{field_path}.agent",
            )
        if agent_type is not None:
            parsed["agent"] = agent_type.value

        for field_name in (
            "mission",
            "deliverable",
            "conditional_task_id",
            "trigger",
        ):
            if field_name not in spec:
                continue
            field_value = spec.get(field_name)
            if type(field_value) is not str:
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.SPEC_FIELD_TYPE_INVALID,
                    message=f"Task spec {field_name} must be a string",
                    field_path=f"{field_path}.{field_name}",
                )
            parsed[field_name] = field_value
        if "constraints" in spec:
            raw_constraints = spec.get("constraints")
            if not isinstance(raw_constraints, list) or any(
                type(item) is not str for item in raw_constraints
            ):
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.SPEC_FIELD_TYPE_INVALID),
                    message="Task spec constraints must be list[str]",
                    field_path=f"{field_path}.constraints",
                )
            parsed["constraints"] = list(raw_constraints)
        if "order" in spec:
            raw_order = spec.get("order")
            if type(raw_order) is not int:
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.SPEC_FIELD_TYPE_INVALID),
                    message="Task spec order must be an integer",
                    field_path=f"{field_path}.order",
                )
            parsed["order"] = raw_order
        for field_name in ("runtime_hints", "scope"):
            if field_name not in spec:
                continue
            raw_object = spec.get(field_name)
            if not isinstance(raw_object, dict):
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.SPEC_FIELD_TYPE_INVALID),
                    message=f"Task spec {field_name} must be a JSON object",
                    field_path=f"{field_path}.{field_name}",
                )
            try:
                parsed[field_name] = JsonObjectPayload.from_mapping(
                    raw_object,
                    field_path=f"{field_path}.{field_name}",
                ).to_dict()
            except AgentExecutionContractError as exc:
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.SPEC_FIELD_TYPE_INVALID,
                    message=str(exc),
                    field_path=f"{field_path}.{field_name}",
                ) from exc
        if "run" in spec:
            parsed["run"] = cls._parse_spec_boolean(
                spec.get("run"),
                field_name="run",
                field_path=field_path,
            )
        if "fallback_used" in spec:
            parsed["fallback_used"] = cls._parse_spec_boolean(
                spec.get("fallback_used"),
                field_name="fallback_used",
                field_path=field_path,
            )
        return parsed

    @staticmethod
    def _parse_spec_boolean(value: Any, *, field_name: str, field_path: str) -> bool:
        if type(value) is not bool:
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.SPEC_BOOLEAN_INVALID,
                message=f"Task spec {field_name} must be a boolean",
                field_path=f"{field_path}.{field_name}",
            )
        return value

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
        if not isinstance(anchor_type, str) or anchor_type not in {
            cls.CONTINUATION_ANCHOR_GATE_DECISION,
            cls.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        }:
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_ANCHOR_INVALID,
                message=f"Unsupported continuation anchor_type: {anchor_type!r}",
                field_path="continuation_checkpoint.anchor_type",
            )
        normalized_anchor_type = anchor_type
        if (
            not isinstance(node_key, str)
            or not node_key
            or node_key != node_key.strip()
            or node_key != node_key.lower()
        ):
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_NODE_INVALID,
                message="Continuation checkpoint node_key must be a canonical string",
                field_path="continuation_checkpoint.node_key",
            )
        normalized_node_key = node_key
        if type(attempt_id) is not int:
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_ATTEMPT_INVALID,
                message="Continuation checkpoint attempt_id must be an integer",
                field_path="continuation_checkpoint.attempt_id",
            )
        normalized_attempt_id = attempt_id
        if normalized_attempt_id <= 0:
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_ATTEMPT_INVALID,
                message="Continuation checkpoint attempt_id must be positive",
                field_path="continuation_checkpoint.attempt_id",
            )
        if decision_id is None:
            normalized_decision_id = None
        else:
            if type(decision_id) is not int:
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_DECISION_INVALID),
                    message="Continuation checkpoint decision_id must be an integer",
                    field_path="continuation_checkpoint.decision_id",
                )
            normalized_decision_id = decision_id
        if (
            normalized_anchor_type == cls.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT
            and normalized_decision_id is not None
        ):
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_DECISION_INVALID,
                message="Runtime continuation checkpoints cannot bind a decision_id",
                field_path="continuation_checkpoint.decision_id",
            )

        ordered_candidates: List[AgentType] = []
        seen_agents = set()
        for index, raw_agent in enumerate(candidate_agents or list((task_specs or {}).keys())):
            if not isinstance(raw_agent, AgentType):
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_AGENT_INVALID),
                    message=f"Unsupported continuation candidate agent: {raw_agent!r}",
                    field_path=f"continuation_checkpoint.candidate_agents[{index}]",
                )
            if raw_agent not in seen_agents:
                ordered_candidates.append(raw_agent)
                seen_agents.add(raw_agent)

        serialized_task_specs: Dict[str, Dict[str, Any]] = {}
        for agent_type, spec in (task_specs or {}).items():
            if not isinstance(agent_type, AgentType):
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_AGENT_INVALID),
                    message=f"Unsupported continuation agent key: {agent_type!r}",
                    field_path="continuation_checkpoint.task_specs",
                )
            if not isinstance(spec, dict):
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.SPEC_NOT_OBJECT,
                    message=f"Continuation task spec for {agent_type.value} must be a dict",
                    field_path=(f"continuation_checkpoint.task_specs.{agent_type.value}"),
                )
            serialized_task_specs[agent_type.value] = cls.parse_task_spec_payload(
                spec=dict(spec),
                default_agent=agent_type.value,
                field_path=f"continuation_checkpoint.task_specs.{agent_type.value}",
            )
            if agent_type not in seen_agents:
                ordered_candidates.append(agent_type)
                seen_agents.add(agent_type)

        serialized_conditional_specs: Dict[str, Dict[str, Any]] = {}
        for raw_task_id, spec in (conditional_task_specs or {}).items():
            if (
                not isinstance(raw_task_id, str)
                or not raw_task_id
                or raw_task_id != raw_task_id.strip()
            ):
                raise ContinuationCheckpointContractError(
                    reason_code=(
                        ContinuationCheckpointContractReason.CHECKPOINT_CONDITIONAL_SPECS_INVALID
                    ),
                    message="Continuation conditional task id cannot be empty",
                    field_path="continuation_checkpoint.conditional_task_specs",
                )
            task_id = raw_task_id
            if not isinstance(spec, dict):
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.SPEC_NOT_OBJECT,
                    message=(f"Continuation conditional task spec for {task_id} must be a dict"),
                    field_path=(f"continuation_checkpoint.conditional_task_specs.{task_id}"),
                )
            serialized_conditional_specs[task_id] = cls.parse_task_spec_payload(
                spec=dict(spec),
                require_explicit_agent=True,
                field_path=f"continuation_checkpoint.conditional_task_specs.{task_id}",
            )

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
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_NOT_OBJECT,
                message="Continuation checkpoint must be a dict",
                field_path="continuation_checkpoint",
            )

        unknown_checkpoint_keys = set(checkpoint.keys()) - set(
            cls._CONTINUATION_ALLOWED_CHECKPOINT_FIELDS
        )
        if unknown_checkpoint_keys:
            raise ContinuationCheckpointContractError(
                reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_UNKNOWN_KEYS),
                message=",".join(sorted(str(key) for key in unknown_checkpoint_keys)),
                field_path="continuation_checkpoint",
            )

        raw_version = checkpoint.get("version")
        if raw_version != cls.CONTINUATION_CHECKPOINT_VERSION:
            raise ContinuationCheckpointContractError(
                reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_VERSION_UNSUPPORTED),
                message=f"Unsupported continuation checkpoint version: {raw_version!r}",
                field_path="continuation_checkpoint.version",
            )

        raw_anchor_type = checkpoint.get("anchor_type")
        if not isinstance(raw_anchor_type, str) or raw_anchor_type not in {
            cls.CONTINUATION_ANCHOR_GATE_DECISION,
            cls.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        }:
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_ANCHOR_INVALID,
                message=(
                    "Unsupported continuation checkpoint anchor_type: "
                    f"{checkpoint.get('anchor_type')!r}"
                ),
                field_path="continuation_checkpoint.anchor_type",
            )
        normalized_anchor_type = raw_anchor_type

        raw_node_key = checkpoint.get("node_key")
        if (
            not isinstance(raw_node_key, str)
            or not raw_node_key
            or raw_node_key != raw_node_key.strip()
            or raw_node_key != raw_node_key.lower()
        ):
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_NODE_INVALID,
                message="Continuation checkpoint node_key must be a canonical string",
                field_path="continuation_checkpoint.node_key",
            )
        normalized_node_key = raw_node_key

        raw_attempt_id = checkpoint.get("attempt_id")
        if type(raw_attempt_id) is not int:
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_ATTEMPT_INVALID,
                message="Continuation checkpoint attempt_id must be an integer",
                field_path="continuation_checkpoint.attempt_id",
            )
        normalized_attempt_id = raw_attempt_id
        if normalized_attempt_id <= 0:
            raise ContinuationCheckpointContractError(
                reason_code=ContinuationCheckpointContractReason.CHECKPOINT_ATTEMPT_INVALID,
                message="Continuation checkpoint attempt_id must be positive",
                field_path="continuation_checkpoint.attempt_id",
            )

        raw_decision_id = checkpoint.get("decision_id")
        if raw_decision_id is None:
            if (
                normalized_anchor_type == cls.CONTINUATION_ANCHOR_GATE_DECISION
                and require_decision_id
            ):
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_DECISION_INVALID),
                    message="Continuation checkpoint decision_id is not bound",
                    field_path="continuation_checkpoint.decision_id",
                )
            normalized_decision_id = None
        else:
            if type(raw_decision_id) is not int:
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_DECISION_INVALID),
                    message="Continuation checkpoint decision_id must be an integer",
                    field_path="continuation_checkpoint.decision_id",
                )
            normalized_decision_id = raw_decision_id
            if normalized_anchor_type == cls.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT:
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_DECISION_INVALID),
                    message="Runtime continuation checkpoint decision_id must be null",
                    field_path="continuation_checkpoint.decision_id",
                )

        raw_candidate_agents = checkpoint.get("candidate_agents")
        if not isinstance(raw_candidate_agents, list) or not raw_candidate_agents:
            raise ContinuationCheckpointContractError(
                reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_CANDIDATES_INVALID),
                message="Continuation checkpoint candidate_agents must be a non-empty list",
                field_path="continuation_checkpoint.candidate_agents",
            )
        normalized_candidate_agents: List[str] = []
        for index, item in enumerate(raw_candidate_agents):
            if type(item) is not str:
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.CHECKPOINT_AGENT_INVALID,
                    message=f"Unsupported continuation candidate agent: {item!r}",
                    field_path=f"continuation_checkpoint.candidate_agents[{index}]",
                )
            try:
                normalized_candidate_agents.append(AgentType(item).value)
            except ValueError as exc:
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_AGENT_INVALID),
                    message=f"Unsupported continuation candidate agent: {item!r}",
                    field_path=f"continuation_checkpoint.candidate_agents[{index}]",
                ) from exc

        raw_task_specs = checkpoint.get("task_specs")
        if not isinstance(raw_task_specs, dict) or not raw_task_specs:
            raise ContinuationCheckpointContractError(
                reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_TASK_SPECS_INVALID),
                message="Continuation checkpoint task_specs must be a non-empty dict",
                field_path="continuation_checkpoint.task_specs",
            )
        normalized_task_specs: Dict[str, Dict[str, Any]] = {}
        for raw_agent, spec in raw_task_specs.items():
            if type(raw_agent) is not str:
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.CHECKPOINT_AGENT_INVALID,
                    message=f"Unsupported continuation task-spec agent: {raw_agent!r}",
                    field_path="continuation_checkpoint.task_specs",
                )
            try:
                agent_type = AgentType(raw_agent)
            except ValueError as exc:
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.CHECKPOINT_AGENT_INVALID),
                    message=f"Unsupported continuation task-spec agent: {raw_agent!r}",
                    field_path="continuation_checkpoint.task_specs",
                ) from exc
            if not isinstance(spec, dict):
                raise ContinuationCheckpointContractError(
                    reason_code=(ContinuationCheckpointContractReason.SPEC_NOT_OBJECT),
                    message=(f"Continuation task spec for {agent_type.value} must be a dict"),
                    field_path=(f"continuation_checkpoint.task_specs.{agent_type.value}"),
                )
            normalized_task_specs[agent_type.value] = cls.parse_task_spec_payload(
                spec=dict(spec),
                default_agent=agent_type.value,
                require_explicit_agent=True,
                field_path=f"continuation_checkpoint.task_specs.{agent_type.value}",
            )

        raw_conditional_specs = checkpoint.get("conditional_task_specs")
        if raw_conditional_specs is None:
            raw_conditional_specs = {}
        if not isinstance(raw_conditional_specs, dict):
            raise ContinuationCheckpointContractError(
                reason_code=(
                    ContinuationCheckpointContractReason.CHECKPOINT_CONDITIONAL_SPECS_INVALID
                ),
                message="Continuation checkpoint conditional_task_specs must be a dict",
                field_path="continuation_checkpoint.conditional_task_specs",
            )
        normalized_conditional_specs: Dict[str, Dict[str, Any]] = {}
        for raw_task_id, spec in raw_conditional_specs.items():
            if (
                not isinstance(raw_task_id, str)
                or not raw_task_id
                or raw_task_id != raw_task_id.strip()
            ):
                raise ContinuationCheckpointContractError(
                    reason_code=(
                        ContinuationCheckpointContractReason.CHECKPOINT_CONDITIONAL_SPECS_INVALID
                    ),
                    message="Continuation checkpoint conditional task id cannot be empty",
                    field_path="continuation_checkpoint.conditional_task_specs",
                )
            task_id = raw_task_id
            if not isinstance(spec, dict):
                raise ContinuationCheckpointContractError(
                    reason_code=ContinuationCheckpointContractReason.SPEC_NOT_OBJECT,
                    message=(f"Continuation conditional task spec for {task_id} must be a dict"),
                    field_path=(f"continuation_checkpoint.conditional_task_specs.{task_id}"),
                )
            normalized_conditional_specs[task_id] = cls.parse_task_spec_payload(
                spec=dict(spec),
                require_explicit_agent=True,
                field_path=f"continuation_checkpoint.conditional_task_specs.{task_id}",
            )

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

        candidate_agents = [
            AgentType(str(raw_agent)) for raw_agent in (normalized.get("candidate_agents") or [])
        ]
        candidate_order = {agent_type: index for index, agent_type in enumerate(candidate_agents)}
        normalized_task_specs = normalized.get("task_specs", {})
        ordered_task_specs = sorted(
            normalized_task_specs.items(),
            key=lambda item: (
                int(item[1]["order"])
                if item[1].get("order") is not None
                else candidate_order.get(AgentType(str(item[0])), len(candidate_order)),
                candidate_order.get(AgentType(str(item[0])), len(candidate_order)),
                str(item[0]),
            ),
        )
        task_specs: Dict[AgentType, Dict[str, Any]] = {}
        for raw_agent, spec in ordered_task_specs:
            agent_type = AgentType(str(raw_agent))
            task_specs[agent_type] = dict(spec)

        conditional_task_specs: Dict[str, Dict[str, Any]] = {
            str(task_id): dict(spec)
            for task_id, spec in (normalized.get("conditional_task_specs") or {}).items()
        }
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

"""Database-independent runtime ports consumed by the MAS control plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from ..domain import AgentTaskReference, AgentType


class OrchestrationRuntimeResumeBootstrapError(RuntimeError):
    """A required runtime resume/bootstrap contract could not be satisfied."""


class OrchestrationRuntimeTransitionError(RuntimeError):
    """A requested MAS control-plane transition could not be persisted."""


@dataclass(frozen=True, slots=True)
class RuntimeResumeContext:
    runtime_session_id: int
    runtime_session_status: str
    runtime_input_payload: Dict[str, Any]
    script_gate_id: Optional[int]
    latest_script_decision_exists: bool
    latest_script_decision_actor_type: str
    script_resume_action: str
    runtime_resume_checkpoint: Optional[Dict[str, Any]]
    resume_anchor_agent: Optional[AgentType]


@dataclass(frozen=True, slots=True)
class RuntimeResumeTaskSpecBundle:
    task_specs: Dict[AgentType, Dict[str, Any]]
    conditional_task_specs: Dict[str, Dict[str, Any]]
    candidate_agents: List[AgentType]


@dataclass(frozen=True, slots=True)
class RuntimeAttemptBootstrapResult:
    node_key: str
    attempt_id: int
    trigger_reason: str
    lease_token: str


class OrchestrationRuntimeResumePort(Protocol):
    def resolve_runtime_resume_context(self, *, task: AgentTaskReference) -> RuntimeResumeContext:
        ...

    def load_authoritative_resume_task_specs(
        self, *, runtime_session_id: int, resume_action: str
    ) -> RuntimeResumeTaskSpecBundle:
        ...

    def consume_script_approval_continuation(
        self, *, runtime_session_id: int, task: AgentTaskReference
    ) -> None:
        ...

    def project_script_revision_context(
        self,
        *,
        runtime_session_id: int,
        workflow_state_id: str,
        resume_action: str,
    ) -> Dict[str, Any]:
        ...

    def start_runtime_attempt(
        self,
        *,
        runtime_session_id: int,
        task: AgentTaskReference,
        current_agent_type: AgentType,
        workflow_state_id: str,
        task_specs: Dict[AgentType, Dict[str, Any]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        candidate_agents: List[AgentType],
        script_trigger_reason: str,
        script_requested_by: str,
        resume_anchor_agent: Optional[AgentType],
        trigger_reason_override: Optional[str] = None,
    ) -> RuntimeAttemptBootstrapResult:
        ...


class OrchestrationRuntimeTransitionPort(Protocol):
    def complete_runtime_attempt(
        self,
        *,
        runtime_session_id: int,
        node_key: str,
        attempt_id: int,
        lease_token: Optional[str],
        node_status: str,
    ) -> None:
        ...

    def fail_runtime_attempt(
        self,
        *,
        runtime_session_id: int,
        node_key: str,
        attempt_id: int,
        error_message: str,
        lease_token: Optional[str],
        diagnostics: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        ...

    def upsert_runtime_attempt_diagnostic(
        self,
        *,
        runtime_session_id: int,
        attempt_id: int,
        diagnostic: Dict[str, Any],
    ) -> None:
        ...

    def open_script_review_gate(
        self,
        *,
        runtime_session_id: int,
        task_id: str,
        workflow_id: str,
        script_attempt_id: int,
        lease_token: Optional[str],
        trigger_reason: str,
        script_output: Dict[str, Any],
        task_specs: Dict[AgentType, Dict[str, Any]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        candidate_agents: List[AgentType],
    ) -> Dict[str, Any]:
        ...

    def mark_runtime_session_completed(
        self,
        *,
        runtime_session_id: int,
        task_id: str,
        summary_output: Optional[Dict[str, Any]] = None,
    ) -> None:
        ...

    def mark_runtime_session_failed(
        self,
        *,
        runtime_session_id: int,
        task_id: str,
        error_message: str,
    ) -> None:
        ...

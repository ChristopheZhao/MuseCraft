"""
Workflow runtime models for single-episode control-plane state
"""
import enum

from sqlalchemy import Column, String, Text, JSON, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from .base import BaseModel


class WorkflowSessionStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_GATE = "waiting_gate"
    RESUMING = "resuming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowNodeStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PENDING_GATE = "pending_gate"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STALE = "stale"


class WorkflowAttemptStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


class WorkflowGateStatus(str, enum.Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    AWAITING_HUMAN = "awaiting_human"
    DECIDED = "decided"


class WorkflowSession(BaseModel):
    __tablename__ = "workflow_sessions"

    task_db_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    mode = Column(String(50), nullable=False, default="quick")
    project_id = Column(String(100), nullable=True, index=True)
    episode_id = Column(String(100), nullable=True, index=True)
    shared_memory_id = Column(String(100), nullable=True, index=True)
    status = Column(String(30), nullable=False, default=WorkflowSessionStatus.QUEUED.value)
    current_node_key = Column(String(100), nullable=True)
    current_attempt_id = Column(Integer, nullable=True)
    input_payload = Column(JSON, default=dict)
    gate_policy = Column(JSON, default=dict)
    summary_output = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)

    task = relationship("Task", back_populates="runtime_sessions")
    nodes = relationship("WorkflowNodeState", back_populates="session", cascade="all, delete-orphan")
    attempts = relationship("WorkflowNodeAttempt", back_populates="session", cascade="all, delete-orphan")
    gates = relationship("WorkflowGate", back_populates="session", cascade="all, delete-orphan")
    decisions = relationship("WorkflowGateDecision", back_populates="session", cascade="all, delete-orphan")
    published_deliverables = relationship(
        "WorkflowPublishedDeliverable",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class WorkflowNodeState(BaseModel):
    __tablename__ = "workflow_node_states"

    session_id = Column(Integer, ForeignKey("workflow_sessions.id"), nullable=False, index=True)
    node_key = Column(String(100), nullable=False, index=True)
    node_type = Column(String(50), nullable=False)
    order_index = Column(Integer, nullable=False, default=0)
    scope_type = Column(String(30), nullable=False, default="episode")
    scope_ref = Column(String(100), nullable=True)
    status = Column(String(30), nullable=False, default=WorkflowNodeStatus.QUEUED.value)
    revision_index = Column(Integer, nullable=False, default=0)
    gate_required = Column(Boolean, nullable=False, default=False)
    last_gate_id = Column(Integer, nullable=True)
    artifact_refs = Column(JSON, default=list)
    diagnostics = Column(JSON, default=list)

    session = relationship("WorkflowSession", back_populates="nodes")
    attempts = relationship("WorkflowNodeAttempt", back_populates="node", cascade="all, delete-orphan")
    gates = relationship("WorkflowGate", back_populates="node", cascade="all, delete-orphan")
    decisions = relationship("WorkflowGateDecision", back_populates="node", cascade="all, delete-orphan")
    published_deliverables = relationship(
        "WorkflowPublishedDeliverable",
        back_populates="node",
        cascade="all, delete-orphan",
    )


class WorkflowNodeAttempt(BaseModel):
    __tablename__ = "workflow_node_attempts"

    session_id = Column(Integer, ForeignKey("workflow_sessions.id"), nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("workflow_node_states.id"), nullable=False, index=True)
    attempt_no = Column(Integer, nullable=False, default=1)
    trigger_reason = Column(String(30), nullable=False, default="initial")
    requested_by = Column(String(30), nullable=False, default="system")
    input_contract = Column(JSON, default=dict)
    output_artifacts = Column(JSON, default=list)
    metrics = Column(JSON, default=dict)
    status = Column(String(20), nullable=False, default=WorkflowAttemptStatus.RUNNING.value)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)

    session = relationship("WorkflowSession", back_populates="attempts")
    node = relationship("WorkflowNodeState", back_populates="attempts")
    gates = relationship("WorkflowGate", back_populates="attempt", cascade="all, delete-orphan")
    published_deliverables = relationship(
        "WorkflowPublishedDeliverable",
        back_populates="attempt",
        cascade="all, delete-orphan",
    )


class WorkflowGate(BaseModel):
    __tablename__ = "workflow_gates"

    session_id = Column(Integer, ForeignKey("workflow_sessions.id"), nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("workflow_node_states.id"), nullable=False, index=True)
    attempt_id = Column(Integer, ForeignKey("workflow_node_attempts.id"), nullable=True, index=True)
    gate_name = Column(String(50), nullable=False)
    gate_type = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False, default=WorkflowGateStatus.PENDING.value)
    contract_version = Column(String(20), nullable=False, default="v1")
    artifact_refs = Column(JSON, default=list)
    facts = Column(JSON, default=dict)
    result_code = Column(String(30), nullable=True)
    reason_code = Column(String(100), nullable=True)
    allowed_actions = Column(JSON, default=list)
    recommended_action = Column(String(30), nullable=True)

    session = relationship("WorkflowSession", back_populates="gates")
    node = relationship("WorkflowNodeState", back_populates="gates")
    attempt = relationship("WorkflowNodeAttempt", back_populates="gates")
    decisions = relationship("WorkflowGateDecision", back_populates="gate", cascade="all, delete-orphan")


class WorkflowGateDecision(BaseModel):
    __tablename__ = "workflow_gate_decisions"

    gate_id = Column(Integer, ForeignKey("workflow_gates.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("workflow_sessions.id"), nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("workflow_node_states.id"), nullable=False, index=True)
    action = Column(String(30), nullable=False)
    actor_type = Column(String(30), nullable=False, default="human")
    actor_id = Column(String(100), nullable=True)
    feedback_text = Column(Text, nullable=True)
    structured_constraints = Column(JSON, default=dict)
    invalidation_scope = Column(String(30), nullable=False, default="node")

    gate = relationship("WorkflowGate", back_populates="decisions")
    session = relationship("WorkflowSession", back_populates="decisions")
    node = relationship("WorkflowNodeState", back_populates="decisions")


class WorkflowPublishedDeliverable(BaseModel):
    __tablename__ = "workflow_published_deliverables"

    session_id = Column(Integer, ForeignKey("workflow_sessions.id"), nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("workflow_node_states.id"), nullable=False, index=True)
    attempt_id = Column(Integer, ForeignKey("workflow_node_attempts.id"), nullable=False, index=True)
    deliverable_type = Column(String(50), nullable=False, index=True)
    scope_type = Column(String(30), nullable=False, default="episode")
    scope_id = Column(String(100), nullable=True)
    revision_no = Column(Integer, nullable=False, default=0)
    payload_ref = Column(String(500), nullable=False)
    summary = Column(JSON, default=dict)
    is_candidate = Column(Boolean, nullable=False, default=True)
    is_approved = Column(Boolean, nullable=False, default=False)

    session = relationship("WorkflowSession", back_populates="published_deliverables")
    node = relationship("WorkflowNodeState", back_populates="published_deliverables")
    attempt = relationship("WorkflowNodeAttempt", back_populates="published_deliverables")

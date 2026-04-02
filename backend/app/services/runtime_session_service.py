"""
DB-backed runtime session service for the single-episode kernel
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..models import (
    Task,
    TaskStatus,
    WorkflowSession,
    WorkflowSessionStatus,
    WorkflowNodeState,
    WorkflowNodeStatus,
    WorkflowNodeAttempt,
    WorkflowAttemptStatus,
    WorkflowGate,
    WorkflowGateStatus,
    WorkflowGateDecision,
)
from ..core.constants import GenerationMode
from ..core.config import settings
from ..core.generation_mode import resolve_generation_mode
from .published_deliverable_service import (
    PublishedDeliverableService,
    build_deliverable_ref,
    clear_published_deliverable_ref,
    set_published_deliverable_ref,
)
from .script_review_contract import (
    build_script_review_contract,
    get_script_review_contract,
    set_script_review_contract,
)
from .orchestration_state_adapter import OrchestrationStateAdapter


DEFAULT_NODE_BLUEPRINT = [
    {
        "node_key": "concept",
        "node_type": "concept",
        "order_index": 10,
        "scope_type": "episode",
        "scope_ref": "episode",
        "gate_required": False,
    },
    {
        "node_key": "script",
        "node_type": "script",
        "order_index": 20,
        "scope_type": "episode",
        "scope_ref": "episode",
        "gate_required": True,
    },
    {
        "node_key": "image",
        "node_type": "image",
        "order_index": 30,
        "scope_type": "episode",
        "scope_ref": "episode",
        "gate_required": False,
    },
    {
        "node_key": "video",
        "node_type": "video",
        "order_index": 40,
        "scope_type": "episode",
        "scope_ref": "episode",
        "gate_required": False,
    },
    {
        "node_key": "voice",
        "node_type": "voice",
        "order_index": 50,
        "scope_type": "episode",
        "scope_ref": "episode",
        "gate_required": False,
    },
    {
        "node_key": "compose",
        "node_type": "compose",
        "order_index": 60,
        "scope_type": "episode",
        "scope_ref": "episode",
        "gate_required": False,
    },
    {
        "node_key": "audio",
        "node_type": "audio",
        "order_index": 70,
        "scope_type": "episode",
        "scope_ref": "episode",
        "gate_required": False,
    },
    {
        "node_key": "quality",
        "node_type": "quality",
        "order_index": 80,
        "scope_type": "episode",
        "scope_ref": "episode",
        "gate_required": False,
    },
]


def _serialize_node(node: WorkflowNodeState) -> Dict[str, Any]:
    return {
        "id": node.id,
        "node_key": node.node_key,
        "node_type": node.node_type,
        "order_index": node.order_index,
        "scope_type": node.scope_type,
        "scope_ref": node.scope_ref,
        "status": node.status,
        "revision_index": node.revision_index,
        "gate_required": bool(node.gate_required),
        "last_gate_id": node.last_gate_id,
        "artifact_refs": node.artifact_refs or [],
        "diagnostics": node.diagnostics or [],
    }


def _serialize_decision(decision: Optional[WorkflowGateDecision]) -> Optional[Dict[str, Any]]:
    if decision is None:
        return None
    return {
        "id": decision.id,
        "gate_id": decision.gate_id,
        "action": decision.action,
        "actor_type": decision.actor_type,
        "actor_id": decision.actor_id,
        "feedback_text": decision.feedback_text,
        "structured_constraints": decision.structured_constraints or {},
        "invalidation_scope": decision.invalidation_scope,
        "created_at": decision.created_at.isoformat() if decision.created_at else None,
        "updated_at": decision.updated_at.isoformat() if decision.updated_at else None,
    }


def _serialize_gate(
    gate: Optional[WorkflowGate],
    *,
    latest_decision: Optional[WorkflowGateDecision] = None,
) -> Optional[Dict[str, Any]]:
    if gate is None:
        return None
    return {
        "id": gate.id,
        "node_id": gate.node_id,
        "attempt_id": gate.attempt_id,
        "gate_name": gate.gate_name,
        "gate_type": gate.gate_type,
        "status": gate.status,
        "contract_version": gate.contract_version,
        "scope": gate.scope or {},
        "artifact_refs": gate.artifact_refs or [],
        "facts": gate.facts or {},
        "result": gate.result_code or gate.status,
        "result_code": gate.result_code,
        "reason_code": gate.reason_code,
        "diagnostics": gate.diagnostics or [],
        "allowed_actions": gate.allowed_actions or [],
        "recommended_action": gate.recommended_action,
        "latest_decision": _serialize_decision(latest_decision),
        "created_at": gate.created_at.isoformat() if gate.created_at else None,
        "updated_at": gate.updated_at.isoformat() if gate.updated_at else None,
    }


def _serialize_session(
    session: WorkflowSession,
    nodes: List[WorkflowNodeState],
    *,
    active_gate: Optional[WorkflowGate] = None,
    latest_decision: Optional[WorkflowGateDecision] = None,
    resume_control: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "session_id": session.id,
        "task_db_id": session.task_db_id,
        "mode": session.mode,
        "project_id": session.project_id,
        "episode_id": session.episode_id,
        "shared_memory_id": session.shared_memory_id,
        "status": session.status,
        "current_node_key": session.current_node_key,
        "current_attempt_id": session.current_attempt_id,
        "active_gate": _serialize_gate(active_gate, latest_decision=latest_decision),
        "error_message": session.error_message,
        "summary_output": session.summary_output or {},
        "resume_control": resume_control,
        "nodes": [_serialize_node(node) for node in nodes],
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_attempt_lease_seconds(lease_timeout_seconds: Optional[int] = None) -> int:
    if lease_timeout_seconds is not None:
        return max(1, int(lease_timeout_seconds))
    return max(1, int(getattr(settings, "RUNTIME_ATTEMPT_LEASE_SECONDS", 300)))


def _clear_attempt_lease_fields(attempt: WorkflowNodeAttempt) -> None:
    attempt.lease_token = None
    attempt.lease_owner = None
    attempt.last_heartbeat_at = None
    attempt.lease_expires_at = None


def _normalize_attempt_lease_fields(
    attempt: Optional[WorkflowNodeAttempt],
) -> Optional[WorkflowNodeAttempt]:
    if attempt is None:
        return None
    attempt.last_heartbeat_at = _normalize_datetime(getattr(attempt, "last_heartbeat_at", None))
    attempt.lease_expires_at = _normalize_datetime(getattr(attempt, "lease_expires_at", None))
    return attempt


def _fresh_session_node_attempt_sync(
    db: Session,
    session: WorkflowSession,
    *,
    node_key: str,
    attempt_id: int,
) -> tuple[WorkflowSession, WorkflowNodeState, WorkflowNodeAttempt]:
    try:
        db.expire_all()
    except Exception:
        pass

    fresh_session = (
        db.query(WorkflowSession)
        .filter(WorkflowSession.id == session.id)
        .first()
    )
    if fresh_session is None:
        raise ValueError(f"Workflow session {session.id} not found")

    node = (
        db.query(WorkflowNodeState)
        .filter(
            WorkflowNodeState.session_id == fresh_session.id,
            WorkflowNodeState.node_key == node_key,
        )
        .first()
    )
    if node is None:
        raise ValueError(f"Workflow node {node_key} not found for session {fresh_session.id}")

    attempt = (
        db.query(WorkflowNodeAttempt)
        .filter(
            WorkflowNodeAttempt.id == attempt_id,
            WorkflowNodeAttempt.session_id == fresh_session.id,
        )
        .first()
    )
    if attempt is None:
        raise ValueError(f"Workflow attempt {attempt_id} not found for session {fresh_session.id}")
    return fresh_session, node, _normalize_attempt_lease_fields(attempt)


def _merge_failure_diagnostics(
    node: WorkflowNodeState,
    diagnostics: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    existing = getattr(node, "diagnostics", None)
    if isinstance(existing, list):
        merged.extend(item for item in existing if isinstance(item, dict))
    if isinstance(diagnostics, list):
        merged.extend(item for item in diagnostics if isinstance(item, dict))
    return merged


def _upsert_node_diagnostic(
    node: WorkflowNodeState,
    diagnostic: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged = _merge_failure_diagnostics(node, None)
    if not isinstance(diagnostic, dict):
        return merged

    code = str(diagnostic.get("code") or "").strip()
    attempt_id = diagnostic.get("attempt_id")
    if not code:
        merged.append(diagnostic)
        return merged

    updated: List[Dict[str, Any]] = []
    replaced = False
    for item in merged:
        item_code = str(item.get("code") or "").strip()
        same_code = item_code == code
        same_attempt = attempt_id is None or item.get("attempt_id") == attempt_id
        if same_code and same_attempt:
            if not replaced:
                updated.append(diagnostic)
                replaced = True
            continue
        updated.append(item)

    if not replaced:
        updated.append(diagnostic)
    return updated


def _build_attempt_lease_diagnostic(
    *,
    attempt: WorkflowNodeAttempt,
    node_key: str,
    reason_code: str,
    validation_error: Optional[str] = None,
) -> Dict[str, Any]:
    captured_at = _now_utc()
    last_heartbeat_at = _normalize_datetime(getattr(attempt, "last_heartbeat_at", None))
    lease_expires_at = _normalize_datetime(getattr(attempt, "lease_expires_at", None))
    lease_owner = str(getattr(attempt, "lease_owner", "") or "").strip() or None
    lease_token_present = bool(str(getattr(attempt, "lease_token", "") or "").strip())
    lease_live = bool(
        lease_token_present
        and lease_owner
        and lease_expires_at is not None
        and lease_expires_at > captured_at
    )
    return {
        "code": "execution_lease_snapshot",
        "node_key": node_key,
        "attempt_id": attempt.id,
        "reason_code": reason_code,
        "lease_owner": lease_owner,
        "lease_token_present": lease_token_present,
        "lease_live": lease_live,
        "last_heartbeat_at": last_heartbeat_at.isoformat() if last_heartbeat_at else None,
        "lease_expires_at": lease_expires_at.isoformat() if lease_expires_at else None,
        "captured_at": captured_at.isoformat(),
        "validation_error": validation_error,
    }


def _build_resume_control_projection(
    db: Session,
    task: Task,
    session: WorkflowSession,
    *,
    active_gate: Optional[WorkflowGate] = None,
) -> Optional[Dict[str, Any]]:
    session_status = str(session.status or "").strip().lower()
    if session_status in {
        WorkflowSessionStatus.COMPLETED.value,
        WorkflowSessionStatus.FAILED.value,
        WorkflowSessionStatus.CANCELLED.value,
    }:
        return None

    if active_gate is not None and str(active_gate.status or "").strip().lower() == WorkflowGateStatus.AWAITING_HUMAN.value:
        return {
            "state": "waiting_gate",
            "can_resume": False,
            "reason_code": "awaiting_gate_decision",
        }

    attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, session.current_attempt_id)
    if attempt is None:
        return {
            "state": "resume_blocked",
            "can_resume": False,
            "reason_code": "missing_current_attempt",
        }

    if RuntimeSessionService.is_attempt_lease_live(attempt):
        return {
            "state": "view_only_running",
            "can_resume": False,
            "reason_code": "active_execution_lease",
        }

    if session_status == WorkflowSessionStatus.RESUMING.value:
        try:
            checkpoint = OrchestrationStateAdapter.validate_continuation_checkpoint(
                attempt.continuation_checkpoint,
                require_decision_id=False,
            )
        except ValueError:
            return {
                "state": "resume_blocked",
                "can_resume": False,
                "reason_code": "missing_continuation_checkpoint",
            }
        anchor_type = str(checkpoint.get("anchor_type") or "").strip().lower()
        if anchor_type == OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION:
            try:
                RuntimeSessionService.load_active_script_continuation_sync(
                    db,
                    session,
                    node_key=str(session.current_node_key or "script"),
                )
            except ValueError:
                return {
                    "state": "resume_blocked",
                    "can_resume": False,
                    "reason_code": "missing_continuation_checkpoint",
                }
        else:
            try:
                RuntimeSessionService.load_active_continuation_sync(
                    db,
                    session,
                    expected_anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
                    require_decision_id=False,
                    require_resuming=True,
                )
            except ValueError:
                return {
                    "state": "resume_blocked",
                    "can_resume": False,
                    "reason_code": "missing_continuation_checkpoint",
                }
        return {
            "state": "view_only_running",
            "can_resume": False,
            "reason_code": "resume_scheduled",
        }

    try:
        RuntimeSessionService.load_active_continuation_sync(
            db,
            session,
            expected_anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            require_decision_id=False,
            require_resuming=False,
        )
    except ValueError:
        return {
            "state": "resume_blocked",
            "can_resume": False,
            "reason_code": "missing_continuation_checkpoint",
        }

    return {
        "state": "resume_available",
        "can_resume": True,
        "reason_code": "checkpoint_available",
    }


class RuntimeSessionService:
    """Creates and manages workflow runtime sessions."""

    @staticmethod
    async def _load_runtime_nodes_async(
        db: AsyncSession,
        session_id: int,
    ) -> List[WorkflowNodeState]:
        result = await db.execute(
            select(WorkflowNodeState)
            .where(WorkflowNodeState.session_id == session_id)
            .order_by(WorkflowNodeState.order_index.asc(), WorkflowNodeState.id.asc())
        )
        nodes = list(result.scalars().all())
        if nodes:
            return nodes
        raise ValueError(
            f"Runtime session {session_id} missing workflow nodes; read path cannot repair runtime invariants"
        )

    @staticmethod
    def _load_runtime_nodes_sync(
        db: Session,
        session_id: int,
    ) -> List[WorkflowNodeState]:
        nodes = (
            db.query(WorkflowNodeState)
            .filter(WorkflowNodeState.session_id == session_id)
            .order_by(WorkflowNodeState.order_index.asc(), WorkflowNodeState.id.asc())
            .all()
        )
        if nodes:
            return list(nodes)
        raise ValueError(
            f"Runtime session {session_id} missing workflow nodes; read path cannot repair runtime invariants"
        )

    @staticmethod
    def mark_node_running_sync(
        db: Session,
        session: WorkflowSession,
        *,
        node_key: str,
        task: Optional[Task] = None,
        progress_step: Optional[str] = None,
        progress_percentage: Optional[int] = None,
    ) -> WorkflowNodeState:
        node = RuntimeSessionService.get_node_by_key_sync(db, session.id, node_key)
        if node is None:
            raise ValueError(f"Workflow node {node_key} not found for session {session.id}")

        session.status = WorkflowSessionStatus.RUNNING.value
        session.current_node_key = node.node_key
        session.current_attempt_id = None
        session.error_message = None
        node.status = WorkflowNodeStatus.RUNNING.value
        if task is not None:
            task.status = TaskStatus.IN_PROGRESS.value
            if progress_step is not None and progress_percentage is not None:
                task.update_progress(progress_step, progress_percentage)

        db.commit()
        db.refresh(node)
        db.refresh(session)
        return node

    @staticmethod
    def mark_node_completed_sync(
        db: Session,
        session: WorkflowSession,
        *,
        node_key: str,
        artifact_refs: Optional[List[Dict[str, Any]]] = None,
        diagnostics: Optional[List[Dict[str, Any]]] = None,
    ) -> WorkflowNodeState:
        node = RuntimeSessionService.get_node_by_key_sync(db, session.id, node_key)
        if node is None:
            raise ValueError(f"Workflow node {node_key} not found for session {session.id}")

        node.status = WorkflowNodeStatus.COMPLETED.value
        if artifact_refs is not None:
            node.artifact_refs = artifact_refs
        if diagnostics is not None:
            node.diagnostics = diagnostics

        db.commit()
        db.refresh(node)
        db.refresh(session)
        return node

    @staticmethod
    def clear_node_diagnostic_codes_sync(
        db: Session,
        session: WorkflowSession,
        *,
        node_key: str,
        codes: List[str],
    ) -> WorkflowNodeState:
        node = RuntimeSessionService.get_node_by_key_sync(db, session.id, node_key)
        if node is None:
            raise ValueError(f"Workflow node {node_key} not found for session {session.id}")

        normalized_codes = {
            str(code or "").strip()
            for code in (codes or [])
            if str(code or "").strip()
        }
        if normalized_codes:
            existing = getattr(node, "diagnostics", None)
            filtered: List[Dict[str, Any]] = []
            if isinstance(existing, list):
                filtered = [
                    item
                    for item in existing
                    if not (
                        isinstance(item, dict)
                        and str(item.get("code") or "").strip() in normalized_codes
                    )
                ]
            node.diagnostics = filtered
            db.commit()
        db.refresh(node)
        db.refresh(session)
        return node

    @staticmethod
    def upsert_attempt_node_diagnostic_sync(
        db: Session,
        session: WorkflowSession,
        *,
        attempt_id: int,
        diagnostic: Dict[str, Any],
    ) -> WorkflowNodeState:
        if not isinstance(diagnostic, dict):
            raise ValueError("diagnostic must be a dict")

        attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, attempt_id)
        if attempt is None:
            raise ValueError(f"Workflow attempt {attempt_id} not found for session {session.id}")

        node = (
            db.query(WorkflowNodeState)
            .filter(
                WorkflowNodeState.id == attempt.node_id,
                WorkflowNodeState.session_id == session.id,
            )
            .first()
        )
        if node is None:
            raise ValueError(
                f"Workflow node for attempt {attempt_id} not found in session {session.id}"
            )

        node.diagnostics = _upsert_node_diagnostic(node, diagnostic)
        db.commit()
        db.refresh(node)
        db.refresh(session)
        return node

    @staticmethod
    def consume_script_approval_continuation_sync(
        db: Session,
        session: WorkflowSession,
        *,
        task: Optional[Task] = None,
    ) -> WorkflowNodeState:
        node = RuntimeSessionService.get_node_by_key_sync(db, session.id, "script")
        if node is None:
            raise ValueError(f"Workflow node script not found for session {session.id}")
        gate = RuntimeSessionService.get_latest_gate_for_node_sync(db, session.id, "script")
        if gate is None:
            raise ValueError(f"No gate found for node script in session {session.id}")
        latest_decision = RuntimeSessionService.get_latest_decision_for_gate_sync(db, gate.id)
        if latest_decision is None or str(latest_decision.action or "").strip().lower() != "approve":
            raise ValueError(
                f"Workflow node script for session {session.id} has no approved continuation decision"
            )
        if session.status != WorkflowSessionStatus.RESUMING.value:
            raise ValueError(
                f"Workflow session {session.id} is not awaiting continuation consumption"
            )
        if node.status != WorkflowNodeStatus.APPROVED.value:
            raise ValueError(
                f"Workflow node script for session {session.id} is not in approved state"
            )

        node.status = WorkflowNodeStatus.COMPLETED.value
        session.status = WorkflowSessionStatus.RUNNING.value
        session.current_node_key = None
        session.current_attempt_id = None
        session.error_message = None
        if task is not None:
            task.status = TaskStatus.IN_PROGRESS.value
            task.requires_human_review = False

        db.commit()
        db.refresh(node)
        db.refresh(session)
        return node

    @staticmethod
    async def _get_latest_gate_for_session_async(
        db: AsyncSession,
        session_id: int,
    ) -> Optional[WorkflowGate]:
        result = await db.execute(
            select(WorkflowGate)
            .where(WorkflowGate.session_id == session_id)
            .order_by(WorkflowGate.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _get_latest_decision_for_gate_async(
        db: AsyncSession,
        gate_id: int,
    ) -> Optional[WorkflowGateDecision]:
        result = await db.execute(
            select(WorkflowGateDecision)
            .where(WorkflowGateDecision.gate_id == gate_id)
            .order_by(WorkflowGateDecision.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_session_for_task(
        db: AsyncSession,
        task: Task,
        *,
        mode: str = "quick",
        project_id: Optional[str] = None,
        episode_id: Optional[str] = None,
    ) -> WorkflowSession:
        session = WorkflowSession(
            task_db_id=task.id,
            mode=mode,
            project_id=project_id,
            episode_id=episode_id,
            shared_memory_id=str(task.task_id),
            status=WorkflowSessionStatus.QUEUED.value,
            input_payload=task.input_parameters or {},
            gate_policy={},
        )
        db.add(session)
        await db.flush()
        await RuntimeSessionService._ensure_default_nodes_async(db, session)
        task.output_metadata = dict(task.output_metadata or {}, workflow_session_id=session.id)
        await db.commit()
        await db.refresh(session)
        await db.refresh(task)
        return session

    @staticmethod
    async def get_latest_session_for_task(db: AsyncSession, task_db_id: int) -> Optional[WorkflowSession]:
        result = await db.execute(
            select(WorkflowSession)
            .where(WorkflowSession.task_db_id == task_db_id)
            .order_by(desc(WorkflowSession.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def get_latest_session_for_task_sync(db: Session, task_db_id: int) -> Optional[WorkflowSession]:
        return (
            db.query(WorkflowSession)
            .filter(WorkflowSession.task_db_id == task_db_id)
            .order_by(WorkflowSession.id.desc())
            .first()
        )

    @staticmethod
    async def build_runtime_view_for_task(db: AsyncSession, task: Task) -> Optional[Dict[str, Any]]:
        # Projection only: explicit stale-runtime reconciliation must stay out of read paths.
        session = await RuntimeSessionService.get_latest_session_for_task(db, task.id)
        if session is None:
            return None
        nodes = await RuntimeSessionService._load_runtime_nodes_async(db, session.id)
        active_gate = await RuntimeSessionService._get_latest_gate_for_session_async(db, session.id)
        latest_decision = None
        if active_gate is not None:
            latest_decision = await RuntimeSessionService._get_latest_decision_for_gate_async(db, active_gate.id)
        resume_control = await db.run_sync(
            lambda sync_db: _build_resume_control_projection(
                sync_db,
                sync_db.query(Task).filter(Task.id == task.id).first(),
                RuntimeSessionService.get_session_by_id_sync(sync_db, session.id),
                active_gate=(
                    RuntimeSessionService.get_latest_gate_for_session_sync(sync_db, session.id)
                    if active_gate is not None
                    else None
                ),
            )
        )
        return _serialize_session(
            session,
            nodes,
            active_gate=active_gate,
            latest_decision=latest_decision,
            resume_control=resume_control,
        )

    @staticmethod
    async def mark_session_cancelled_for_task(db: AsyncSession, task: Task) -> Optional[WorkflowSession]:
        session = await RuntimeSessionService.get_latest_session_for_task(db, task.id)
        if session is None:
            task.status = TaskStatus.CANCELLED.value
            await db.commit()
            return None
        session.status = WorkflowSessionStatus.CANCELLED.value
        task.status = TaskStatus.CANCELLED.value
        await db.commit()
        return session

    @staticmethod
    async def _ensure_default_nodes_async(db: AsyncSession, session: WorkflowSession) -> None:
        result = await db.execute(
            select(WorkflowNodeState.id).where(WorkflowNodeState.session_id == session.id).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return
        for blueprint in DEFAULT_NODE_BLUEPRINT:
            db.add(WorkflowNodeState(session_id=session.id, **blueprint))
        await db.flush()

    @staticmethod
    def get_or_create_session_for_task_sync(
        db: Session,
        task: Task,
        *,
        mode: str = "quick",
        project_id: Optional[str] = None,
        episode_id: Optional[str] = None,
    ) -> WorkflowSession:
        session = (
            db.query(WorkflowSession)
            .filter(WorkflowSession.task_db_id == task.id)
            .order_by(WorkflowSession.id.desc())
            .first()
        )
        if session is not None:
            RuntimeSessionService._ensure_default_nodes_sync(db, session)
            return session

        session = WorkflowSession(
            task_db_id=task.id,
            mode=mode,
            project_id=project_id,
            episode_id=episode_id,
            shared_memory_id=str(task.task_id),
            status=WorkflowSessionStatus.QUEUED.value,
            input_payload=task.input_parameters or {},
            gate_policy={},
        )
        db.add(session)
        db.flush()
        RuntimeSessionService._ensure_default_nodes_sync(db, session)
        task.output_metadata = dict(task.output_metadata or {}, workflow_session_id=session.id)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def prepare_dispatch_payload_for_task_sync(
        db: Session,
        task: Task,
        *,
        mode: str | GenerationMode = "quick",
        project_id: Optional[str] = None,
        episode_id: Optional[str] = None,
    ) -> tuple[Optional[WorkflowSession], Dict[str, Any]]:
        mode_value = getattr(mode, "value", mode)
        dispatch_payload = dict(task.input_parameters or {})
        if str(mode_value or "").strip().lower() != GenerationMode.QUICK.value:
            return None, dispatch_payload

        runtime_session = RuntimeSessionService.get_or_create_session_for_task_sync(
            db,
            task,
            mode=GenerationMode.QUICK.value,
            project_id=project_id,
            episode_id=episode_id,
        )
        if isinstance(runtime_session.input_payload, dict) and runtime_session.input_payload:
            dispatch_payload = dict(runtime_session.input_payload)
        return runtime_session, dispatch_payload

    @staticmethod
    def mark_task_execution_failed_sync(
        db: Session,
        task: Task,
        *,
        error_message: str,
    ) -> Optional[WorkflowSession]:
        mode = resolve_generation_mode((task.input_parameters or {}).get("mode"))
        if mode == GenerationMode.QUICK:
            runtime_session = RuntimeSessionService.get_or_create_session_for_task_sync(
                db,
                task,
                mode=GenerationMode.QUICK.value,
            )
            RuntimeSessionService.mark_session_failed_sync(
                db,
                runtime_session,
                error_message=error_message,
                task=task,
            )
            return runtime_session

        task.status = TaskStatus.FAILED.value
        task.error_message = error_message
        db.commit()
        return None

    @staticmethod
    def get_session_by_id_sync(db: Session, session_id: int) -> Optional[WorkflowSession]:
        return db.query(WorkflowSession).filter(WorkflowSession.id == session_id).first()

    @staticmethod
    def build_runtime_view_for_task_sync(db: Session, task: Task) -> Optional[Dict[str, Any]]:
        # Projection only: explicit stale-runtime reconciliation must stay out of read paths.
        session = RuntimeSessionService.get_latest_session_for_task_sync(db, task.id)
        if session is None:
            return None
        nodes = RuntimeSessionService._load_runtime_nodes_sync(db, session.id)
        active_gate = RuntimeSessionService.get_latest_gate_for_session_sync(db, session.id)
        latest_decision = None
        if active_gate is not None:
            latest_decision = RuntimeSessionService.get_latest_decision_for_gate_sync(db, active_gate.id)
        resume_control = _build_resume_control_projection(db, task, session, active_gate=active_gate)
        return _serialize_session(
            session,
            list(nodes),
            active_gate=active_gate,
            latest_decision=latest_decision,
            resume_control=resume_control,
        )

    @staticmethod
    def get_resume_control_sync(
        db: Session,
        task: Task,
        session: WorkflowSession,
    ) -> Optional[Dict[str, Any]]:
        active_gate = RuntimeSessionService.get_latest_gate_for_session_sync(db, session.id)
        return _build_resume_control_projection(db, task, session, active_gate=active_gate)

    @staticmethod
    def reconcile_irrecoverable_quick_runtime_sync(
        db: Session,
        task: Optional[Task],
        session: Optional[WorkflowSession],
    ) -> Optional[WorkflowSession]:
        if task is None or session is None:
            return session
        if str(session.mode or "").strip().lower() != GenerationMode.QUICK.value:
            return session
        if str(session.status or "").strip().lower() in {
            WorkflowSessionStatus.COMPLETED.value,
            WorkflowSessionStatus.FAILED.value,
            WorkflowSessionStatus.CANCELLED.value,
        }:
            return session

        resume_control = RuntimeSessionService.get_resume_control_sync(db, task, session)
        if not resume_control:
            return session
        if (
            str(resume_control.get("state") or "").strip().lower() != "resume_blocked"
            or str(resume_control.get("reason_code") or "").strip().lower()
            != "missing_continuation_checkpoint"
        ):
            return session

        error_message = (
            "Stale quick runtime detected: execution lease is no longer active and continuation checkpoint is missing"
        )
        logging.getLogger("runtime_session_service").warning(
            "Marking irrecoverable stale quick runtime failed: task_id=%s session_id=%s node=%s",
            getattr(task, "task_id", None),
            session.id,
            getattr(session, "current_node_key", None),
        )
        RuntimeSessionService.mark_session_failed_sync(
            db,
            session,
            error_message=error_message,
            task=task,
        )
        return session

    @staticmethod
    def reconcile_irrecoverable_quick_runtimes_sync(
        db: Session,
        *,
        limit: int = 100,
    ) -> Dict[str, int]:
        non_terminal_statuses = [
            WorkflowSessionStatus.RUNNING.value,
            WorkflowSessionStatus.RESUMING.value,
        ]
        sessions = (
            db.query(WorkflowSession)
            .filter(
                WorkflowSession.mode == GenerationMode.QUICK.value,
                WorkflowSession.status.in_(non_terminal_statuses),
            )
            .order_by(WorkflowSession.updated_at.asc(), WorkflowSession.id.asc())
            .limit(max(1, int(limit)))
            .all()
        )

        inspected = 0
        failed = 0
        skipped = 0
        for session in sessions:
            inspected += 1
            task = session.task
            if task is None:
                skipped += 1
                continue
            before_status = str(session.status or "").strip().lower()
            RuntimeSessionService.reconcile_irrecoverable_quick_runtime_sync(
                db,
                task,
                session,
            )
            db.refresh(session)
            after_status = str(session.status or "").strip().lower()
            if before_status != WorkflowSessionStatus.FAILED.value and after_status == WorkflowSessionStatus.FAILED.value:
                failed += 1
            else:
                skipped += 1

        return {
            "inspected": inspected,
            "failed": failed,
            "skipped": skipped,
        }

    @staticmethod
    def get_node_by_key_sync(
        db: Session,
        session_id: int,
        node_key: str,
    ) -> Optional[WorkflowNodeState]:
        return (
            db.query(WorkflowNodeState)
            .filter(
                WorkflowNodeState.session_id == session_id,
                WorkflowNodeState.node_key == node_key,
            )
            .first()
        )

    @staticmethod
    def get_latest_gate_for_session_sync(
        db: Session,
        session_id: int,
    ) -> Optional[WorkflowGate]:
        return (
            db.query(WorkflowGate)
            .filter(WorkflowGate.session_id == session_id)
            .order_by(WorkflowGate.id.desc())
            .first()
        )

    @staticmethod
    def get_latest_gate_for_node_sync(
        db: Session,
        session_id: int,
        node_key: str,
    ) -> Optional[WorkflowGate]:
        node = RuntimeSessionService.get_node_by_key_sync(db, session_id, node_key)
        if node is None:
            return None
        return (
            db.query(WorkflowGate)
            .filter(
                WorkflowGate.session_id == session_id,
                WorkflowGate.node_id == node.id,
            )
            .order_by(WorkflowGate.id.desc())
            .first()
        )

    @staticmethod
    def get_latest_decision_for_gate_sync(
        db: Session,
        gate_id: int,
    ) -> Optional[WorkflowGateDecision]:
        return (
            db.query(WorkflowGateDecision)
            .filter(WorkflowGateDecision.gate_id == gate_id)
            .order_by(WorkflowGateDecision.id.desc())
            .first()
        )

    @staticmethod
    def get_attempt_by_id_sync(
        db: Session,
        session_id: int,
        attempt_id: Optional[int],
    ) -> Optional[WorkflowNodeAttempt]:
        if attempt_id is None:
            return None
        attempt = (
            db.query(WorkflowNodeAttempt)
            .filter(
                WorkflowNodeAttempt.id == attempt_id,
                WorkflowNodeAttempt.session_id == session_id,
            )
            .first()
        )
        return _normalize_attempt_lease_fields(attempt)

    @staticmethod
    def is_attempt_lease_live(
        attempt: Optional[WorkflowNodeAttempt],
        *,
        as_of: Optional[datetime] = None,
    ) -> bool:
        if attempt is None:
            return False
        lease_token = str(getattr(attempt, "lease_token", "") or "").strip()
        lease_owner = str(getattr(attempt, "lease_owner", "") or "").strip()
        lease_expires_at = _normalize_datetime(getattr(attempt, "lease_expires_at", None))
        if not lease_token or not lease_owner or lease_expires_at is None:
            return False
        effective_as_of = _normalize_datetime(as_of) or _now_utc()
        return lease_expires_at > effective_as_of

    @staticmethod
    def grant_attempt_lease_sync(
        db: Session,
        session: WorkflowSession,
        *,
        attempt_id: int,
        lease_owner: str,
        lease_timeout_seconds: Optional[int] = None,
        lease_token: Optional[str] = None,
    ) -> WorkflowNodeAttempt:
        # lease_owner identifies the control-plane issuer of the live execution lease.
        # Execution hosts renew that lease later via lease_token only.
        attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, attempt_id)
        if attempt is None:
            raise ValueError(f"Workflow attempt {attempt_id} not found for session {session.id}")

        owner_value = str(lease_owner or "").strip()
        if not owner_value:
            raise ValueError("lease_owner is required when granting an execution lease")

        token_value = str(lease_token or uuid4().hex).strip()
        if not token_value:
            raise ValueError("A non-empty lease token is required when granting an execution lease")

        lease_started_at = _now_utc()
        attempt.lease_token = token_value
        attempt.lease_owner = owner_value
        attempt.last_heartbeat_at = lease_started_at
        attempt.lease_expires_at = lease_started_at + timedelta(
            seconds=_resolve_attempt_lease_seconds(lease_timeout_seconds)
        )

        db.commit()
        db.refresh(attempt)
        db.refresh(session)
        return _normalize_attempt_lease_fields(attempt)

    @staticmethod
    def assert_attempt_lease_sync(
        db: Session,
        session: WorkflowSession,
        *,
        attempt_id: int,
        lease_token: str,
        allow_expired: bool = False,
    ) -> WorkflowNodeAttempt:
        attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, attempt_id)
        if attempt is None:
            raise ValueError(f"Workflow attempt {attempt_id} not found for session {session.id}")

        expected_token = str(lease_token or "").strip()
        if not expected_token:
            raise ValueError("lease_token is required for execution lease validation")

        actual_token = str(getattr(attempt, "lease_token", "") or "").strip()
        if not actual_token:
            raise ValueError(
                f"Workflow attempt {attempt_id} does not have an active execution lease"
            )
        if actual_token != expected_token:
            raise ValueError(
                f"Workflow attempt {attempt_id} execution lease token mismatch"
            )
        if not allow_expired and not RuntimeSessionService.is_attempt_lease_live(attempt):
            raise ValueError(
                f"Workflow attempt {attempt_id} execution lease expired"
            )
        return attempt

    @staticmethod
    def heartbeat_attempt_lease_sync(
        db: Session,
        session: WorkflowSession,
        *,
        attempt_id: int,
        lease_token: str,
        lease_timeout_seconds: Optional[int] = None,
    ) -> WorkflowNodeAttempt:
        # Heartbeat is host-side liveness reporting for an already-issued lease.
        attempt = RuntimeSessionService.assert_attempt_lease_sync(
            db,
            session,
            attempt_id=attempt_id,
            lease_token=lease_token,
            allow_expired=False,
        )
        heartbeat_at = _now_utc()
        attempt.last_heartbeat_at = heartbeat_at
        attempt.lease_expires_at = heartbeat_at + timedelta(
            seconds=_resolve_attempt_lease_seconds(lease_timeout_seconds)
        )

        db.commit()
        db.refresh(attempt)
        db.refresh(session)
        return _normalize_attempt_lease_fields(attempt)

    @staticmethod
    def release_attempt_lease_sync(
        db: Session,
        session: WorkflowSession,
        *,
        attempt_id: int,
        lease_token: Optional[str] = None,
    ) -> WorkflowNodeAttempt:
        attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, attempt_id)
        if attempt is None:
            raise ValueError(f"Workflow attempt {attempt_id} not found for session {session.id}")
        if lease_token is not None:
            RuntimeSessionService.assert_attempt_lease_sync(
                db,
                session,
                attempt_id=attempt_id,
                lease_token=lease_token,
                allow_expired=True,
            )

        attempt.lease_token = None
        attempt.lease_owner = None
        attempt.last_heartbeat_at = None
        attempt.lease_expires_at = None

        db.commit()
        db.refresh(attempt)
        db.refresh(session)
        return _normalize_attempt_lease_fields(attempt)

    @staticmethod
    def load_active_script_continuation_sync(
        db: Session,
        session: WorkflowSession,
        *,
        node_key: str = "script",
    ) -> Dict[str, Any]:
        checkpoint = RuntimeSessionService.load_active_continuation_sync(
            db,
            session,
            expected_anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
            require_decision_id=True,
            require_resuming=True,
        )
        if str(checkpoint.get("node_key") or "") != str(node_key or "").strip().lower():
            raise ValueError(
                f"Workflow session {session.id} continuation is not anchored to node {node_key}"
            )
        return checkpoint

    @staticmethod
    def load_active_continuation_sync(
        db: Session,
        session: WorkflowSession,
        *,
        expected_anchor_type: Optional[str] = None,
        require_decision_id: bool,
        require_resuming: bool,
    ) -> Dict[str, Any]:
        if session is None:
            raise ValueError("Workflow session is required for continuation loading")
        if require_resuming and session.status != WorkflowSessionStatus.RESUMING.value:
            raise ValueError(f"Workflow session {session.id} is not in resuming state")

        node_key = str(session.current_node_key or "").strip().lower()
        if not node_key:
            raise ValueError(f"Workflow session {session.id} missing current node anchor")

        attempt_id = session.current_attempt_id
        if attempt_id is None:
            raise ValueError(
                f"Workflow session {session.id} missing current attempt anchor for continuation"
            )

        attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, attempt_id)
        if attempt is None:
            raise ValueError(f"Workflow attempt {attempt_id} not found for session {session.id}")

        checkpoint = OrchestrationStateAdapter.validate_continuation_checkpoint(
            attempt.continuation_checkpoint,
            require_decision_id=require_decision_id,
        )
        checkpoint_anchor_type = str(checkpoint.get("anchor_type") or "").strip().lower()
        if expected_anchor_type is not None and checkpoint_anchor_type != str(expected_anchor_type).strip().lower():
            raise ValueError(
                f"Workflow session {session.id} continuation anchor_type mismatch: "
                f"expected={expected_anchor_type} actual={checkpoint_anchor_type or '<empty>'}"
            )
        if str(checkpoint.get("node_key") or "").strip().lower() != node_key:
            raise ValueError(
                f"Workflow session {session.id} continuation node anchor mismatch: "
                f"checkpoint={checkpoint.get('node_key')} session={node_key}"
            )
        if int(checkpoint.get("attempt_id")) != int(attempt_id):
            raise ValueError(
                f"Workflow session {session.id} continuation attempt anchor mismatch: "
                f"checkpoint={checkpoint.get('attempt_id')} session={attempt_id}"
            )

        if checkpoint_anchor_type == OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION:
            gate = RuntimeSessionService.get_latest_gate_for_node_sync(db, session.id, node_key)
            if gate is None:
                raise ValueError(f"No gate found for node {node_key} in session {session.id}")
            latest_decision = RuntimeSessionService.get_latest_decision_for_gate_sync(db, gate.id)
            if latest_decision is None:
                raise ValueError(
                    f"No continuation decision found for gate {gate.id} in session {session.id}"
                )
            if gate.attempt_id != attempt_id:
                raise ValueError(
                    f"Workflow session {session.id} attempt anchor {attempt_id} does not match gate attempt {gate.attempt_id}"
                )
            if require_decision_id and int(checkpoint.get("decision_id")) != int(latest_decision.id):
                raise ValueError(
                    f"Continuation checkpoint decision binding is stale for session {session.id}: "
                    f"checkpoint={checkpoint.get('decision_id')} latest={latest_decision.id}"
                )

        return checkpoint

    @staticmethod
    def bind_attempt_continuation_checkpoint_sync(
        db: Session,
        session: WorkflowSession,
        *,
        attempt_id: int,
        continuation_checkpoint: Dict[str, Any],
    ) -> WorkflowNodeAttempt:
        attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, attempt_id)
        if attempt is None:
            raise ValueError(f"Workflow attempt {attempt_id} not found for session {session.id}")
        attempt.continuation_checkpoint = OrchestrationStateAdapter.validate_continuation_checkpoint(
            continuation_checkpoint,
            require_decision_id=False,
        )
        db.commit()
        db.refresh(attempt)
        db.refresh(session)
        return attempt

    @staticmethod
    def start_node_attempt_sync(
        db: Session,
        session: WorkflowSession,
        *,
        node_key: str,
        trigger_reason: str = "initial",
        requested_by: str = "system",
        input_contract: Optional[Dict[str, Any]] = None,
        task: Optional[Task] = None,
        progress_step: Optional[str] = None,
        progress_percentage: Optional[int] = None,
    ) -> WorkflowNodeAttempt:
        node = RuntimeSessionService.get_node_by_key_sync(db, session.id, node_key)
        if node is None:
            raise ValueError(f"Workflow node {node_key} not found for session {session.id}")
        latest_attempt = (
            db.query(WorkflowNodeAttempt)
            .filter(WorkflowNodeAttempt.node_id == node.id)
            .order_by(WorkflowNodeAttempt.attempt_no.desc())
            .first()
        )
        attempt = WorkflowNodeAttempt(
            session_id=session.id,
            node_id=node.id,
            attempt_no=(latest_attempt.attempt_no + 1) if latest_attempt is not None else 1,
            trigger_reason=str(trigger_reason or "initial"),
            requested_by=str(requested_by or "system"),
            input_contract=input_contract or {},
            status=WorkflowAttemptStatus.RUNNING.value,
        )
        db.add(attempt)
        db.flush()

        session.status = WorkflowSessionStatus.RUNNING.value
        session.current_node_key = node.node_key
        session.current_attempt_id = attempt.id
        session.error_message = None
        node.status = WorkflowNodeStatus.RUNNING.value
        if task is not None:
            task.status = TaskStatus.IN_PROGRESS.value
            if progress_step is not None and progress_percentage is not None:
                task.update_progress(progress_step, progress_percentage)
            task.requires_human_review = False

        db.commit()
        db.refresh(session)
        db.refresh(node)
        db.refresh(attempt)
        return attempt

    @staticmethod
    def complete_node_attempt_sync(
        db: Session,
        session: WorkflowSession,
        *,
        node_key: str,
        attempt_id: int,
        lease_token: Optional[str] = None,
        output_artifacts: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        artifact_refs: Optional[List[Dict[str, Any]]] = None,
        diagnostics: Optional[List[Dict[str, Any]]] = None,
        node_status: Optional[str] = None,
    ) -> WorkflowNodeAttempt:
        fresh_session, node, attempt = _fresh_session_node_attempt_sync(
            db,
            session,
            node_key=node_key,
            attempt_id=attempt_id,
        )
        if lease_token is not None:
            RuntimeSessionService.assert_attempt_lease_sync(
                db,
                fresh_session,
                attempt_id=attempt_id,
                lease_token=lease_token,
                allow_expired=False,
            )

        attempt.status = WorkflowAttemptStatus.SUCCEEDED.value
        _clear_attempt_lease_fields(attempt)
        attempt.output_artifacts = output_artifacts or []
        attempt.metrics = metrics or {}
        if artifact_refs is not None:
            node.artifact_refs = artifact_refs
        if diagnostics is not None:
            node.diagnostics = diagnostics
        if node_status is not None:
            node.status = node_status

        fresh_session.current_attempt_id = attempt.id
        db.commit()
        db.refresh(attempt)
        db.refresh(node)
        db.refresh(fresh_session)
        return attempt

    @staticmethod
    def fail_node_attempt_sync(
        db: Session,
        session: WorkflowSession,
        *,
        node_key: str,
        attempt_id: int,
        error_message: str,
        lease_token: Optional[str] = None,
        output_artifacts: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        artifact_refs: Optional[List[Dict[str, Any]]] = None,
        diagnostics: Optional[List[Dict[str, Any]]] = None,
        node_status: Optional[str] = None,
    ) -> WorkflowNodeAttempt:
        fresh_session, node, attempt = _fresh_session_node_attempt_sync(
            db,
            session,
            node_key=node_key,
            attempt_id=attempt_id,
        )
        failure_diagnostics = _merge_failure_diagnostics(node, diagnostics)
        if lease_token is not None:
            try:
                RuntimeSessionService.assert_attempt_lease_sync(
                    db,
                    fresh_session,
                    attempt_id=attempt_id,
                    lease_token=lease_token,
                    allow_expired=False,
                )
            except ValueError as exc:
                failure_diagnostics.append(
                    _build_attempt_lease_diagnostic(
                        attempt=attempt,
                        node_key=node_key,
                        reason_code="lease_validation_failed",
                        validation_error=str(exc),
                    )
                )
                node.diagnostics = failure_diagnostics
                db.commit()
                db.refresh(attempt)
                db.refresh(node)
                db.refresh(fresh_session)
                raise

        failure_diagnostics.append(
            _build_attempt_lease_diagnostic(
                attempt=attempt,
                node_key=node_key,
                reason_code="node_attempt_failed",
            )
        )
        attempt.status = WorkflowAttemptStatus.FAILED.value
        _clear_attempt_lease_fields(attempt)
        attempt.output_artifacts = output_artifacts or []
        attempt.metrics = metrics or {}
        if artifact_refs is not None:
            node.artifact_refs = artifact_refs
        node.diagnostics = failure_diagnostics
        node.status = node_status or WorkflowNodeStatus.FAILED.value
        fresh_session.current_node_key = node.node_key
        fresh_session.current_attempt_id = attempt.id
        fresh_session.error_message = str(error_message or "")

        db.commit()
        db.refresh(attempt)
        db.refresh(node)
        db.refresh(fresh_session)
        return attempt

    @staticmethod
    def open_human_gate_sync(
        db: Session,
        session: WorkflowSession,
        *,
        node_key: str,
        gate_name: str,
        gate_type: str,
        attempt_id: Optional[int] = None,
        lease_token: Optional[str] = None,
        scope: Optional[Dict[str, Any]] = None,
        artifact_refs: Optional[List[Dict[str, Any]]] = None,
        facts: Optional[Dict[str, Any]] = None,
        result_code: Optional[str] = None,
        reason_code: Optional[str] = None,
        diagnostics: Optional[List[Dict[str, Any]]] = None,
        allowed_actions: Optional[List[str]] = None,
        recommended_action: Optional[str] = None,
        task: Optional[Task] = None,
        progress_step: Optional[str] = None,
        progress_percentage: Optional[int] = None,
    ) -> WorkflowGate:
        node = RuntimeSessionService.get_node_by_key_sync(db, session.id, node_key)
        if node is None:
            raise ValueError(f"Workflow node {node_key} not found for session {session.id}")
        attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, attempt_id)
        if attempt_id is not None and attempt is None:
            raise ValueError(f"Workflow attempt {attempt_id} not found for session {session.id}")
        if lease_token is not None:
            if attempt_id is None:
                raise ValueError("attempt_id is required when validating a gate-opening execution lease")
            RuntimeSessionService.assert_attempt_lease_sync(
                db,
                session,
                attempt_id=attempt_id,
                lease_token=lease_token,
                allow_expired=False,
            )

        gate = WorkflowGate(
            session_id=session.id,
            node_id=node.id,
            attempt_id=attempt_id,
            gate_name=gate_name,
            gate_type=gate_type,
            status=WorkflowGateStatus.AWAITING_HUMAN.value,
            scope=scope or {},
            artifact_refs=artifact_refs or [],
            facts=facts or {},
            result_code=result_code or WorkflowGateStatus.AWAITING_HUMAN.value,
            reason_code=reason_code,
            diagnostics=diagnostics or [],
            allowed_actions=allowed_actions or [],
            recommended_action=recommended_action,
        )
        db.add(gate)
        db.flush()

        if attempt is not None:
            _clear_attempt_lease_fields(attempt)
        node.last_gate_id = gate.id
        node.status = WorkflowNodeStatus.PENDING_GATE.value
        session.status = WorkflowSessionStatus.WAITING_GATE.value
        session.current_node_key = node.node_key
        session.current_attempt_id = attempt_id
        if task is not None:
            task.status = TaskStatus.IN_PROGRESS.value
            task.requires_human_review = True
            if progress_step is not None and progress_percentage is not None:
                task.update_progress(progress_step, progress_percentage)

        db.commit()
        db.refresh(gate)
        db.refresh(node)
        db.refresh(session)
        return gate

    @staticmethod
    def complete_script_attempt_and_open_review_gate_sync(
        db: Session,
        session: WorkflowSession,
        *,
        task: Task,
        workflow_state_id: str,
        attempt_id: int,
        trigger_reason: str,
        script_output: Dict[str, Any],
        artifact_ref: Dict[str, Any],
        script_preview_text: str,
        lease_token: Optional[str] = None,
        continuation_checkpoint: Optional[Dict[str, Any]] = None,
    ) -> WorkflowGate:
        node = RuntimeSessionService.get_node_by_key_sync(db, session.id, "script")
        if node is None:
            raise ValueError(f"Workflow node script not found for session {session.id}")
        attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, attempt_id)
        if attempt is None:
            raise ValueError(f"Workflow attempt {attempt_id} not found for session {session.id}")
        if lease_token is not None:
            RuntimeSessionService.assert_attempt_lease_sync(
                db,
                session,
                attempt_id=attempt_id,
                lease_token=lease_token,
                allow_expired=False,
            )

        review_contract = get_script_review_contract(session.input_payload) or {}
        payload = set_script_review_contract(session.input_payload, None)
        payload = clear_published_deliverable_ref(
            payload,
            node_key="script",
        )
        session.input_payload = payload

        artifact_refs = [dict(artifact_ref or {})]
        attempt.status = WorkflowAttemptStatus.SUCCEEDED.value
        _clear_attempt_lease_fields(attempt)
        attempt.output_artifacts = artifact_refs
        attempt.metrics = {
            "trigger_reason": trigger_reason,
            "scenes_generated": script_output.get("scenes_generated"),
            "total_scenes": script_output.get("total_scenes"),
            "review_contract_action": review_contract.get("action"),
        }
        if continuation_checkpoint is None:
            attempt.continuation_checkpoint = None
        else:
            attempt.continuation_checkpoint = OrchestrationStateAdapter.validate_continuation_checkpoint(
                continuation_checkpoint,
                require_decision_id=False,
            )

        gate = WorkflowGate(
            session_id=session.id,
            node_id=node.id,
            attempt_id=attempt.id,
            gate_name="script_review",
            gate_type="human_review",
            status=WorkflowGateStatus.AWAITING_HUMAN.value,
            scope={
                "scope_type": "episode",
                "scope_ref": str(workflow_state_id or ""),
            },
            artifact_refs=artifact_refs,
            facts={
                "workflow_state_id": workflow_state_id,
                "scenes_generated": script_output.get("scenes_generated"),
                "total_scenes": script_output.get("total_scenes"),
                "script_preview_text": script_preview_text,
                "trigger_reason": trigger_reason,
            },
            result_code=WorkflowGateStatus.AWAITING_HUMAN.value,
            reason_code=str(trigger_reason or "script_review_requested"),
            diagnostics=[],
            allowed_actions=["approve", "revise", "replan"],
            recommended_action="approve",
        )
        db.add(gate)
        db.flush()

        node.artifact_refs = artifact_refs
        node.diagnostics = []
        node.last_gate_id = gate.id
        node.status = WorkflowNodeStatus.PENDING_GATE.value
        session.status = WorkflowSessionStatus.WAITING_GATE.value
        session.current_node_key = node.node_key
        session.current_attempt_id = attempt.id
        if task is not None:
            task.status = TaskStatus.IN_PROGRESS.value
            task.requires_human_review = True
            task.update_progress("Waiting for script approval", 35)

        db.commit()
        db.refresh(gate)
        db.refresh(node)
        db.refresh(session)
        db.refresh(attempt)
        return gate

    @staticmethod
    def submit_gate_decision_sync(
        db: Session,
        session_id: int,
        *,
        node_key: str,
        action: str,
        feedback_text: Optional[str] = None,
        structured_constraints: Optional[Dict[str, Any]] = None,
        actor_type: str = "human",
        actor_id: Optional[str] = None,
    ) -> WorkflowGateDecision:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"approve", "revise", "replan"}:
            raise ValueError(f"Unsupported gate action: {action}")

        session = RuntimeSessionService.get_session_by_id_sync(db, session_id)
        if session is None:
            raise ValueError(f"Workflow session {session_id} not found")
        node = RuntimeSessionService.get_node_by_key_sync(db, session.id, node_key)
        if node is None:
            raise ValueError(f"Workflow node {node_key} not found for session {session.id}")
        gate = RuntimeSessionService.get_latest_gate_for_node_sync(db, session.id, node_key)
        if gate is None:
            raise ValueError(f"No gate found for node {node_key} in session {session.id}")
        if gate.status != WorkflowGateStatus.AWAITING_HUMAN.value:
            raise ValueError(f"Gate {gate.id} is not awaiting human review")
        allowed_actions = [str(item).strip().lower() for item in (gate.allowed_actions or [])]
        if allowed_actions and normalized_action not in allowed_actions:
            raise ValueError(f"Action {normalized_action} is not allowed for gate {gate.id}")
        attempt = RuntimeSessionService.get_attempt_by_id_sync(db, session.id, gate.attempt_id)
        if attempt is None:
            raise ValueError(f"Workflow attempt {gate.attempt_id} not found for session {session.id}")
        checkpoint = OrchestrationStateAdapter.validate_continuation_checkpoint(
            attempt.continuation_checkpoint,
            require_decision_id=False,
        )

        invalidation_scope = "workflow" if normalized_action == "replan" else "node"
        decision = WorkflowGateDecision(
            gate_id=gate.id,
            session_id=session.id,
            node_id=node.id,
            action=normalized_action,
            actor_type=str(actor_type or "human"),
            actor_id=actor_id,
            feedback_text=feedback_text,
            structured_constraints=structured_constraints or {},
            invalidation_scope=invalidation_scope,
        )
        db.add(decision)
        db.flush()
        checkpoint["decision_id"] = decision.id
        attempt.continuation_checkpoint = checkpoint

        gate.status = WorkflowGateStatus.DECIDED.value
        gate.result_code = normalized_action
        gate.reason_code = "human_gate_decision"
        node.status = (
            WorkflowNodeStatus.APPROVED.value
            if normalized_action == "approve"
            else WorkflowNodeStatus.NEEDS_REVISION.value
        )
        if normalized_action in {"revise", "replan"}:
            node.revision_index = int(node.revision_index or 0) + 1

        session.status = WorkflowSessionStatus.RESUMING.value
        session.current_node_key = node.node_key
        session.current_attempt_id = gate.attempt_id
        session.error_message = None

        payload = dict(session.input_payload or {})
        if normalized_action == "approve":
            deliverable = PublishedDeliverableService.mark_node_deliverable_approved_sync(
                db,
                session=session,
                node_key=node_key,
                attempt_id=gate.attempt_id,
            )
            payload = set_published_deliverable_ref(
                payload,
                node_key=node_key,
                ref=build_deliverable_ref(deliverable),
            )
        else:
            payload = clear_published_deliverable_ref(
                payload,
                node_key=node_key,
            )
        if normalized_action in {"revise", "replan"}:
            payload = set_script_review_contract(
                payload,
                build_script_review_contract(
                    action=normalized_action,
                    gate_id=gate.id,
                    decision_id=decision.id,
                    feedback_text=feedback_text,
                    structured_constraints=structured_constraints or {},
                ),
            )
        else:
            payload = set_script_review_contract(payload, None)
        session.input_payload = payload

        task = session.task
        if task is not None:
            task.status = TaskStatus.IN_PROGRESS.value
            task.requires_human_review = False
            if normalized_action == "approve":
                task.update_progress("Script approved, resuming generation", 40)
            elif normalized_action == "replan":
                task.update_progress("Script replan requested", 15)
            else:
                task.update_progress("Script revision requested", 20)

        db.commit()
        db.refresh(decision)
        db.refresh(gate)
        db.refresh(node)
        db.refresh(session)
        return decision

    @staticmethod
    def mark_session_running_sync(db: Session, session: WorkflowSession, task: Optional[Task] = None) -> WorkflowSession:
        session.status = WorkflowSessionStatus.RUNNING.value
        if not session.current_node_key:
            first_node = (
                db.query(WorkflowNodeState)
                .filter(WorkflowNodeState.session_id == session.id)
                .order_by(WorkflowNodeState.order_index.asc(), WorkflowNodeState.id.asc())
                .first()
            )
            if first_node is not None:
                session.current_node_key = first_node.node_key
                if first_node.status == WorkflowNodeStatus.QUEUED.value:
                    first_node.status = WorkflowNodeStatus.RUNNING.value
        if task is not None:
            task.status = TaskStatus.IN_PROGRESS.value
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def mark_session_resuming_sync(
        db: Session,
        session: WorkflowSession,
        *,
        task: Optional[Task] = None,
    ) -> WorkflowSession:
        node = None
        attempt = RuntimeSessionService.get_attempt_by_id_sync(
            db,
            session.id,
            session.current_attempt_id,
        )
        if attempt is not None and attempt.status == WorkflowAttemptStatus.RUNNING.value:
            attempt.status = WorkflowAttemptStatus.ABORTED.value
            _clear_attempt_lease_fields(attempt)
            node = RuntimeSessionService.get_node_by_key_sync(
                db,
                session.id,
                attempt.node.node_key if attempt.node is not None else session.current_node_key,
            )
            if node is not None and node.status == WorkflowNodeStatus.RUNNING.value:
                node.status = WorkflowNodeStatus.STALE.value
        session.status = WorkflowSessionStatus.RESUMING.value
        session.error_message = None
        if task is not None:
            task.status = TaskStatus.IN_PROGRESS.value
            task.error_message = None
        db.commit()
        if node is not None:
            db.refresh(node)
        if attempt is not None:
            db.refresh(attempt)
        db.refresh(session)
        return session

    @staticmethod
    def mark_session_completed_sync(
        db: Session,
        session: WorkflowSession,
        *,
        task: Optional[Task] = None,
        summary_output: Optional[Dict[str, Any]] = None,
    ) -> WorkflowSession:
        session.status = WorkflowSessionStatus.COMPLETED.value
        session.summary_output = summary_output or {}
        current_attempt = RuntimeSessionService.get_attempt_by_id_sync(
            db,
            session.id,
            session.current_attempt_id,
        )
        if current_attempt is not None:
            _clear_attempt_lease_fields(current_attempt)
        nodes = (
            db.query(WorkflowNodeState)
            .filter(WorkflowNodeState.session_id == session.id)
            .order_by(WorkflowNodeState.order_index.asc(), WorkflowNodeState.id.asc())
            .all()
        )
        for node in nodes:
            if node.status in {
                WorkflowNodeStatus.SKIPPED.value,
                WorkflowNodeStatus.FAILED.value,
                WorkflowNodeStatus.COMPLETED.value,
            }:
                continue
            if node.status in {
                WorkflowNodeStatus.QUEUED.value,
                WorkflowNodeStatus.STALE.value,
            }:
                node.status = WorkflowNodeStatus.SKIPPED.value
            else:
                node.status = WorkflowNodeStatus.COMPLETED.value
        visited_nodes = [
            node for node in nodes if node.status not in {WorkflowNodeStatus.SKIPPED.value}
        ]
        if visited_nodes:
            session.current_node_key = visited_nodes[-1].node_key
        if task is not None:
            task.status = TaskStatus.COMPLETED.value
            task.update_progress("Completed", 100)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def mark_session_failed_sync(
        db: Session,
        session: WorkflowSession,
        *,
        error_message: str,
        task: Optional[Task] = None,
    ) -> WorkflowSession:
        session.status = WorkflowSessionStatus.FAILED.value
        session.error_message = error_message
        if session.current_attempt_id is not None:
            current_attempt = RuntimeSessionService.get_attempt_by_id_sync(
                db,
                session.id,
                session.current_attempt_id,
            )
            if current_attempt is not None:
                _clear_attempt_lease_fields(current_attempt)
                if current_attempt.status == WorkflowAttemptStatus.RUNNING.value:
                    current_attempt.status = WorkflowAttemptStatus.FAILED.value
                    current_attempt.error_message = error_message
        if session.current_node_key:
            current_node = (
                db.query(WorkflowNodeState)
                .filter(
                    WorkflowNodeState.session_id == session.id,
                    WorkflowNodeState.node_key == session.current_node_key,
                )
                .first()
            )
            if current_node is not None:
                current_node.status = WorkflowNodeStatus.FAILED.value
        if task is not None:
            task.status = TaskStatus.FAILED.value
            task.error_message = error_message
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def mark_session_cancelled_sync(db: Session, session: WorkflowSession, task: Optional[Task] = None) -> WorkflowSession:
        session.status = WorkflowSessionStatus.CANCELLED.value
        if task is not None:
            task.status = TaskStatus.CANCELLED.value
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def _ensure_default_nodes_sync(db: Session, session: WorkflowSession) -> None:
        exists = (
            db.query(WorkflowNodeState.id)
            .filter(WorkflowNodeState.session_id == session.id)
            .first()
        )
        if exists is not None:
            return
        for blueprint in DEFAULT_NODE_BLUEPRINT:
            db.add(WorkflowNodeState(session_id=session.id, **blueprint))
        db.flush()

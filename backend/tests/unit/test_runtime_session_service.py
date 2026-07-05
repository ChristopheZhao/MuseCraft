import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from types import SimpleNamespace

from app.core.database import Base
from app.models import (
    AgentType,
    Task,
    TaskType,
    TaskStatus,
    WorkflowGateStatus,
    WorkflowNodeState,
    WorkflowSessionStatus,
    WorkflowSession,
    WorkflowNodeStatus,
)
from app.services.runtime_session_service import RuntimeSessionService
from app.services.published_deliverable_service import PublishedDeliverableService
from app.services.script_review_contract import get_script_review_contract
from app.services.orchestration_state_adapter import OrchestrationStateAdapter
from app.services.published_deliverable_service import get_published_deliverable_ref
import app.services.runtime_session_service as runtime_session_service_module


@pytest.fixture
def sync_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_task(db):
    task = Task(
        title="Runtime Test",
        description="runtime test",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.PENDING.value,
        input_parameters={"user_prompt": "test prompt"},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _build_continuation_checkpoint(
    *,
    anchor_type: str = OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
    node_key: str = "image",
    attempt_id: int = 1,
    decision_id: int | None = None,
):
    return OrchestrationStateAdapter.build_continuation_checkpoint(
        task_specs={
            AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
            AgentType.SCRIPT_WRITER: {"run": True, "order": 1},
            AgentType.IMAGE_GENERATOR: {"run": True, "order": 2},
        },
        conditional_task_specs={},
        candidate_agents=[
            AgentType.CONCEPT_PLANNER,
            AgentType.SCRIPT_WRITER,
            AgentType.IMAGE_GENERATOR,
        ],
        anchor_type=anchor_type,
        node_key=node_key,
        attempt_id=attempt_id,
        decision_id=decision_id,
    )


def test_get_or_create_session_initializes_default_nodes(sync_db):
    task = _create_task(sync_db)

    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)

    assert session.status == WorkflowSessionStatus.QUEUED.value
    assert task.output_metadata["workflow_session_id"] == session.id
    assert view is not None
    assert [node["node_key"] for node in view["nodes"]] == [
        "concept",
        "script",
        "image",
        "video",
        "voice",
        "compose",
        "audio",
        "quality",
    ]


def test_build_runtime_view_sync_returns_none_without_session(sync_db):
    task = _create_task(sync_db)

    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)

    assert view is None
    assert RuntimeSessionService.get_latest_session_for_task_sync(sync_db, task.id) is None


def test_build_runtime_view_sync_does_not_repair_missing_nodes(sync_db):
    task = _create_task(sync_db)
    session = WorkflowSession(
        task_db_id=task.id,
        mode="quick",
        shared_memory_id=str(task.task_id),
        status=WorkflowSessionStatus.QUEUED.value,
        input_payload=task.input_parameters or {},
        gate_policy={},
    )
    sync_db.add(session)
    sync_db.commit()
    sync_db.refresh(session)

    with pytest.raises(
        ValueError,
        match="missing workflow nodes; read path cannot repair runtime invariants",
    ):
        RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)

    node_count = (
        sync_db.query(WorkflowNodeState)
        .filter(WorkflowNodeState.session_id == session.id)
        .count()
    )
    assert node_count == 0


def test_mark_session_running_and_completed_updates_projection(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

    RuntimeSessionService.mark_session_running_sync(sync_db, session, task=task)
    running_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    assert running_view["status"] == WorkflowSessionStatus.RUNNING.value
    assert running_view["current_node_key"] == "concept"
    assert running_view["nodes"][0]["status"] == WorkflowNodeStatus.RUNNING.value

    RuntimeSessionService.mark_session_completed_sync(
        sync_db,
        session,
        task=task,
        summary_output={
            "final_video_url": "https://example.com/final.mp4",
            "role_continuity_diagnostics": {
                "status": "not_evaluated",
                "review_status": "unverified",
                "score_cap": 89,
                "fallback_reason": "role_continuity_visual_evidence_missing",
            },
        },
    )
    completed_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    assert completed_view["status"] == WorkflowSessionStatus.COMPLETED.value
    assert completed_view["summary_output"]["final_video_url"] == "https://example.com/final.mp4"
    assert completed_view["summary_output"]["role_continuity_diagnostics"]["review_status"] == "unverified"
    assert completed_view["nodes"][0]["status"] == WorkflowNodeStatus.COMPLETED.value
    assert all(
        node["status"] in {WorkflowNodeStatus.COMPLETED.value, WorkflowNodeStatus.SKIPPED.value}
        for node in completed_view["nodes"]
    )


def test_grant_attempt_lease_sync_assigns_control_plane_lease(sync_db, monkeypatch):
    lease_started_at = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: lease_started_at)
    monkeypatch.setattr(
        runtime_session_service_module.settings,
        "RUNTIME_ATTEMPT_LEASE_SECONDS",
        120,
    )
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="concept",
        task=task,
    )

    leased_attempt = RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:test",
        lease_token="lease-token-1",
    )

    assert leased_attempt.lease_token == "lease-token-1"
    assert leased_attempt.lease_owner == "orchestrator:test"
    assert leased_attempt.last_heartbeat_at == lease_started_at
    assert leased_attempt.lease_expires_at == lease_started_at + timedelta(seconds=120)
    assert RuntimeSessionService.is_attempt_lease_live(
        leased_attempt,
        as_of=lease_started_at + timedelta(seconds=119),
    )
    assert not RuntimeSessionService.is_attempt_lease_live(
        leased_attempt,
        as_of=lease_started_at + timedelta(seconds=120),
    )


def test_heartbeat_attempt_lease_sync_renews_expiry(sync_db, monkeypatch):
    initial_now = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    renewed_now = initial_now + timedelta(seconds=45)
    monkeypatch.setattr(
        runtime_session_service_module.settings,
        "RUNTIME_ATTEMPT_LEASE_SECONDS",
        180,
    )
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="image",
        task=task,
    )

    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: initial_now)
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:image",
        lease_token="lease-token-2",
    )

    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: renewed_now)
    renewed_attempt = RuntimeSessionService.heartbeat_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_token="lease-token-2",
    )

    assert renewed_attempt.last_heartbeat_at == renewed_now
    assert renewed_attempt.lease_expires_at == renewed_now + timedelta(seconds=180)


def test_assert_attempt_lease_sync_rejects_mismatch_and_expiry(sync_db, monkeypatch):
    lease_started_at = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    expired_now = lease_started_at + timedelta(seconds=301)
    monkeypatch.setattr(
        runtime_session_service_module.settings,
        "RUNTIME_ATTEMPT_LEASE_SECONDS",
        300,
    )
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="video",
        task=task,
    )

    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: lease_started_at)
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:video",
        lease_token="lease-token-3",
    )

    with pytest.raises(ValueError, match="token mismatch"):
        RuntimeSessionService.assert_attempt_lease_sync(
            sync_db,
            session,
            attempt_id=attempt.id,
            lease_token="wrong-token",
        )

    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: expired_now)
    with pytest.raises(ValueError, match="lease expired"):
        RuntimeSessionService.assert_attempt_lease_sync(
            sync_db,
            session,
            attempt_id=attempt.id,
            lease_token="lease-token-3",
        )


def test_release_attempt_lease_sync_clears_lease_fields(sync_db, monkeypatch):
    lease_started_at = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: lease_started_at)
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="audio",
        task=task,
    )
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:audio",
        lease_token="lease-token-4",
    )

    released_attempt = RuntimeSessionService.release_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_token="lease-token-4",
    )

    assert released_attempt.lease_token is None
    assert released_attempt.lease_owner is None
    assert released_attempt.last_heartbeat_at is None
    assert released_attempt.lease_expires_at is None
    assert not RuntimeSessionService.is_attempt_lease_live(released_attempt)


def test_complete_node_attempt_sync_clears_control_plane_lease(sync_db, monkeypatch):
    lease_started_at = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: lease_started_at)
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="image",
        task=task,
    )
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:image",
        lease_token="lease-token-complete",
    )

    completed_attempt = RuntimeSessionService.complete_node_attempt_sync(
        sync_db,
        session,
        node_key="image",
        attempt_id=attempt.id,
        lease_token="lease-token-complete",
        node_status=WorkflowNodeStatus.COMPLETED.value,
    )

    assert completed_attempt.status == "succeeded"
    assert completed_attempt.lease_token is None
    assert completed_attempt.lease_owner is None
    assert completed_attempt.lease_expires_at is None


def test_complete_node_attempt_sync_fresh_reads_cross_session_lease(sync_db, monkeypatch):
    lease_started_at = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    heartbeat_at = lease_started_at + timedelta(seconds=45)
    assert_at = lease_started_at + timedelta(seconds=100)
    monkeypatch.setattr(
        runtime_session_service_module.settings,
        "RUNTIME_ATTEMPT_LEASE_SECONDS",
        60,
    )
    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: lease_started_at)

    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="image",
        task=task,
    )
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:image",
        lease_token="lease-token-cross-session-complete",
    )

    SessionLocal = sessionmaker(bind=sync_db.get_bind(), autocommit=False, autoflush=False)
    other_db = SessionLocal()
    try:
        other_session = RuntimeSessionService.get_session_by_id_sync(other_db, session.id)
        monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: heartbeat_at)
        RuntimeSessionService.heartbeat_attempt_lease_sync(
            other_db,
            other_session,
            attempt_id=attempt.id,
            lease_token="lease-token-cross-session-complete",
        )
    finally:
        other_db.close()

    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: assert_at)
    completed_attempt = RuntimeSessionService.complete_node_attempt_sync(
        sync_db,
        session,
        node_key="image",
        attempt_id=attempt.id,
        lease_token="lease-token-cross-session-complete",
        node_status=WorkflowNodeStatus.COMPLETED.value,
    )

    assert completed_attempt.status == "succeeded"
    assert completed_attempt.lease_token is None


def test_fail_node_attempt_sync_clears_control_plane_lease(sync_db, monkeypatch):
    lease_started_at = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: lease_started_at)
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="video",
        task=task,
    )
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:video",
        lease_token="lease-token-fail",
    )

    failed_attempt = RuntimeSessionService.fail_node_attempt_sync(
        sync_db,
        session,
        node_key="video",
        attempt_id=attempt.id,
        lease_token="lease-token-fail",
        error_message="boom",
    )

    assert failed_attempt.status == "failed"
    assert failed_attempt.lease_token is None
    assert failed_attempt.lease_owner is None
    assert failed_attempt.lease_expires_at is None


def test_fail_node_attempt_sync_preserves_lease_snapshot_after_cross_session_heartbeat(sync_db, monkeypatch):
    lease_started_at = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    heartbeat_at = lease_started_at + timedelta(seconds=45)
    assert_at = lease_started_at + timedelta(seconds=100)
    monkeypatch.setattr(
        runtime_session_service_module.settings,
        "RUNTIME_ATTEMPT_LEASE_SECONDS",
        60,
    )
    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: lease_started_at)

    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="video",
        task=task,
    )
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:video",
        lease_token="lease-token-cross-session-fail",
    )

    SessionLocal = sessionmaker(bind=sync_db.get_bind(), autocommit=False, autoflush=False)
    other_db = SessionLocal()
    try:
        other_session = RuntimeSessionService.get_session_by_id_sync(other_db, session.id)
        monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: heartbeat_at)
        RuntimeSessionService.heartbeat_attempt_lease_sync(
            other_db,
            other_session,
            attempt_id=attempt.id,
            lease_token="lease-token-cross-session-fail",
        )
    finally:
        other_db.close()

    monkeypatch.setattr(runtime_session_service_module, "_now_utc", lambda: assert_at)
    failed_attempt = RuntimeSessionService.fail_node_attempt_sync(
        sync_db,
        session,
        node_key="video",
        attempt_id=attempt.id,
        lease_token="lease-token-cross-session-fail",
        error_message="boom",
        diagnostics=[{"code": "video_stage_failed", "message": "boom"}],
    )

    node = RuntimeSessionService.get_node_by_key_sync(sync_db, session.id, "video")
    snapshot = next(
        item for item in (node.diagnostics or [])
        if item.get("code") == "execution_lease_snapshot"
    )

    assert failed_attempt.status == "failed"
    assert failed_attempt.lease_token is None
    assert any(item.get("code") == "video_stage_failed" for item in (node.diagnostics or []))
    assert snapshot["reason_code"] == "node_attempt_failed"
    assert snapshot["lease_owner"] == "orchestrator:video"
    assert snapshot["lease_live"] is True
    assert snapshot["lease_expires_at"] == (heartbeat_at + timedelta(seconds=60)).isoformat()


def test_upsert_attempt_node_diagnostic_sync_replaces_keepalive_entry_for_same_attempt(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="video",
        task=task,
    )

    RuntimeSessionService.upsert_attempt_node_diagnostic_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        diagnostic={
            "code": "execution_host_keepalive",
            "attempt_id": attempt.id,
            "state": "failed",
            "reason_code": "heartbeat_error",
            "message": "boom",
            "captured_at": "2026-04-01T00:00:00+00:00",
        },
    )
    RuntimeSessionService.upsert_attempt_node_diagnostic_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        diagnostic={
            "code": "execution_host_keepalive",
            "attempt_id": attempt.id,
            "state": "stopped",
            "reason_code": "heartbeat_validation_failed",
            "message": "lease expired",
            "captured_at": "2026-04-01T00:01:00+00:00",
        },
    )

    node = RuntimeSessionService.get_node_by_key_sync(sync_db, session.id, "video")
    keepalive_diagnostics = [
        item
        for item in (node.diagnostics or [])
        if item.get("code") == "execution_host_keepalive"
    ]

    assert len(keepalive_diagnostics) == 1
    assert keepalive_diagnostics[0]["attempt_id"] == attempt.id
    assert keepalive_diagnostics[0]["state"] == "stopped"
    assert keepalive_diagnostics[0]["reason_code"] == "heartbeat_validation_failed"


def test_complete_node_attempt_sync_persists_completion_validation_failed_receipt(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="video",
        task=task,
    )
    leased_attempt = RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:video",
        lease_token="expired-token",
        lease_timeout_seconds=60,
    )
    leased_attempt.lease_expires_at = leased_attempt.last_heartbeat_at - timedelta(seconds=1)
    sync_db.commit()

    with pytest.raises(ValueError, match="execution lease expired"):
        RuntimeSessionService.complete_node_attempt_sync(
            sync_db,
            session,
            node_key="video",
            attempt_id=attempt.id,
            lease_token="expired-token",
            node_status=WorkflowNodeStatus.COMPLETED.value,
        )

    node = RuntimeSessionService.get_node_by_key_sync(sync_db, session.id, "video")
    completion_diagnostics = [
        item
        for item in (node.diagnostics or [])
        if item.get("code") == "execution_host_keepalive_completion_validation_failed"
    ]

    assert len(completion_diagnostics) == 1
    assert completion_diagnostics[0]["attempt_id"] == attempt.id
    assert completion_diagnostics[0]["reason_code"] == "completion_validation_failed"
    assert completion_diagnostics[0]["validation_error"] == f"Workflow attempt {attempt.id} execution lease expired"


def test_open_human_gate_exposes_waiting_gate_in_runtime_view(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        task=task,
        progress_step="Generating script",
        progress_percentage=15,
    )
    RuntimeSessionService.complete_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        attempt_id=attempt.id,
        output_artifacts=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        metrics={"scenes_generated": 1},
        artifact_refs=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        node_status=WorkflowNodeStatus.RUNNING.value,
    )
    RuntimeSessionService.open_human_gate_sync(
        sync_db,
        session,
        node_key="script",
        gate_name="script_review",
        gate_type="human_review",
        attempt_id=attempt.id,
        facts={"script_preview_text": "draft"},
        allowed_actions=["approve", "revise", "replan"],
        recommended_action="approve",
        task=task,
        progress_step="Waiting for script approval",
        progress_percentage=35,
    )
    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    nodes_by_key = {node["node_key"]: node for node in view["nodes"]}

    assert view["status"] == WorkflowSessionStatus.WAITING_GATE.value
    assert view["current_node_key"] == "script"
    assert view["active_gate"]["gate_name"] == "script_review"
    assert view["active_gate"]["result"] == WorkflowGateStatus.AWAITING_HUMAN.value
    assert view["active_gate"]["diagnostics"] == []
    assert view["active_gate"]["scope"] == {}
    assert view["active_gate"]["latest_decision"] is None
    assert view["resume_control"] == {
        "state": "waiting_gate",
        "can_resume": False,
        "reason_code": "awaiting_gate_decision",
    }
    assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.PENDING_GATE.value


def test_running_runtime_exposes_view_only_recent_resume_control(sync_db, monkeypatch):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="concept",
        task=task,
    )
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:concept",
        lease_token="lease-token-running",
    )
    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)

    assert view["resume_control"] == {
        "state": "view_only_running",
        "can_resume": False,
        "reason_code": "active_execution_lease",
    }


def test_running_runtime_exposes_transport_active_before_freshness(sync_db, monkeypatch):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="image",
        task=task,
    )
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:image",
        lease_token="lease-token-live",
    )
    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)

    assert view["resume_control"] == {
        "state": "view_only_running",
        "can_resume": False,
        "reason_code": "active_execution_lease",
    }


def test_stalled_runtime_exposes_resume_available_when_transport_is_not_live(sync_db, monkeypatch):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="image",
        task=task,
    )
    RuntimeSessionService.bind_attempt_continuation_checkpoint_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        continuation_checkpoint=_build_continuation_checkpoint(
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            node_key="image",
            attempt_id=attempt.id,
        ),
    )

    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)

    assert view["resume_control"] == {
        "state": "resume_available",
        "can_resume": True,
        "reason_code": "checkpoint_available",
    }


def test_resuming_runtime_exposes_view_only_resume_scheduled(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="image",
        task=task,
    )
    RuntimeSessionService.bind_attempt_continuation_checkpoint_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        continuation_checkpoint=_build_continuation_checkpoint(
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            node_key="image",
            attempt_id=attempt.id,
        ),
    )
    RuntimeSessionService.mark_session_resuming_sync(sync_db, session, task=task)

    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)

    assert view["resume_control"] == {
        "state": "view_only_running",
        "can_resume": False,
        "reason_code": "resume_scheduled",
    }


def test_running_runtime_without_checkpoint_is_resume_blocked(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

    RuntimeSessionService.start_node_attempt_sync(sync_db, session, node_key="concept", task=task)

    resume_control = RuntimeSessionService.get_resume_control_sync(sync_db, task, session)

    assert resume_control == {
        "state": "resume_blocked",
        "can_resume": False,
        "reason_code": "missing_continuation_checkpoint",
    }


def test_build_runtime_view_keeps_irrecoverable_stale_quick_runtime_read_only(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        task=task,
        progress_step="Generating script",
        progress_percentage=15,
    )

    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    sync_db.refresh(task)
    sync_db.refresh(session)
    sync_db.refresh(attempt)

    assert view["status"] == WorkflowSessionStatus.RUNNING.value
    assert view["resume_control"] == {
        "state": "resume_blocked",
        "can_resume": False,
        "reason_code": "missing_continuation_checkpoint",
    }
    assert view["error_message"] is None
    assert task.status == TaskStatus.IN_PROGRESS.value
    assert session.status == WorkflowSessionStatus.RUNNING.value
    assert attempt.status == "running"
    assert attempt.error_message is None


def test_stalled_runtime_exposes_resume_blocked_when_checkpoint_is_missing(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

    RuntimeSessionService.start_node_attempt_sync(sync_db, session, node_key="voice", task=task)

    resume_control = RuntimeSessionService.get_resume_control_sync(sync_db, task, session)

    assert resume_control == {
        "state": "resume_blocked",
        "can_resume": False,
        "reason_code": "missing_continuation_checkpoint",
    }


def test_complete_script_attempt_and_open_review_gate_sync_rehomes_runtime_mutation(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    session.input_payload = {
        "user_prompt": "test prompt",
        "published_deliverables": {
            "script": {
                "type": "published_deliverable",
                "deliverable_id": 3,
                "deliverable_type": "script",
                "scope_type": "episode",
                "scope_id": "episode",
                "attempt_id": 1,
                "revision_no": 0,
                "payload_ref": "tmp/approved_script_payload.json",
                "summary": {"total_scenes": 1},
                "is_candidate": False,
                "is_approved": True,
            }
        },
    }
    sync_db.commit()

    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        task=task,
        progress_step="Generating script",
        progress_percentage=15,
    )
    RuntimeSessionService.grant_attempt_lease_sync(
        sync_db,
        session,
        attempt_id=attempt.id,
        lease_owner="orchestrator:script",
        lease_token="lease-token-script-review",
    )
    artifact_ref = {
        "type": "published_deliverable",
        "deliverable_id": 9,
        "deliverable_type": "script",
        "scope_type": "episode",
        "scope_id": "episode",
        "attempt_id": attempt.id,
        "revision_no": 0,
        "payload_ref": "tmp/script_payload.json",
        "summary": {"total_scenes": 1},
        "is_candidate": True,
        "is_approved": False,
    }

    gate = RuntimeSessionService.complete_script_attempt_and_open_review_gate_sync(
        sync_db,
        session,
        task=task,
        workflow_state_id="wf-script-review",
        attempt_id=attempt.id,
        trigger_reason="replan",
        script_output={"scenes_generated": 1, "total_scenes": 1},
        artifact_ref=artifact_ref,
        script_preview_text="draft preview",
        lease_token="lease-token-script-review",
        continuation_checkpoint=_build_continuation_checkpoint(
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
            node_key="script",
            attempt_id=attempt.id,
        ),
    )

    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    refreshed_session = RuntimeSessionService.get_session_by_id_sync(sync_db, session.id)
    refreshed_attempt = RuntimeSessionService.get_attempt_by_id_sync(sync_db, session.id, attempt.id)
    script_payload = get_published_deliverable_ref(refreshed_session.input_payload, node_key="script")

    assert gate.gate_name == "script_review"
    assert gate.result_code == WorkflowGateStatus.AWAITING_HUMAN.value
    assert gate.reason_code == "replan"
    assert refreshed_attempt.lease_token is None
    assert gate.scope == {"scope_type": "episode", "scope_ref": "wf-script-review"}
    assert view["status"] == WorkflowSessionStatus.WAITING_GATE.value
    assert view["active_gate"]["gate_name"] == "script_review"
    assert view["active_gate"]["result"] == WorkflowGateStatus.AWAITING_HUMAN.value
    assert view["active_gate"]["reason_code"] == "replan"
    assert view["active_gate"]["scope"] == {"scope_type": "episode", "scope_ref": "wf-script-review"}
    assert view["active_gate"]["diagnostics"] == []
    assert view["active_gate"]["facts"]["script_preview_text"] == "draft preview"
    assert refreshed_session.current_attempt_id == attempt.id
    assert script_payload is None
    assert get_script_review_contract(refreshed_session.input_payload) is None
    assert refreshed_attempt.continuation_checkpoint["decision_id"] is None
    assert refreshed_attempt.continuation_checkpoint["candidate_agents"] == [
        AgentType.CONCEPT_PLANNER.value,
        AgentType.SCRIPT_WRITER.value,
        AgentType.IMAGE_GENERATOR.value,
    ]


def test_submit_gate_decision_marks_revision_state(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    session.input_payload = {
        "published_deliverables": {
            "script": {
                "type": "published_deliverable",
                "deliverable_id": 11,
                "deliverable_type": "script",
                "scope_type": "episode",
                "scope_id": "episode",
                "attempt_id": 7,
                "revision_no": 0,
                "payload_ref": "tmp/approved_script_payload.json",
                "summary": {"total_scenes": 1},
                "is_candidate": False,
                "is_approved": True,
            }
        }
    }
    sync_db.commit()

    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        task=task,
        progress_step="Generating script",
        progress_percentage=15,
    )
    RuntimeSessionService.complete_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        attempt_id=attempt.id,
        output_artifacts=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        metrics={"scenes_generated": 1},
        artifact_refs=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        node_status=WorkflowNodeStatus.RUNNING.value,
    )
    attempt.continuation_checkpoint = _build_continuation_checkpoint(
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
        node_key="script",
        attempt_id=attempt.id,
    )
    sync_db.commit()
    RuntimeSessionService.open_human_gate_sync(
        sync_db,
        session,
        node_key="script",
        gate_name="script_review",
        gate_type="human_review",
        attempt_id=attempt.id,
        facts={"script_preview_text": "draft"},
        allowed_actions=["approve", "revise", "replan"],
        recommended_action="approve",
        task=task,
        progress_step="Waiting for script approval",
        progress_percentage=35,
    )

    decision = RuntimeSessionService.submit_gate_decision_sync(
        sync_db,
        session.id,
        node_key="script",
        action="revise",
        feedback_text="tighten scene pacing",
        structured_constraints={"keep_character": True},
    )
    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    nodes_by_key = {node["node_key"]: node for node in view["nodes"]}

    assert decision.action == "revise"
    assert view["status"] == WorkflowSessionStatus.RESUMING.value
    assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.NEEDS_REVISION.value
    assert nodes_by_key["script"]["revision_index"] == 1
    assert view["active_gate"]["latest_decision"]["feedback_text"] == "tighten scene pacing"
    refreshed_session = RuntimeSessionService.get_session_by_id_sync(sync_db, session.id)
    refreshed_attempt = RuntimeSessionService.get_attempt_by_id_sync(sync_db, session.id, attempt.id)
    review_contract = get_script_review_contract(refreshed_session.input_payload)
    assert review_contract is not None
    assert review_contract["action"] == "revise"
    assert review_contract["feedback_text"] == "tighten scene pacing"
    assert review_contract["structured_constraints"] == {"keep_character": True}
    assert get_published_deliverable_ref(refreshed_session.input_payload, node_key="script") is None
    assert refreshed_attempt.continuation_checkpoint["decision_id"] == decision.id


def test_submit_gate_decision_requires_pending_continuation_checkpoint(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        task=task,
        progress_step="Generating script",
        progress_percentage=15,
    )
    RuntimeSessionService.complete_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        attempt_id=attempt.id,
        output_artifacts=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        metrics={"scenes_generated": 1},
        artifact_refs=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        node_status=WorkflowNodeStatus.RUNNING.value,
    )
    RuntimeSessionService.open_human_gate_sync(
        sync_db,
        session,
        node_key="script",
        gate_name="script_review",
        gate_type="human_review",
        attempt_id=attempt.id,
        facts={"script_preview_text": "draft"},
        allowed_actions=["approve", "revise", "replan"],
        recommended_action="approve",
        task=task,
        progress_step="Waiting for script approval",
        progress_percentage=35,
    )

    with pytest.raises(ValueError, match="Continuation checkpoint must be a dict"):
        RuntimeSessionService.submit_gate_decision_sync(
            sync_db,
            session.id,
            node_key="script",
            action="approve",
        )


def test_load_active_script_continuation_sync_validates_latest_decision_binding(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        task=task,
        progress_step="Generating script",
        progress_percentage=15,
    )
    gate = RuntimeSessionService.complete_script_attempt_and_open_review_gate_sync(
        sync_db,
        session,
        task=task,
        workflow_state_id="wf-script-review",
        attempt_id=attempt.id,
        trigger_reason="initial",
        script_output={"scenes_generated": 1, "total_scenes": 1},
        artifact_ref={
            "type": "published_deliverable",
            "deliverable_id": 9,
            "deliverable_type": "script",
            "scope_type": "episode",
            "scope_id": "episode",
            "attempt_id": attempt.id,
            "revision_no": 0,
            "payload_ref": "tmp/script_payload.json",
            "summary": {"total_scenes": 1},
            "is_candidate": True,
            "is_approved": False,
        },
        script_preview_text="draft preview",
        continuation_checkpoint=_build_continuation_checkpoint(
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
            node_key="script",
            attempt_id=attempt.id,
        ),
    )
    decision = RuntimeSessionService.submit_gate_decision_sync(
        sync_db,
        session.id,
        node_key="script",
        action="revise",
        feedback_text="tighten scene pacing",
    )

    checkpoint = RuntimeSessionService.load_active_script_continuation_sync(
        sync_db,
        RuntimeSessionService.get_session_by_id_sync(sync_db, session.id),
    )
    assert checkpoint["decision_id"] == decision.id
    assert checkpoint["task_specs"][AgentType.SCRIPT_WRITER.value]["run"] is True

    attempt = RuntimeSessionService.get_attempt_by_id_sync(sync_db, session.id, gate.attempt_id)
    stale_checkpoint = dict(attempt.continuation_checkpoint or {})
    stale_checkpoint["decision_id"] = decision.id + 1
    attempt.continuation_checkpoint = stale_checkpoint
    sync_db.commit()

    with pytest.raises(ValueError, match="decision binding is stale"):
        RuntimeSessionService.load_active_script_continuation_sync(
            sync_db,
            RuntimeSessionService.get_session_by_id_sync(sync_db, session.id),
        )


def test_consume_script_approval_continuation_sync_rehomes_runtime_transition(sync_db):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        task=task,
        progress_step="Generating script",
        progress_percentage=15,
    )
    RuntimeSessionService.complete_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        attempt_id=attempt.id,
        output_artifacts=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        metrics={"scenes_generated": 1},
        artifact_refs=[{"type": "shared_fact", "ref": "project.scene_scripts"}],
        node_status=WorkflowNodeStatus.RUNNING.value,
    )
    attempt.continuation_checkpoint = _build_continuation_checkpoint(
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
        node_key="script",
        attempt_id=attempt.id,
    )
    sync_db.commit()
    RuntimeSessionService.open_human_gate_sync(
        sync_db,
        session,
        node_key="script",
        gate_name="script_review",
        gate_type="human_review",
        attempt_id=attempt.id,
        facts={"script_preview_text": "draft"},
        allowed_actions=["approve", "revise", "replan"],
        recommended_action="approve",
        task=task,
        progress_step="Waiting for script approval",
        progress_percentage=35,
    )
    PublishedDeliverableService.publish_script_deliverable_sync(
        sync_db,
        session=session,
        workflow_id=str(task.task_id),
        attempt_id=attempt.id,
        payload={"scene_scripts": {"1": {"script_text": "draft"}}},
        summary={"total_scenes": 1},
    )

    RuntimeSessionService.submit_gate_decision_sync(
        sync_db,
        session.id,
        node_key="script",
        action="approve",
        feedback_text="looks good",
    )

    RuntimeSessionService.consume_script_approval_continuation_sync(
        sync_db,
        session,
        task=task,
    )

    view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
    nodes_by_key = {node["node_key"]: node for node in view["nodes"]}

    assert view["status"] == WorkflowSessionStatus.RUNNING.value
    assert view["current_node_key"] is None
    assert view["current_attempt_id"] is None
    assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.COMPLETED.value
    assert task.status == TaskStatus.IN_PROGRESS.value
    assert task.requires_human_review is False


def test_mark_session_cancelled_for_task_cancels_without_runtime_session(monkeypatch):
    task = SimpleNamespace(id=7, status=TaskStatus.IN_PROGRESS.value)
    commit_events = {"count": 0}

    class _FakeDb:
        async def commit(self):
            commit_events["count"] += 1

    async def _return_none(*args, **kwargs):
        return None

    monkeypatch.setattr(RuntimeSessionService, "get_latest_session_for_task", _return_none)

    result = asyncio.run(RuntimeSessionService.mark_session_cancelled_for_task(_FakeDb(), task))

    assert result is None
    assert task.status == TaskStatus.CANCELLED.value
    assert commit_events["count"] == 1


def test_build_runtime_view_async_returns_none_without_bootstrapping_session(monkeypatch):
    task = SimpleNamespace(
        id=7,
        status=TaskStatus.IN_PROGRESS.value,
        input_parameters={"user_prompt": "test prompt"},
    )
    calls = {"create": 0, "ensure": 0}

    async def _return_none(*args, **kwargs):
        return None

    async def _forbidden_create(*args, **kwargs):
        calls["create"] += 1
        raise AssertionError("read path must not create runtime sessions")

    async def _forbidden_ensure(*args, **kwargs):
        calls["ensure"] += 1
        raise AssertionError("read path must not repair default nodes")

    monkeypatch.setattr(RuntimeSessionService, "get_latest_session_for_task", _return_none)
    monkeypatch.setattr(RuntimeSessionService, "create_session_for_task", _forbidden_create)
    monkeypatch.setattr(RuntimeSessionService, "_ensure_default_nodes_async", _forbidden_ensure)

    view = asyncio.run(RuntimeSessionService.build_runtime_view_for_task(object(), task))

    assert view is None
    assert calls == {"create": 0, "ensure": 0}


def test_build_runtime_view_async_does_not_call_reconcile_helper(sync_db, monkeypatch):
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    RuntimeSessionService.start_node_attempt_sync(sync_db, session, node_key="script", task=task)
    calls = {"reconcile": 0}

    class _FakeAsyncDb:
        async def run_sync(self, fn):
            return fn(sync_db)

    async def _fake_get_latest_session(db, task_db_id):
        assert task_db_id == task.id
        return RuntimeSessionService.get_latest_session_for_task_sync(sync_db, task_db_id)

    async def _fake_load_runtime_nodes(db, session_id):
        return list(RuntimeSessionService._load_runtime_nodes_sync(sync_db, session_id))

    async def _fake_get_latest_gate(db, session_id):
        return None

    def _forbidden_reconcile(*args, **kwargs):
        calls["reconcile"] += 1
        raise AssertionError("runtime view builder must not reconcile or fail runtimes")

    monkeypatch.setattr(
        RuntimeSessionService,
        "reconcile_irrecoverable_quick_runtime_sync",
        staticmethod(_forbidden_reconcile),
    )
    monkeypatch.setattr(RuntimeSessionService, "get_latest_session_for_task", _fake_get_latest_session)
    monkeypatch.setattr(RuntimeSessionService, "_load_runtime_nodes_async", _fake_load_runtime_nodes)
    monkeypatch.setattr(RuntimeSessionService, "_get_latest_gate_for_session_async", _fake_get_latest_gate)

    view = asyncio.run(RuntimeSessionService.build_runtime_view_for_task(_FakeAsyncDb(), task))

    assert calls["reconcile"] == 0
    assert view["status"] == WorkflowSessionStatus.RUNNING.value
    assert view["resume_control"] == {
        "state": "resume_blocked",
        "can_resume": False,
        "reason_code": "missing_continuation_checkpoint",
    }


def test_create_session_for_task_refreshes_task_after_commit(monkeypatch):
    refreshed_targets = []

    class _FakeAsyncDb:
        def __init__(self):
            self._added = []

        def add(self, obj):
            self._added.append(obj)

        async def flush(self):
            for obj in self._added:
                if getattr(obj, "id", None) is None:
                    obj.id = 123

        async def commit(self):
            return None

        async def refresh(self, obj):
            refreshed_targets.append(obj)

    async def _noop_ensure_default_nodes(db, session):
        return None

    monkeypatch.setattr(RuntimeSessionService, "_ensure_default_nodes_async", _noop_ensure_default_nodes)

    task = SimpleNamespace(
        id=7,
        task_id="task-7",
        input_parameters={"user_prompt": "test prompt"},
        output_metadata={},
    )
    fake_db = _FakeAsyncDb()

    session = asyncio.run(RuntimeSessionService.create_session_for_task(fake_db, task, mode="quick"))

    assert session.id == 123
    assert task.output_metadata["workflow_session_id"] == 123
    assert refreshed_targets[0] is session
    assert refreshed_targets[1] is task

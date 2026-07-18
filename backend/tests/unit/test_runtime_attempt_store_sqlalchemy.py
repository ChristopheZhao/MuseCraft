from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.domain import (
    AgentType,
    JsonObjectPayload,
    RuntimeAttemptHeartbeatCommand,
    RuntimeAttemptLeaseCommand,
    RuntimeAttemptReleaseCommand,
    RuntimeAttemptStartCommand,
    RuntimeAttemptStore,
    RuntimeContinuationBindCommand,
    RuntimeGateStore,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    TaskStatus,
    TaskType,
    WorkflowAttemptStatus,
    WorkflowGateStatus,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)
from app.infrastructure import SqlAlchemyRuntimeAttemptStore, SqlAlchemyRuntimeAttemptUnitOfWork
from app.models import (
    Task,
    WorkflowGate,
    WorkflowNodeAttempt,
    WorkflowNodeState,
    WorkflowPublishedDeliverable,
    WorkflowSession,
)
from app.services.orchestration_state_adapter import OrchestrationStateAdapter
from app.services.runtime_attempt_control_plane import RuntimeAttemptControlPlane
from app.services.runtime_gate_control_plane import RuntimeGateControlPlane
from app.services.script_gate_decision_control_plane import ScriptGateDecisionControlPlane


@pytest.fixture
def runtime_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = session_factory()
    try:
        yield db, session_factory
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _seed_runtime(db):
    task = Task(
        task_id="public-task-1",
        title="Runtime store test",
        description="runtime store test",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.PENDING.value,
        input_parameters={"user_prompt": "test"},
    )
    db.add(task)
    db.flush()
    session = WorkflowSession(
        task_db_id=task.id,
        mode="quick",
        status=WorkflowSessionStatus.QUEUED.value,
        input_payload={"user_prompt": "test"},
        gate_policy={},
        summary_output={},
    )
    db.add(session)
    db.flush()
    node = WorkflowNodeState(
        session_id=session.id,
        node_key="image",
        node_type="image",
        order_index=30,
        scope_type="episode",
        scope_ref="episode",
        status=WorkflowNodeStatus.QUEUED.value,
        artifact_refs=[],
        diagnostics=[],
    )
    db.add(node)
    db.commit()
    return task, session, node


def _start_command(
    session_id: int,
    *,
    node_key: str = "image",
) -> RuntimeAttemptStartCommand:
    return RuntimeAttemptStartCommand(
        session_id=session_id,
        node_key=node_key,
        trigger_reason="initial",
        requested_by="orchestrator",
        input_contract=JsonObjectPayload.from_mapping(
            {"scope": "episode"},
            field_path="test.input_contract",
        ),
        expected_session_status=WorkflowSessionStatus.QUEUED,
        expected_node_status=WorkflowNodeStatus.QUEUED,
        task_transition=RuntimeTaskTransition(
            task_id="public-task-1",
            expected_status=TaskStatus.PENDING,
            target_status=TaskStatus.IN_PROGRESS,
            progress_step="Generating images",
            progress_percentage=30,
            requires_human_review=False,
        ),
    )


def test_attempt_store_maps_stable_task_identity_and_strict_records(runtime_db):
    db, _ = runtime_db
    _, session, _ = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)

    record = store.load_session(session.id)

    assert record is not None
    assert record.task_id == "public-task-1"
    assert record.status is WorkflowSessionStatus.QUEUED
    assert isinstance(store, RuntimeAttemptStore)


def test_attempt_store_rejects_corrupt_persisted_status(runtime_db):
    db, _ = runtime_db
    _, session, _ = _seed_runtime(db)
    session.status = "mystery"
    db.commit()

    with pytest.raises(RuntimeStoreError) as caught:
        SqlAlchemyRuntimeAttemptStore(db).load_session(session.id)

    assert caught.value.reason_code is RuntimeStoreReason.INTEGRITY_ERROR
    assert caught.value.operation == "load_session"


def test_start_attempt_applies_explicit_runtime_and_task_transitions(runtime_db):
    db, _ = runtime_db
    task, session, node = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)

    attempt = store.start_attempt(_start_command(session.id))
    db.commit()
    db.refresh(task)
    db.refresh(session)
    db.refresh(node)

    assert attempt.status is WorkflowAttemptStatus.RUNNING
    assert attempt.input_contract.to_dict() == {"scope": "episode"}
    assert session.status == WorkflowSessionStatus.RUNNING.value
    assert session.current_node_key == "image"
    assert session.current_attempt_id == attempt.attempt_id
    assert node.status == WorkflowNodeStatus.RUNNING.value
    assert task.status == TaskStatus.IN_PROGRESS.value
    assert task.current_step == "Generating images"
    assert task.progress_percentage == 30


def test_start_attempt_fails_closed_on_session_state_conflict(runtime_db):
    db, _ = runtime_db
    _, session, _ = _seed_runtime(db)
    session.status = WorkflowSessionStatus.RUNNING.value
    db.commit()

    with pytest.raises(RuntimeStoreError) as caught:
        SqlAlchemyRuntimeAttemptStore(db).start_attempt(_start_command(session.id))

    assert caught.value.reason_code is RuntimeStoreReason.STATE_CONFLICT
    assert db.query(WorkflowNodeAttempt).count() == 0


def test_attempt_lease_lifecycle_uses_caller_selected_times_and_token(runtime_db):
    db, _ = runtime_db
    _, session, _ = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    started_at = datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc)

    leased = store.grant_attempt_lease(
        RuntimeAttemptLeaseCommand(
            session_id=session.id,
            attempt_id=attempt.attempt_id,
            lease_owner="orchestrator:image",
            lease_token="lease-1",
            heartbeat_at=started_at,
            lease_expires_at=started_at + timedelta(seconds=60),
        )
    )
    renewed = store.heartbeat_attempt_lease(
        RuntimeAttemptHeartbeatCommand(
            session_id=session.id,
            attempt_id=attempt.attempt_id,
            lease_token="lease-1",
            heartbeat_at=started_at + timedelta(seconds=30),
            lease_expires_at=started_at + timedelta(seconds=90),
        )
    )
    released = store.release_attempt_lease(
        RuntimeAttemptReleaseCommand(
            session_id=session.id,
            attempt_id=attempt.attempt_id,
            lease_token="lease-1",
            expected_attempt_status=WorkflowAttemptStatus.RUNNING,
        )
    )

    assert leased.lease_expires_at == started_at + timedelta(seconds=60)
    assert renewed.last_heartbeat_at == started_at + timedelta(seconds=30)
    assert renewed.lease_expires_at == started_at + timedelta(seconds=90)
    assert released.lease_token is None
    assert released.lease_owner is None


def test_attempt_heartbeat_rejects_token_mismatch_and_expired_lease(runtime_db):
    db, _ = runtime_db
    _, session, _ = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    started_at = datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc)
    store.grant_attempt_lease(
        RuntimeAttemptLeaseCommand(
            session_id=session.id,
            attempt_id=attempt.attempt_id,
            lease_owner="orchestrator:image",
            lease_token="lease-1",
            heartbeat_at=started_at,
            lease_expires_at=started_at + timedelta(seconds=60),
        )
    )

    with pytest.raises(RuntimeStoreError) as mismatch:
        store.heartbeat_attempt_lease(
            RuntimeAttemptHeartbeatCommand(
                session_id=session.id,
                attempt_id=attempt.attempt_id,
                lease_token="wrong-token",
                heartbeat_at=started_at + timedelta(seconds=10),
                lease_expires_at=started_at + timedelta(seconds=70),
            )
        )
    with pytest.raises(RuntimeStoreError) as expired:
        store.heartbeat_attempt_lease(
            RuntimeAttemptHeartbeatCommand(
                session_id=session.id,
                attempt_id=attempt.attempt_id,
                lease_token="lease-1",
                heartbeat_at=started_at + timedelta(seconds=60),
                lease_expires_at=started_at + timedelta(seconds=120),
            )
        )

    assert mismatch.value.reason_code is RuntimeStoreReason.LEASE_CONFLICT
    assert expired.value.reason_code is RuntimeStoreReason.LEASE_CONFLICT


def test_bind_continuation_requires_expected_attempt_status(runtime_db):
    db, _ = runtime_db
    _, session, _ = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    checkpoint = JsonObjectPayload.from_mapping(
        {"anchor_type": "runtime_checkpoint", "attempt_id": attempt.attempt_id},
        field_path="test.continuation_checkpoint",
    )

    bound = store.bind_attempt_continuation(
        RuntimeContinuationBindCommand(
            session_id=session.id,
            attempt_id=attempt.attempt_id,
            continuation_checkpoint=checkpoint,
        )
    )
    db_attempt = db.get(WorkflowNodeAttempt, attempt.attempt_id)
    db_attempt.status = WorkflowAttemptStatus.SUCCEEDED.value
    db.commit()

    with pytest.raises(RuntimeStoreError) as caught:
        store.bind_attempt_continuation(
            RuntimeContinuationBindCommand(
                session_id=session.id,
                attempt_id=attempt.attempt_id,
                continuation_checkpoint=checkpoint,
            )
        )

    assert bound.continuation_checkpoint == checkpoint
    assert caught.value.reason_code is RuntimeStoreReason.STATE_CONFLICT


def test_attempt_unit_of_work_rolls_back_without_explicit_commit(runtime_db):
    db, session_factory = runtime_db
    _, session, _ = _seed_runtime(db)
    session_id = session.id
    db.close()

    with SqlAlchemyRuntimeAttemptUnitOfWork(session_factory) as unit_of_work:
        unit_of_work.runtime.start_attempt(_start_command(session_id))

    inspect_db = session_factory()
    try:
        assert inspect_db.query(WorkflowNodeAttempt).count() == 0
        persisted_session = inspect_db.get(WorkflowSession, session_id)
        assert persisted_session.status == WorkflowSessionStatus.QUEUED.value
    finally:
        inspect_db.close()


def test_control_plane_completes_attempt_with_live_lease(runtime_db):
    db, _ = runtime_db
    _, session, node = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    observed_at = datetime(2026, 7, 19, 2, 0, tzinfo=timezone.utc)
    store.grant_attempt_lease(
        RuntimeAttemptLeaseCommand(
            session_id=session.id,
            attempt_id=attempt.attempt_id,
            lease_owner="orchestrator:image",
            lease_token="completion-lease",
            heartbeat_at=observed_at - timedelta(seconds=10),
            lease_expires_at=observed_at + timedelta(seconds=50),
        )
    )
    control_plane = RuntimeAttemptControlPlane(store, clock=lambda: observed_at)

    completed = control_plane.complete_attempt(
        session_id=session.id,
        node_key="image",
        attempt_id=attempt.attempt_id,
        expected_lease_token="completion-lease",
        target_node_status=WorkflowNodeStatus.COMPLETED,
    )
    db.commit()
    db.refresh(node)

    assert completed.status is WorkflowAttemptStatus.SUCCEEDED
    assert completed.lease_token is None
    assert node.status == WorkflowNodeStatus.COMPLETED.value


def test_control_plane_completion_without_token_cannot_clear_active_lease(runtime_db):
    db, _ = runtime_db
    _, session, _ = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    observed_at = datetime(2026, 7, 19, 2, 0, tzinfo=timezone.utc)
    store.grant_attempt_lease(
        RuntimeAttemptLeaseCommand(
            session_id=session.id,
            attempt_id=attempt.attempt_id,
            lease_owner="orchestrator:image",
            lease_token="completion-lease",
            heartbeat_at=observed_at - timedelta(seconds=10),
            lease_expires_at=observed_at + timedelta(seconds=50),
        )
    )
    control_plane = RuntimeAttemptControlPlane(store, clock=lambda: observed_at)

    with pytest.raises(RuntimeStoreError) as caught:
        control_plane.complete_attempt(
            session_id=session.id,
            node_key="image",
            attempt_id=attempt.attempt_id,
            expected_lease_token=None,
            target_node_status=WorkflowNodeStatus.COMPLETED,
        )

    persisted = store.load_attempt(session.id, attempt.attempt_id)
    assert caught.value.reason_code is RuntimeStoreReason.LEASE_CONFLICT
    assert persisted.status is WorkflowAttemptStatus.RUNNING
    assert persisted.lease_token == "completion-lease"


def test_control_plane_failure_preserves_diagnostics_and_appends_lease_snapshot(runtime_db):
    db, _ = runtime_db
    _, session, node = _seed_runtime(db)
    node.diagnostics = [{"code": "existing", "message": "keep"}]
    db.commit()
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    observed_at = datetime(2026, 7, 19, 2, 0, tzinfo=timezone.utc)
    store.grant_attempt_lease(
        RuntimeAttemptLeaseCommand(
            session_id=session.id,
            attempt_id=attempt.attempt_id,
            lease_owner="orchestrator:image",
            lease_token="failure-lease",
            heartbeat_at=observed_at - timedelta(seconds=10),
            lease_expires_at=observed_at + timedelta(seconds=50),
        )
    )
    control_plane = RuntimeAttemptControlPlane(store, clock=lambda: observed_at)
    stage_diagnostic = JsonObjectPayload.from_mapping(
        {"code": "image_stage_failed", "message": "boom"},
        field_path="test.failure_diagnostic",
    )

    failed = control_plane.fail_attempt(
        session_id=session.id,
        node_key="image",
        attempt_id=attempt.attempt_id,
        expected_lease_token="failure-lease",
        error_message="boom",
        diagnostics=(stage_diagnostic,),
    )
    db.commit()
    node_record = store.load_node(session.id, "image")
    diagnostics = [payload.to_dict() for payload in node_record.diagnostics]

    assert failed.status is WorkflowAttemptStatus.FAILED
    assert failed.lease_token is None
    assert node_record.status is WorkflowNodeStatus.FAILED
    assert [item["code"] for item in diagnostics] == [
        "existing",
        "image_stage_failed",
        "execution_lease_snapshot",
    ]
    assert diagnostics[-1]["lease_live"] is True
    assert diagnostics[-1]["lease_owner"] == "orchestrator:image"


def test_gate_control_plane_opens_human_gate_with_explicit_runtime_targets(runtime_db):
    db, _ = runtime_db
    task, session, node = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    attempt_control = RuntimeAttemptControlPlane(store)
    attempt_control.complete_attempt(
        session_id=session.id,
        node_key="image",
        attempt_id=attempt.attempt_id,
        expected_lease_token=None,
        target_node_status=WorkflowNodeStatus.RUNNING,
    )
    artifact_ref = JsonObjectPayload.from_mapping(
        {"type": "published_deliverable", "deliverable_id": 9},
        field_path="test.gate_artifact_ref",
    )
    session_payload = JsonObjectPayload.from_mapping(
        {"user_prompt": "test", "review_pending": True},
        field_path="test.gate_session_payload",
    )
    gate_control = RuntimeGateControlPlane(store)

    gate = gate_control.open_human_gate(
        session_id=session.id,
        node_key="image",
        attempt_id=attempt.attempt_id,
        gate_name="image_review",
        gate_type="human_review",
        contract_version="v1",
        scope=JsonObjectPayload.from_mapping(
            {"scope_type": "episode"},
            field_path="test.gate_scope",
        ),
        artifact_refs=(artifact_ref,),
        facts=JsonObjectPayload.from_mapping(
            {"candidate_count": 1},
            field_path="test.gate_facts",
        ),
        allowed_actions=("approve", "revise"),
        recommended_action="approve",
        expected_lease_token=None,
        result_code=WorkflowGateStatus.AWAITING_HUMAN.value,
        reason_code="review_requested",
        session_input_payload=session_payload,
        node_artifact_refs=(artifact_ref,),
        node_diagnostics=(),
        task_transition=RuntimeTaskTransition(
            task_id="public-task-1",
            expected_status=TaskStatus.IN_PROGRESS,
            target_status=TaskStatus.IN_PROGRESS,
            progress_step="Waiting for review",
            progress_percentage=35,
            requires_human_review=True,
        ),
    )
    db.commit()
    db.refresh(session)
    db.refresh(node)
    db.refresh(task)

    assert isinstance(store, RuntimeGateStore)
    assert gate.status is WorkflowGateStatus.AWAITING_HUMAN
    assert gate.artifact_refs == (artifact_ref,)
    assert session.status == WorkflowSessionStatus.WAITING_GATE.value
    assert session.input_payload == session_payload.to_dict()
    assert node.status == WorkflowNodeStatus.PENDING_GATE.value
    assert node.last_gate_id == gate.gate_id
    assert task.requires_human_review is True


def test_script_gate_approve_applies_decision_checkpoint_and_deliverable_atomically(
    runtime_db,
):
    db, _ = runtime_db
    task, session, node = _seed_runtime(db)
    node.node_key = "script"
    node.node_type = "script"
    node.gate_required = True
    db.commit()
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id, node_key="script"))
    checkpoint = OrchestrationStateAdapter.build_continuation_checkpoint(
        task_specs={
            AgentType.SCRIPT_WRITER: {"run": True, "order": 0},
            AgentType.IMAGE_GENERATOR: {"run": True, "order": 1},
        },
        conditional_task_specs={},
        candidate_agents=[AgentType.SCRIPT_WRITER, AgentType.IMAGE_GENERATOR],
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
        node_key="script",
        attempt_id=attempt.attempt_id,
    )
    RuntimeAttemptControlPlane(store).complete_attempt(
        session_id=session.id,
        node_key="script",
        attempt_id=attempt.attempt_id,
        expected_lease_token=None,
        target_node_status=WorkflowNodeStatus.RUNNING,
        continuation_checkpoint=JsonObjectPayload.from_mapping(
            checkpoint,
            field_path="test.script_checkpoint",
        ),
    )
    deliverable = WorkflowPublishedDeliverable(
        session_id=session.id,
        node_id=node.id,
        attempt_id=attempt.attempt_id,
        deliverable_type="script",
        scope_type="episode",
        scope_id="episode",
        revision_no=0,
        payload_ref="/tmp/script.json",
        summary={"script_preview_text": "draft"},
        is_candidate=True,
        is_approved=False,
    )
    db.add(deliverable)
    db.flush()
    artifact_ref = JsonObjectPayload.from_mapping(
        {
            "type": "published_deliverable",
            "deliverable_id": deliverable.id,
            "attempt_id": attempt.attempt_id,
        },
        field_path="test.script_artifact_ref",
    )
    RuntimeGateControlPlane(store).open_human_gate(
        session_id=session.id,
        node_key="script",
        attempt_id=attempt.attempt_id,
        gate_name="script_review",
        gate_type="human_review",
        contract_version="v1",
        scope=JsonObjectPayload.from_mapping({}, field_path="test.script_gate_scope"),
        artifact_refs=(artifact_ref,),
        facts=JsonObjectPayload.from_mapping({}, field_path="test.script_gate_facts"),
        allowed_actions=("approve", "revise", "replan"),
        recommended_action="approve",
        expected_lease_token=None,
        result_code=WorkflowGateStatus.AWAITING_HUMAN.value,
        reason_code="script_review_requested",
        task_transition=RuntimeTaskTransition(
            task_id="public-task-1",
            expected_status=TaskStatus.IN_PROGRESS,
            target_status=TaskStatus.IN_PROGRESS,
            requires_human_review=True,
        ),
    )

    decision = ScriptGateDecisionControlPlane(store).submit(
        session_id=session.id,
        node_key="script",
        action="approve",
        feedback_text=None,
        structured_constraints=JsonObjectPayload.empty(),
        actor_type="human",
        actor_id="reviewer-1",
        task_id="public-task-1",
        expected_task_status=TaskStatus.IN_PROGRESS,
    )
    db.commit()
    db.refresh(session)
    db.refresh(node)
    db.refresh(task)
    db.refresh(deliverable)
    gate = db.query(WorkflowGate).filter(WorkflowGate.id == node.last_gate_id).one()
    persisted_attempt = db.get(WorkflowNodeAttempt, attempt.attempt_id)

    assert gate.status == WorkflowGateStatus.DECIDED.value
    assert gate.result_code == "approve"
    assert node.status == WorkflowNodeStatus.APPROVED.value
    assert session.status == WorkflowSessionStatus.RESUMING.value
    assert persisted_attempt.continuation_checkpoint["decision_id"] == decision.decision_id
    assert session.input_payload["published_deliverables"]["script"]["is_approved"] is True
    assert deliverable.is_candidate is False
    assert deliverable.is_approved is True
    assert task.requires_human_review is False
    assert task.progress_percentage == 40

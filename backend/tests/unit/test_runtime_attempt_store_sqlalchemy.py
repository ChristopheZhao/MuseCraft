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
    RuntimeNodeDiagnosticsClearCommand,
    RuntimePublishedDeliverableApprovalCommand,
    RuntimePublishedDeliverableStore,
    RuntimePublishedDeliverableWrite,
    RuntimeReadModelQuery,
    RuntimeReadStore,
    RuntimeResumeStore,
    RuntimeSessionBootstrapStore,
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
from app.services.runtime_read_model_service import (
    RuntimeReadModelPresenter,
    RuntimeReadModelService,
)
from app.services.runtime_reconciler import RuntimeReconciler
from app.services.runtime_resume_control_plane import RuntimeResumeControlPlane
from app.services.runtime_session_bootstrap_control_plane import RuntimeSessionBootstrapControlPlane
from app.services.runtime_session_control_plane import RuntimeSessionControlPlane
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
    assert record.task_status is TaskStatus.PENDING
    assert isinstance(store, RuntimeAttemptStore)
    assert isinstance(store, RuntimeReadStore)


def test_session_bootstrap_creates_default_graph_and_rejects_stale_latest_session(runtime_db):
    db, _ = runtime_db
    task = Task(
        task_id="public-bootstrap-task",
        title="Runtime bootstrap test",
        description="runtime bootstrap test",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.PENDING.value,
        input_parameters={"user_prompt": "bootstrap"},
    )
    db.add(task)
    db.flush()
    store = SqlAlchemyRuntimeAttemptStore(db)
    control_plane = RuntimeSessionBootstrapControlPlane(store)

    record = control_plane.create_quick_session(
        task_id="public-bootstrap-task",
        expected_task_status=TaskStatus.PENDING,
        expected_latest_session_id=None,
        input_payload=JsonObjectPayload.from_mapping(
            {"user_prompt": "bootstrap"},
            field_path="test.bootstrap_input",
        ),
    )
    db.commit()
    db.refresh(task)

    assert isinstance(store, RuntimeSessionBootstrapStore)
    assert record.status is WorkflowSessionStatus.QUEUED
    assert record.shared_memory_id == "public-bootstrap-task"
    assert task.output_metadata["workflow_session_id"] == record.session_id
    assert [node.node_key for node in store.load_nodes(record.session_id)] == [
        "concept",
        "script",
        "image",
        "video",
        "voice",
        "compose",
        "audio",
        "quality",
    ]

    with pytest.raises(RuntimeStoreError) as caught:
        control_plane.create_quick_session(
            task_id="public-bootstrap-task",
            expected_task_status=TaskStatus.PENDING,
            expected_latest_session_id=None,
            input_payload=JsonObjectPayload.empty(),
        )

    assert caught.value.reason_code is RuntimeStoreReason.STATE_CONFLICT
    assert caught.value.operation == "create_runtime_session"


def test_attempt_store_rejects_corrupt_persisted_status(runtime_db):
    db, _ = runtime_db
    _, session, _ = _seed_runtime(db)
    session.status = "mystery"
    db.commit()

    with pytest.raises(RuntimeStoreError) as caught:
        SqlAlchemyRuntimeAttemptStore(db).load_session(session.id)

    assert caught.value.reason_code is RuntimeStoreReason.INTEGRITY_ERROR
    assert caught.value.operation == "load_session"


def test_clear_node_diagnostics_rejects_stale_expected_snapshot(runtime_db):
    db, _ = runtime_db
    _, session, node = _seed_runtime(db)
    node.diagnostics = [{"code": "lease_expired"}]
    db.commit()
    store = SqlAlchemyRuntimeAttemptStore(db)
    expected_node = store.load_node(session.id, "image")
    assert expected_node is not None

    node.diagnostics = [
        {"code": "lease_expired"},
        {"code": "concurrent_update"},
    ]
    db.commit()

    with pytest.raises(RuntimeStoreError) as caught:
        store.clear_node_diagnostics(
            RuntimeNodeDiagnosticsClearCommand(
                session_id=session.id,
                node_key="image",
                codes=("lease_expired",),
                expected_status=expected_node.status,
                expected_diagnostics=expected_node.diagnostics,
            )
        )

    assert caught.value.reason_code is RuntimeStoreReason.STATE_CONFLICT
    assert caught.value.operation == "clear_node_diagnostics"
    assert node.diagnostics == [
        {"code": "lease_expired"},
        {"code": "concurrent_update"},
    ]


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
    deliverable_record = store.publish_deliverable(
        RuntimePublishedDeliverableWrite(
            session_id=session.id,
            node_key="script",
            attempt_id=attempt.attempt_id,
            deliverable_type="script",
            scope_type="episode",
            scope_id="episode",
            revision_no=0,
            payload_ref="/tmp/script.json",
            summary=JsonObjectPayload.from_mapping(
                {"script_preview_text": "draft"},
                field_path="test.script_summary",
            ),
            expected_session_status=WorkflowSessionStatus.RUNNING,
            expected_node_status=WorkflowNodeStatus.RUNNING,
            expected_attempt_status=WorkflowAttemptStatus.SUCCEEDED,
        )
    )
    artifact_ref = JsonObjectPayload.from_mapping(
        {
            "type": "published_deliverable",
            "deliverable_id": deliverable_record.deliverable_id,
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
    deliverable = db.get(
        WorkflowPublishedDeliverable,
        deliverable_record.deliverable_id,
    )
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
    assert isinstance(store, RuntimeResumeStore)

    stale_checkpoint = dict(persisted_attempt.continuation_checkpoint)
    stale_checkpoint["decision_id"] = decision.decision_id + 1
    persisted_attempt.continuation_checkpoint = stale_checkpoint
    db.commit()
    resume_control = RuntimeResumeControlPlane(store)

    with pytest.raises(RuntimeStoreError) as caught:
        resume_control.load_continuation(
            session.id,
            expected_anchor_type=(OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION),
            require_decision_id=True,
            require_resuming=True,
            expected_node_key="script",
        )

    assert caught.value.reason_code is RuntimeStoreReason.STATE_CONFLICT
    assert caught.value.operation == "load_runtime_continuation"

    valid_checkpoint = dict(stale_checkpoint)
    valid_checkpoint["decision_id"] = decision.decision_id
    persisted_attempt.continuation_checkpoint = valid_checkpoint
    db.commit()

    resumed = resume_control.consume_script_approval(session.id)
    db.commit()
    db.refresh(session)
    db.refresh(node)
    db.refresh(task)

    assert resumed.status is WorkflowSessionStatus.RUNNING
    assert session.status == WorkflowSessionStatus.RUNNING.value
    assert session.current_node_key is None
    assert session.current_attempt_id is None
    assert node.status == WorkflowNodeStatus.COMPLETED.value
    assert task.status == TaskStatus.IN_PROGRESS.value
    assert task.requires_human_review is False


def test_published_deliverable_store_rejects_stale_runtime_preconditions(runtime_db):
    db, _ = runtime_db
    _, session, node = _seed_runtime(db)
    node.node_key = "script"
    node.node_type = "script"
    db.commit()
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id, node_key="script"))

    assert isinstance(store, RuntimePublishedDeliverableStore)
    with pytest.raises(RuntimeStoreError) as excinfo:
        store.publish_deliverable(
            RuntimePublishedDeliverableWrite(
                session_id=session.id,
                node_key="script",
                attempt_id=attempt.attempt_id,
                deliverable_type="script",
                scope_type="episode",
                scope_id="episode",
                revision_no=0,
                payload_ref="/tmp/script.json",
                summary=JsonObjectPayload.empty(),
                expected_session_status=WorkflowSessionStatus.QUEUED,
                expected_node_status=WorkflowNodeStatus.RUNNING,
                expected_attempt_status=WorkflowAttemptStatus.RUNNING,
            )
        )

    assert excinfo.value.reason_code is RuntimeStoreReason.STATE_CONFLICT
    assert db.query(WorkflowPublishedDeliverable).count() == 0


def test_published_deliverable_store_rejects_stale_approval_state(runtime_db):
    db, _ = runtime_db
    _, session, node = _seed_runtime(db)
    node.node_key = "script"
    node.node_type = "script"
    db.commit()
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id, node_key="script"))
    deliverable = store.publish_deliverable(
        RuntimePublishedDeliverableWrite(
            session_id=session.id,
            node_key="script",
            attempt_id=attempt.attempt_id,
            deliverable_type="script",
            scope_type="episode",
            scope_id="episode",
            revision_no=0,
            payload_ref="/tmp/script.json",
            summary=JsonObjectPayload.empty(),
            expected_session_status=WorkflowSessionStatus.RUNNING,
            expected_node_status=WorkflowNodeStatus.RUNNING,
            expected_attempt_status=WorkflowAttemptStatus.RUNNING,
        )
    )

    with pytest.raises(RuntimeStoreError) as excinfo:
        store.approve_deliverable(
            RuntimePublishedDeliverableApprovalCommand(
                session_id=session.id,
                node_key="script",
                attempt_id=attempt.attempt_id,
                deliverable_id=deliverable.deliverable_id,
                expected_is_candidate=False,
                expected_is_approved=False,
                target_is_candidate=False,
                target_is_approved=True,
            )
        )

    assert excinfo.value.reason_code is RuntimeStoreReason.STATE_CONFLICT
    persisted = db.get(WorkflowPublishedDeliverable, deliverable.deliverable_id)
    assert persisted.is_candidate is True
    assert persisted.is_approved is False


def test_runtime_read_model_is_immutable_and_preserves_public_projection(runtime_db):
    db, _ = runtime_db
    _, session, _ = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    checkpoint = OrchestrationStateAdapter.build_continuation_checkpoint(
        task_specs={AgentType.IMAGE_GENERATOR: {"run": True, "order": 0}},
        conditional_task_specs={},
        candidate_agents=[AgentType.IMAGE_GENERATOR],
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        node_key="image",
        attempt_id=attempt.attempt_id,
    )
    RuntimeAttemptControlPlane(store).bind_continuation(
        session_id=session.id,
        attempt_id=attempt.attempt_id,
        continuation_checkpoint=JsonObjectPayload.from_mapping(
            checkpoint,
            field_path="test.runtime_checkpoint",
        ),
    )
    db.commit()

    query = RuntimeReadModelService(store)
    model = query.load_for_task("public-task-1")

    assert isinstance(query, RuntimeReadModelQuery)
    assert model is not None
    assert model.session.session_id == session.id
    assert model.resume_control is not None
    assert model.resume_control.to_dict() == {
        "state": "resume_available",
        "can_resume": True,
        "reason_code": "checkpoint_available",
    }
    payload = RuntimeReadModelPresenter.to_payload(model).to_dict()
    assert payload["task_id"] == "public-task-1"
    assert "task_db_id" not in payload
    assert payload["nodes"][0]["node_key"] == "image"


def test_session_control_plane_resumes_with_explicit_attempt_and_node_outcomes(runtime_db):
    db, _ = runtime_db
    task, session, node = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    checkpoint = OrchestrationStateAdapter.build_continuation_checkpoint(
        task_specs={AgentType.IMAGE_GENERATOR: {"run": True, "order": 0}},
        conditional_task_specs={},
        candidate_agents=[AgentType.IMAGE_GENERATOR],
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        node_key="image",
        attempt_id=attempt.attempt_id,
    )
    RuntimeAttemptControlPlane(store).bind_continuation(
        session_id=session.id,
        attempt_id=attempt.attempt_id,
        continuation_checkpoint=JsonObjectPayload.from_mapping(
            checkpoint,
            field_path="test.resume_checkpoint",
        ),
    )
    db.commit()

    result = RuntimeSessionControlPlane(store).mark_resuming(session.id)
    db.commit()
    db.refresh(task)
    db.refresh(session)
    db.refresh(node)
    persisted_attempt = db.get(WorkflowNodeAttempt, attempt.attempt_id)

    assert result.status is WorkflowSessionStatus.RESUMING
    assert session.status == WorkflowSessionStatus.RESUMING.value
    assert node.status == WorkflowNodeStatus.STALE.value
    assert persisted_attempt.status == WorkflowAttemptStatus.ABORTED.value
    assert persisted_attempt.lease_token is None
    assert task.status == TaskStatus.IN_PROGRESS.value


def test_session_control_plane_completion_closes_running_attempt_and_nodes(runtime_db):
    db, _ = runtime_db
    task, session, node = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    db.commit()

    result = RuntimeSessionControlPlane(store).mark_completed(
        session.id,
        summary_output=JsonObjectPayload.from_mapping(
            {"final_video_url": "https://example.com/final.mp4"},
            field_path="test.runtime_summary",
        ),
    )
    db.commit()
    db.refresh(task)
    db.refresh(node)
    persisted_attempt = db.get(WorkflowNodeAttempt, attempt.attempt_id)

    assert result.status is WorkflowSessionStatus.COMPLETED
    assert result.summary_output.to_dict()["final_video_url"].endswith("final.mp4")
    assert node.status == WorkflowNodeStatus.COMPLETED.value
    assert persisted_attempt.status == WorkflowAttemptStatus.SUCCEEDED.value
    assert task.status == TaskStatus.COMPLETED.value
    assert task.progress_percentage == 100


def test_session_control_plane_failure_invalidates_live_attempt_lease(runtime_db):
    db, _ = runtime_db
    task, session, node = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    RuntimeAttemptControlPlane(
        store,
        clock=lambda: datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc),
        token_factory=lambda: "runtime-lease-token",
    ).grant_lease(
        session_id=session.id,
        attempt_id=attempt.attempt_id,
        lease_owner="worker-1",
        lease_timeout_seconds=120,
    )
    db.commit()

    RuntimeSessionControlPlane(store).mark_failed(
        session.id,
        error_message="provider failed",
    )
    db.commit()
    db.refresh(task)
    db.refresh(node)
    persisted_attempt = db.get(WorkflowNodeAttempt, attempt.attempt_id)

    assert persisted_attempt.status == WorkflowAttemptStatus.FAILED.value
    assert persisted_attempt.error_code == "runtime_session_failed"
    assert persisted_attempt.lease_token is None
    assert node.status == WorkflowNodeStatus.FAILED.value
    assert task.status == TaskStatus.FAILED.value
    assert task.error_message == "provider failed"


def test_runtime_reconciler_fails_only_missing_checkpoint_candidates(runtime_db):
    db, _ = runtime_db
    task, session, node = _seed_runtime(db)
    store = SqlAlchemyRuntimeAttemptStore(db)
    attempt = store.start_attempt(_start_command(session.id))
    db.commit()

    summary = RuntimeReconciler(store).reconcile_irrecoverable_quick_runtimes(limit=10)
    db.commit()
    db.refresh(task)
    db.refresh(session)
    db.refresh(node)
    persisted_attempt = db.get(WorkflowNodeAttempt, attempt.attempt_id)

    assert summary.to_dict() == {"inspected": 1, "failed": 1, "skipped": 0}
    assert session.status == WorkflowSessionStatus.FAILED.value
    assert node.status == WorkflowNodeStatus.FAILED.value
    assert persisted_attempt.status == WorkflowAttemptStatus.FAILED.value
    assert task.status == TaskStatus.FAILED.value
    assert "continuation checkpoint is missing" in task.error_message

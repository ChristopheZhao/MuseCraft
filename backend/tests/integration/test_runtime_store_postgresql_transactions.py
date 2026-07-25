"""PostgreSQL transaction evidence for MAS runtime persistence contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.domain import (
    AgentType,
    JsonObjectPayload,
    RuntimeAttemptHeartbeatCommand,
    RuntimeAttemptLeaseCommand,
    RuntimeAttemptStartCommand,
    RuntimePublishedDeliverableWrite,
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
from app.infrastructure import SqlAlchemyRuntimeAttemptStore
from app.models import (
    Task,
    WorkflowGate,
    WorkflowGateDecision,
    WorkflowNodeAttempt,
    WorkflowNodeState,
    WorkflowPublishedDeliverable,
    WorkflowSession,
)
from app.services.orchestration_state_adapter import OrchestrationStateAdapter
from app.services.runtime_attempt_control_plane import RuntimeAttemptControlPlane
from app.services.runtime_gate_control_plane import RuntimeGateControlPlane
from app.services.runtime_resume_control_plane import RuntimeResumeControlPlane
from app.services.runtime_session_control_plane import RuntimeSessionControlPlane
from app.services.script_gate_decision_control_plane import (
    ScriptGateDecisionControlPlane,
)


POSTGRES_RUNTIME_TEST_URL = os.environ.get("POSTGRES_RUNTIME_TEST_URL", "").strip()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not POSTGRES_RUNTIME_TEST_URL,
        reason=(
            "POSTGRES_RUNTIME_TEST_URL is required for PostgreSQL runtime " "transaction evidence"
        ),
    ),
]


@dataclass(frozen=True)
class RuntimeSeed:
    task_id: str
    task_db_id: int
    session_id: int
    node_id: int
    node_key: str


@pytest.fixture(scope="module")
def postgres_session_factory():
    url = make_url(POSTGRES_RUNTIME_TEST_URL)
    if url.get_backend_name() != "postgresql":
        pytest.fail("POSTGRES_RUNTIME_TEST_URL must select the PostgreSQL adapter")

    engine = create_engine(url, pool_pre_ping=True)
    required_tables = {
        "tasks",
        "workflow_sessions",
        "workflow_node_states",
        "workflow_node_attempts",
        "workflow_gates",
        "workflow_gate_decisions",
        "workflow_published_deliverables",
    }
    missing_tables = required_tables.difference(inspect(engine).get_table_names())
    if missing_tables:
        pytest.fail(
            "PostgreSQL runtime contract database is not migrated; missing tables: "
            f"{sorted(missing_tables)}"
        )

    factory = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def runtime_seed(postgres_session_factory):
    seed = _seed_runtime(postgres_session_factory)
    try:
        yield seed
    finally:
        with postgres_session_factory() as db:
            task = db.execute(select(Task).where(Task.task_id == seed.task_id)).scalar_one_or_none()
            if task is not None:
                db.delete(task)
                db.commit()


def _seed_runtime(postgres_session_factory, *, node_key: str = "image") -> RuntimeSeed:
    task_id = f"gate-f-{uuid4().hex[:24]}"
    with postgres_session_factory() as db:
        task = Task(
            task_id=task_id,
            title="PostgreSQL runtime contract",
            description="Gate F transaction evidence",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.PENDING.value,
            input_parameters={"user_prompt": "runtime contract"},
        )
        db.add(task)
        db.flush()
        runtime_session = WorkflowSession(
            task_db_id=task.id,
            mode="quick",
            status=WorkflowSessionStatus.QUEUED.value,
            input_payload={"user_prompt": "runtime contract"},
            gate_policy={},
            summary_output={},
        )
        db.add(runtime_session)
        db.flush()
        node = WorkflowNodeState(
            session_id=runtime_session.id,
            node_key=node_key,
            node_type=node_key,
            order_index=10,
            scope_type="episode",
            scope_ref="episode",
            status=WorkflowNodeStatus.QUEUED.value,
            gate_required=node_key == "script",
            artifact_refs=[],
            diagnostics=[],
        )
        db.add(node)
        db.commit()
        return RuntimeSeed(
            task_id=task_id,
            task_db_id=task.id,
            session_id=runtime_session.id,
            node_id=node.id,
            node_key=node_key,
        )


def _start_command(seed: RuntimeSeed) -> RuntimeAttemptStartCommand:
    return RuntimeAttemptStartCommand(
        session_id=seed.session_id,
        node_key=seed.node_key,
        trigger_reason="initial",
        requested_by="orchestrator",
        input_contract=JsonObjectPayload.from_mapping(
            {"scope": "episode"},
            field_path="postgres_runtime_test.input_contract",
        ),
        expected_session_status=WorkflowSessionStatus.QUEUED,
        expected_node_status=WorkflowNodeStatus.QUEUED,
        task_transition=RuntimeTaskTransition(
            task_id=seed.task_id,
            expected_status=TaskStatus.PENDING,
            target_status=TaskStatus.IN_PROGRESS,
            progress_step=f"Generating {seed.node_key}",
            progress_percentage=20,
            requires_human_review=False,
        ),
    )


def _start_attempt(postgres_session_factory, seed: RuntimeSeed) -> int:
    with postgres_session_factory() as db:
        attempt = SqlAlchemyRuntimeAttemptStore(db).start_attempt(_start_command(seed))
        db.commit()
        return attempt.attempt_id


def _grant_lease_concurrently(
    postgres_session_factory,
    *,
    seed: RuntimeSeed,
    attempt_id: int,
    started_at: datetime,
) -> tuple[list[str], list[RuntimeStoreReason]]:
    barrier = Barrier(2)

    def claim(token: str) -> tuple[str | None, RuntimeStoreReason | None]:
        with postgres_session_factory() as db:
            barrier.wait(timeout=10)
            try:
                SqlAlchemyRuntimeAttemptStore(db).grant_attempt_lease(
                    RuntimeAttemptLeaseCommand(
                        session_id=seed.session_id,
                        attempt_id=attempt_id,
                        lease_owner=f"worker:{token}",
                        lease_token=token,
                        heartbeat_at=started_at,
                        lease_expires_at=started_at + timedelta(seconds=60),
                    )
                )
                db.commit()
                return token, None
            except RuntimeStoreError as exc:
                db.rollback()
                return None, exc.reason_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ("lease-a", "lease-b")))
    winners = [token for token, _ in results if token is not None]
    failures = [reason for _, reason in results if reason is not None]
    return winners, failures


def test_postgresql_serializes_concurrent_lease_and_preserves_heartbeat_freshness(
    postgres_session_factory,
    runtime_seed,
):
    attempt_id = _start_attempt(postgres_session_factory, runtime_seed)
    started_at = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)

    winners, failures = _grant_lease_concurrently(
        postgres_session_factory,
        seed=runtime_seed,
        attempt_id=attempt_id,
        started_at=started_at,
    )

    assert len(winners) == 1
    assert failures == [RuntimeStoreReason.LEASE_CONFLICT]
    lease_token = winners[0]

    for heartbeat_at, token in (
        (started_at + timedelta(seconds=10), "wrong-token"),
        (started_at - timedelta(seconds=1), lease_token),
    ):
        with postgres_session_factory() as db:
            with pytest.raises(RuntimeStoreError) as caught:
                SqlAlchemyRuntimeAttemptStore(db).heartbeat_attempt_lease(
                    RuntimeAttemptHeartbeatCommand(
                        session_id=runtime_seed.session_id,
                        attempt_id=attempt_id,
                        lease_token=token,
                        heartbeat_at=heartbeat_at,
                        lease_expires_at=started_at + timedelta(seconds=90),
                    )
                )
            db.rollback()
        assert caught.value.reason_code is RuntimeStoreReason.LEASE_CONFLICT

    renewed_at = started_at + timedelta(seconds=20)
    renewed_until = started_at + timedelta(seconds=120)
    with postgres_session_factory() as db:
        renewed = SqlAlchemyRuntimeAttemptStore(db).heartbeat_attempt_lease(
            RuntimeAttemptHeartbeatCommand(
                session_id=runtime_seed.session_id,
                attempt_id=attempt_id,
                lease_token=lease_token,
                heartbeat_at=renewed_at,
                lease_expires_at=renewed_until,
            )
        )
        db.commit()
        assert renewed.last_heartbeat_at == renewed_at

    with postgres_session_factory() as db:
        persisted = db.get(WorkflowNodeAttempt, attempt_id)
        assert persisted is not None
        assert persisted.lease_token == lease_token
        assert persisted.last_heartbeat_at == renewed_at
        assert persisted.lease_expires_at == renewed_until


def _prepare_script_gate(postgres_session_factory) -> tuple[RuntimeSeed, int, int]:
    seed = _seed_runtime(postgres_session_factory, node_key="script")
    attempt_id = _start_attempt(postgres_session_factory, seed)
    checkpoint = OrchestrationStateAdapter.build_continuation_checkpoint(
        task_specs={
            AgentType.SCRIPT_WRITER: {"run": True, "order": 0},
            AgentType.IMAGE_GENERATOR: {"run": True, "order": 1},
        },
        conditional_task_specs={},
        candidate_agents=[AgentType.SCRIPT_WRITER, AgentType.IMAGE_GENERATOR],
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
        node_key="script",
        attempt_id=attempt_id,
    )

    with postgres_session_factory() as db:
        store = SqlAlchemyRuntimeAttemptStore(db)
        RuntimeAttemptControlPlane(store).complete_attempt(
            session_id=seed.session_id,
            node_key="script",
            attempt_id=attempt_id,
            expected_lease_token=None,
            target_node_status=WorkflowNodeStatus.RUNNING,
            continuation_checkpoint=JsonObjectPayload.from_mapping(
                checkpoint,
                field_path="postgres_runtime_test.script_checkpoint",
            ),
        )
        deliverable = store.publish_deliverable(
            RuntimePublishedDeliverableWrite(
                session_id=seed.session_id,
                node_key="script",
                attempt_id=attempt_id,
                deliverable_type="script",
                scope_type="episode",
                scope_id="episode",
                revision_no=0,
                payload_ref="/tmp/postgres-runtime-script.json",
                summary=JsonObjectPayload.from_mapping(
                    {"script_preview_text": "draft"},
                    field_path="postgres_runtime_test.script_summary",
                ),
                expected_session_status=WorkflowSessionStatus.RUNNING,
                expected_node_status=WorkflowNodeStatus.RUNNING,
                expected_attempt_status=WorkflowAttemptStatus.SUCCEEDED,
            )
        )
        artifact_ref = JsonObjectPayload.from_mapping(
            {
                "type": "published_deliverable",
                "deliverable_id": deliverable.deliverable_id,
                "attempt_id": attempt_id,
            },
            field_path="postgres_runtime_test.script_artifact_ref",
        )
        gate = RuntimeGateControlPlane(store).open_human_gate(
            session_id=seed.session_id,
            node_key="script",
            attempt_id=attempt_id,
            gate_name="script_review",
            gate_type="human_review",
            contract_version="v1",
            scope=JsonObjectPayload.empty(),
            artifact_refs=(artifact_ref,),
            facts=JsonObjectPayload.empty(),
            allowed_actions=("approve", "revise", "replan"),
            recommended_action="approve",
            expected_lease_token=None,
            result_code=WorkflowGateStatus.AWAITING_HUMAN.value,
            reason_code="script_review_requested",
            task_transition=RuntimeTaskTransition(
                task_id=seed.task_id,
                expected_status=TaskStatus.IN_PROGRESS,
                target_status=TaskStatus.IN_PROGRESS,
                requires_human_review=True,
            ),
        )
        db.commit()
        return seed, attempt_id, gate.gate_id


def _submit_script_approval(
    db,
    *,
    seed: RuntimeSeed,
    expected_task_status: TaskStatus,
):
    return ScriptGateDecisionControlPlane(SqlAlchemyRuntimeAttemptStore(db)).submit(
        session_id=seed.session_id,
        node_key="script",
        action="approve",
        feedback_text=None,
        structured_constraints=JsonObjectPayload.empty(),
        actor_type="human",
        actor_id="postgres-runtime-reviewer",
        task_id=seed.task_id,
        expected_task_status=expected_task_status,
    )


def test_postgresql_gate_decision_is_atomic_and_continuation_is_cross_session_visible(
    postgres_session_factory,
):
    seed, attempt_id, gate_id = _prepare_script_gate(postgres_session_factory)
    try:
        with postgres_session_factory() as db:
            with pytest.raises(RuntimeStoreError) as caught:
                _submit_script_approval(
                    db,
                    seed=seed,
                    expected_task_status=TaskStatus.PENDING,
                )
            db.rollback()
        assert caught.value.reason_code is RuntimeStoreReason.STATE_CONFLICT

        with postgres_session_factory() as db:
            assert (
                db.execute(
                    select(WorkflowGateDecision).where(WorkflowGateDecision.gate_id == gate_id)
                )
                .scalars()
                .all()
                == []
            )
            gate = db.get(WorkflowGate, gate_id)
            runtime_session = db.get(WorkflowSession, seed.session_id)
            assert gate is not None
            assert runtime_session is not None
            assert gate.status == WorkflowGateStatus.AWAITING_HUMAN.value
            assert runtime_session.status == WorkflowSessionStatus.WAITING_GATE.value

        with postgres_session_factory() as db:
            decision = _submit_script_approval(
                db,
                seed=seed,
                expected_task_status=TaskStatus.IN_PROGRESS,
            )
            decision_id = decision.decision_id
            db.commit()

        with postgres_session_factory() as db:
            store = SqlAlchemyRuntimeAttemptStore(db)
            checkpoint = RuntimeResumeControlPlane(store).load_continuation(
                seed.session_id,
                expected_anchor_type=(OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION),
                require_decision_id=True,
                require_resuming=True,
                expected_node_key="script",
            )
            assert checkpoint.to_dict()["decision_id"] == decision_id
            assert checkpoint.to_dict()["attempt_id"] == attempt_id
            RuntimeResumeControlPlane(store).consume_script_approval(seed.session_id)
            db.commit()

        with postgres_session_factory() as db:
            with pytest.raises(RuntimeStoreError) as duplicate:
                _submit_script_approval(
                    db,
                    seed=seed,
                    expected_task_status=TaskStatus.IN_PROGRESS,
                )
            db.rollback()
        assert duplicate.value.reason_code is RuntimeStoreReason.STATE_CONFLICT

        with postgres_session_factory() as db:
            decisions = (
                db.execute(
                    select(WorkflowGateDecision).where(WorkflowGateDecision.gate_id == gate_id)
                )
                .scalars()
                .all()
            )
            runtime_session = db.get(WorkflowSession, seed.session_id)
            node = db.get(WorkflowNodeState, seed.node_id)
            deliverable = db.execute(
                select(WorkflowPublishedDeliverable).where(
                    WorkflowPublishedDeliverable.attempt_id == attempt_id
                )
            ).scalar_one()
            assert len(decisions) == 1
            assert runtime_session is not None
            assert node is not None
            assert runtime_session.status == WorkflowSessionStatus.RUNNING.value
            assert node.status == WorkflowNodeStatus.COMPLETED.value
            assert deliverable.is_candidate is False
            assert deliverable.is_approved is True
    finally:
        with postgres_session_factory() as db:
            task = db.execute(select(Task).where(Task.task_id == seed.task_id)).scalar_one_or_none()
            if task is not None:
                db.delete(task)
                db.commit()


@pytest.mark.parametrize("outcome", ("completed", "failed"))
def test_postgresql_session_terminal_transition_is_visible_across_fresh_sessions(
    postgres_session_factory,
    runtime_seed,
    outcome,
):
    attempt_id = _start_attempt(postgres_session_factory, runtime_seed)

    if outcome == "failed":
        with postgres_session_factory() as db:
            RuntimeAttemptControlPlane(
                SqlAlchemyRuntimeAttemptStore(db),
                clock=lambda: datetime(2026, 7, 23, 13, 0, tzinfo=timezone.utc),
                token_factory=lambda: "terminal-transition-lease",
            ).grant_lease(
                session_id=runtime_seed.session_id,
                attempt_id=attempt_id,
                lease_owner="worker:terminal-transition",
                lease_timeout_seconds=120,
            )
            db.commit()

    with postgres_session_factory() as db:
        control_plane = RuntimeSessionControlPlane(SqlAlchemyRuntimeAttemptStore(db))
        if outcome == "completed":
            control_plane.mark_completed(
                runtime_seed.session_id,
                summary_output=JsonObjectPayload.from_mapping(
                    {"final_video_url": "https://example.com/final.mp4"},
                    field_path="postgres_runtime_test.summary_output",
                ),
            )
        else:
            control_plane.mark_failed(
                runtime_seed.session_id,
                error_message="provider failed",
            )
        db.commit()

    with postgres_session_factory() as db:
        task = db.get(Task, runtime_seed.task_db_id)
        runtime_session = db.get(WorkflowSession, runtime_seed.session_id)
        node = db.get(WorkflowNodeState, runtime_seed.node_id)
        attempt = db.get(WorkflowNodeAttempt, attempt_id)
        assert task is not None
        assert runtime_session is not None
        assert node is not None
        assert attempt is not None
        assert attempt.lease_token is None
        if outcome == "completed":
            assert task.status == TaskStatus.COMPLETED.value
            assert runtime_session.status == WorkflowSessionStatus.COMPLETED.value
            assert node.status == WorkflowNodeStatus.COMPLETED.value
            assert attempt.status == WorkflowAttemptStatus.SUCCEEDED.value
            assert runtime_session.summary_output["final_video_url"].endswith("final.mp4")
        else:
            assert task.status == TaskStatus.FAILED.value
            assert runtime_session.status == WorkflowSessionStatus.FAILED.value
            assert node.status == WorkflowNodeStatus.FAILED.value
            assert attempt.status == WorkflowAttemptStatus.FAILED.value
            assert attempt.error_code == "runtime_session_failed"

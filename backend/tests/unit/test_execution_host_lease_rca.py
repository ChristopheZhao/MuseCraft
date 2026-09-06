import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.domain import (
    JsonObjectPayload,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    TaskStatus,
    TaskType,
)
from app.infrastructure import SqlAlchemyRuntimeAttemptStore
from app.models import Task
from app.services import execution_host_lease
from app.services.runtime_attempt_control_plane import RuntimeAttemptControlPlane
from app.services.runtime_attempt_keepalive_adapter import (
    create_runtime_attempt_keepalive_controller,
)
from app.services.runtime_session_bootstrap_control_plane import RuntimeSessionBootstrapControlPlane


def _build_threaded_sqlite_session_factory(tmp_path, name: str):
    engine = create_engine(
        f"sqlite:///{(tmp_path / name).as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _create_runtime_attempt(
    session_factory, *, node_key: str = "video", lease_timeout_seconds: int = 2
):
    db = session_factory()
    try:
        task = Task(
            title="Execution Host Lease RCA",
            description="lease rca",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.PENDING.value,
            input_parameters={"user_prompt": "test prompt"},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        store = SqlAlchemyRuntimeAttemptStore(db)
        runtime_session = RuntimeSessionBootstrapControlPlane(store).create_quick_session(
            task_id=str(task.task_id),
            expected_task_status=TaskStatus(str(task.status)),
            expected_latest_session_id=None,
            input_payload=JsonObjectPayload.from_mapping(
                task.input_parameters or {},
                field_path="test.runtime_input_payload",
            ),
        )
        db.commit()
        runtime_session = store.load_session(runtime_session.session_id)
        assert runtime_session is not None
        control_plane = RuntimeAttemptControlPlane(store)
        attempt = control_plane.start_attempt(
            session_id=runtime_session.session_id,
            node_key=node_key,
            trigger_reason="initial",
            requested_by="test",
            input_contract=JsonObjectPayload.empty(),
            task_transition=RuntimeTaskTransition(
                task_id=runtime_session.task_id,
                expected_status=runtime_session.task_status,
                target_status=TaskStatus.IN_PROGRESS,
                requires_human_review=False,
            ),
        )
        leased_attempt = control_plane.grant_lease(
            session_id=runtime_session.session_id,
            attempt_id=attempt.attempt_id,
            lease_owner=f"orchestrator:{node_key}",
            lease_token=f"lease-token-{attempt.attempt_id}",
            lease_timeout_seconds=lease_timeout_seconds,
        )
        db.commit()
        return {
            "task_id": str(task.task_id),
            "runtime_session_id": runtime_session.session_id,
            "attempt_id": attempt.attempt_id,
            "lease_token": str(leased_attempt.lease_token),
            "last_heartbeat_at": leased_attempt.last_heartbeat_at,
            "lease_expires_at": leased_attempt.lease_expires_at,
            "node_key": node_key,
        }
    finally:
        db.close()


def _wait_until(predicate, *, timeout: float = 2.0, interval: float = 0.02, message: str) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval)
    pytest.fail(message)


def test_attempt_lease_keepalive_controller_renews_real_runtime_lease_on_threaded_sqlite(tmp_path):
    engine, session_factory = _build_threaded_sqlite_session_factory(
        tmp_path,
        "lease_rca_renew.sqlite",
    )
    setup = _create_runtime_attempt(session_factory, lease_timeout_seconds=2)

    def _heartbeat_attempt(db, runtime_session, *, attempt_id, lease_token):
        attempt = RuntimeAttemptControlPlane(SqlAlchemyRuntimeAttemptStore(db)).heartbeat_lease(
            session_id=runtime_session.session_id,
            attempt_id=attempt_id,
            lease_token=lease_token,
            lease_timeout_seconds=2,
        )
        db.commit()
        return attempt

    def _load_session(db, runtime_session_id):
        return SqlAlchemyRuntimeAttemptStore(db).load_session(runtime_session_id)

    controller = execution_host_lease.AttemptLeaseKeepaliveController(
        session_factory=session_factory,
        load_session=_load_session,
        heartbeat_attempt=_heartbeat_attempt,
        interval_seconds=0.05,
    )

    try:
        controller.activate(
            runtime_session_id=setup["runtime_session_id"],
            attempt_id=setup["attempt_id"],
            lease_token=setup["lease_token"],
        )

        def _lease_advanced() -> bool:
            db = session_factory()
            try:
                attempt = SqlAlchemyRuntimeAttemptStore(db).load_attempt(
                    setup["runtime_session_id"],
                    setup["attempt_id"],
                )
                return bool(
                    attempt is not None
                    and attempt.last_heartbeat_at is not None
                    and attempt.lease_expires_at is not None
                    and attempt.last_heartbeat_at > setup["last_heartbeat_at"]
                    and attempt.lease_expires_at > setup["lease_expires_at"]
                )
            finally:
                db.close()

        _wait_until(
            _lease_advanced,
            timeout=2.0,
            interval=0.02,
            message="expected keepalive controller to renew attempt lease on the real runtime path",
        )
    finally:
        controller.close()
        engine.dispose()


def test_keepalive_adapter_persists_receipts_through_runtime_store(tmp_path):
    engine, session_factory = _build_threaded_sqlite_session_factory(
        tmp_path,
        "lease_adapter_receipts.sqlite",
    )
    setup = _create_runtime_attempt(session_factory, lease_timeout_seconds=2)
    controller = create_runtime_attempt_keepalive_controller(
        session_factory=session_factory,
        interval_seconds=10,
    )

    try:
        controller.activate(
            runtime_session_id=setup["runtime_session_id"],
            attempt_id=setup["attempt_id"],
            lease_token=setup["lease_token"],
        )
        controller.deactivate(reason="test_complete")

        db = session_factory()
        try:
            node = SqlAlchemyRuntimeAttemptStore(db).load_node(
                setup["runtime_session_id"],
                setup["node_key"],
            )
            assert node is not None
            codes = {diagnostic.to_dict().get("code") for diagnostic in node.diagnostics}
            assert "execution_host_keepalive_activation_requested" in codes
            assert "execution_host_keepalive_deactivated" in codes
        finally:
            db.close()
    finally:
        controller.close()
        engine.dispose()


def test_attempt_lease_keepalive_controller_can_leave_silent_expired_window_when_heartbeat_blocks(
    tmp_path,
):
    engine, session_factory = _build_threaded_sqlite_session_factory(
        tmp_path,
        "lease_rca_blocked.sqlite",
    )
    setup = _create_runtime_attempt(session_factory, lease_timeout_seconds=2)
    entered_heartbeat = threading.Event()
    release_heartbeat = threading.Event()
    published = []

    def _publish_keepalive_diagnostic(*, runtime_session_id: int, attempt_id: int, diagnostic):
        published.append(
            {
                "runtime_session_id": runtime_session_id,
                "attempt_id": attempt_id,
                "diagnostic": dict(diagnostic),
            }
        )
        diagnostic_db = session_factory()
        try:
            SqlAlchemyRuntimeAttemptStore(diagnostic_db).upsert_node_diagnostic(
                session_id=runtime_session_id,
                attempt_id=attempt_id,
                diagnostic=JsonObjectPayload.from_mapping(
                    diagnostic,
                    field_path="test.keepalive_diagnostic",
                ),
            )
            diagnostic_db.commit()
        finally:
            diagnostic_db.close()

    def _blocked_heartbeat(db, runtime_session, *, attempt_id, lease_token):
        entered_heartbeat.set()
        if not release_heartbeat.wait(timeout=5.0):
            raise RuntimeError("test heartbeat release timeout")
        attempt = RuntimeAttemptControlPlane(SqlAlchemyRuntimeAttemptStore(db)).heartbeat_lease(
            session_id=runtime_session.session_id,
            attempt_id=attempt_id,
            lease_token=lease_token,
            lease_timeout_seconds=2,
        )
        db.commit()
        return attempt

    def _load_session(db, runtime_session_id):
        return SqlAlchemyRuntimeAttemptStore(db).load_session(runtime_session_id)

    controller = execution_host_lease.AttemptLeaseKeepaliveController(
        session_factory=session_factory,
        load_session=_load_session,
        heartbeat_attempt=_blocked_heartbeat,
        interval_seconds=0.05,
        publish_diagnostic=_publish_keepalive_diagnostic,
    )

    try:
        controller.activate(
            runtime_session_id=setup["runtime_session_id"],
            attempt_id=setup["attempt_id"],
            lease_token=setup["lease_token"],
        )
        assert entered_heartbeat.wait(
            timeout=1.0
        ), "expected keepalive loop to enter heartbeat call"

        sleep_seconds = max(
            0.0,
            (setup["lease_expires_at"] - setup["last_heartbeat_at"]).total_seconds() + 0.2,
        )
        time.sleep(sleep_seconds)

        mid_db = session_factory()
        try:
            store = SqlAlchemyRuntimeAttemptStore(mid_db)
            node = store.load_node(
                setup["runtime_session_id"],
                setup["node_key"],
            )
            assert node is not None
            with pytest.raises(RuntimeStoreError) as excinfo:
                RuntimeAttemptControlPlane(store).heartbeat_lease(
                    session_id=setup["runtime_session_id"],
                    attempt_id=setup["attempt_id"],
                    lease_token=setup["lease_token"],
                    lease_timeout_seconds=2,
                )
            assert excinfo.value.reason_code is RuntimeStoreReason.LEASE_CONFLICT
            keepalive_stop_diagnostics = [
                item.to_dict()
                for item in node.diagnostics
                if item.to_dict().get("code") == "execution_host_keepalive"
            ]
            assert keepalive_stop_diagnostics == []
        finally:
            mid_db.close()

        controller.assert_healthy()
        assert [
            item
            for item in published
            if item["diagnostic"].get("code") == "execution_host_keepalive"
        ] == []

        release_heartbeat.set()

        def _published_stop_diagnostic() -> bool:
            return bool(published)

        _wait_until(
            _published_stop_diagnostic,
            timeout=2.0,
            interval=0.02,
            message="expected blocked heartbeat to surface a keepalive stop diagnostic after it returns",
        )

        def _controller_is_unhealthy() -> bool:
            try:
                controller.assert_healthy()
            except execution_host_lease.ExecutionHostKeepaliveLostError:
                return True
            return False

        _wait_until(
            _controller_is_unhealthy,
            timeout=2.0,
            interval=0.02,
            message="expected blocked heartbeat to mark the keepalive controller unhealthy after validation stops",
        )

        with pytest.raises(execution_host_lease.ExecutionHostKeepaliveLostError) as excinfo:
            controller.assert_healthy()

        end_db = session_factory()
        try:
            node = SqlAlchemyRuntimeAttemptStore(end_db).load_node(
                setup["runtime_session_id"],
                setup["node_key"],
            )
            assert node is not None
            keepalive_diagnostics = [
                item.to_dict()
                for item in node.diagnostics
                if item.to_dict().get("code") == "execution_host_keepalive"
            ]
        finally:
            end_db.close()

        published_stop_diagnostics = [
            item["diagnostic"]
            for item in published
            if item["diagnostic"].get("code") == "execution_host_keepalive"
        ]
        assert published_stop_diagnostics[0]["reason_code"] == "lease_conflict"
        assert excinfo.value.diagnostic["reason_code"] == "lease_conflict"
        assert len(keepalive_diagnostics) == 1
        assert keepalive_diagnostics[0]["state"] == "stopped"
    finally:
        release_heartbeat.set()
        controller.close()
        engine.dispose()

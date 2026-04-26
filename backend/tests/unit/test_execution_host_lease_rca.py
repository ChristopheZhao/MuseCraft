import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import Task, TaskStatus, TaskType
from app.services import execution_host_lease
from app.services.runtime_session_service import RuntimeSessionService


def _build_threaded_sqlite_session_factory(tmp_path, name: str):
    engine = create_engine(
        f"sqlite:///{(tmp_path / name).as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _create_runtime_attempt(session_factory, *, node_key: str = "video", lease_timeout_seconds: int = 2):
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

        runtime_session = RuntimeSessionService.get_or_create_session_for_task_sync(db, task, mode="quick")
        attempt = RuntimeSessionService.start_node_attempt_sync(
            db,
            runtime_session,
            node_key=node_key,
            task=task,
        )
        leased_attempt = RuntimeSessionService.grant_attempt_lease_sync(
            db,
            runtime_session,
            attempt_id=attempt.id,
            lease_owner=f"orchestrator:{node_key}",
            lease_token=f"lease-token-{attempt.id}",
            lease_timeout_seconds=lease_timeout_seconds,
        )
        return {
            "task_id": task.id,
            "runtime_session_id": runtime_session.id,
            "attempt_id": attempt.id,
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
        return RuntimeSessionService.heartbeat_attempt_lease_sync(
            db,
            runtime_session,
            attempt_id=attempt_id,
            lease_token=lease_token,
            lease_timeout_seconds=2,
        )

    controller = execution_host_lease.AttemptLeaseKeepaliveController(
        session_factory=session_factory,
        load_session=RuntimeSessionService.get_session_by_id_sync,
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
                attempt = RuntimeSessionService.get_attempt_by_id_sync(
                    db,
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


def test_attempt_lease_keepalive_controller_can_leave_silent_expired_window_when_heartbeat_blocks(tmp_path):
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
            runtime_session = RuntimeSessionService.get_session_by_id_sync(
                diagnostic_db,
                runtime_session_id,
            )
            RuntimeSessionService.upsert_attempt_node_diagnostic_sync(
                diagnostic_db,
                runtime_session,
                attempt_id=attempt_id,
                diagnostic=diagnostic,
            )
        finally:
            diagnostic_db.close()

    def _blocked_heartbeat(db, runtime_session, *, attempt_id, lease_token):
        entered_heartbeat.set()
        if not release_heartbeat.wait(timeout=5.0):
            raise RuntimeError("test heartbeat release timeout")
        return RuntimeSessionService.heartbeat_attempt_lease_sync(
            db,
            runtime_session,
            attempt_id=attempt_id,
            lease_token=lease_token,
            lease_timeout_seconds=2,
        )

    controller = execution_host_lease.AttemptLeaseKeepaliveController(
        session_factory=session_factory,
        load_session=RuntimeSessionService.get_session_by_id_sync,
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
        assert entered_heartbeat.wait(timeout=1.0), "expected keepalive loop to enter heartbeat call"

        sleep_seconds = max(
            0.0,
            (setup["lease_expires_at"] - setup["last_heartbeat_at"]).total_seconds() + 0.2,
        )
        time.sleep(sleep_seconds)

        mid_db = session_factory()
        try:
            runtime_session = RuntimeSessionService.get_session_by_id_sync(
                mid_db,
                setup["runtime_session_id"],
            )
            node = RuntimeSessionService.get_node_by_key_sync(
                mid_db,
                setup["runtime_session_id"],
                setup["node_key"],
            )
            with pytest.raises(ValueError, match="execution lease expired"):
                RuntimeSessionService.assert_attempt_lease_sync(
                    mid_db,
                    runtime_session,
                    attempt_id=setup["attempt_id"],
                    lease_token=setup["lease_token"],
                )
            keepalive_stop_diagnostics = [
                item
                for item in (getattr(node, "diagnostics", None) or [])
                if isinstance(item, dict) and item.get("code") == "execution_host_keepalive"
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
            node = RuntimeSessionService.get_node_by_key_sync(
                end_db,
                setup["runtime_session_id"],
                setup["node_key"],
            )
            keepalive_diagnostics = [
                item
                for item in (node.diagnostics or [])
                if isinstance(item, dict) and item.get("code") == "execution_host_keepalive"
            ]
        finally:
            end_db.close()

        published_stop_diagnostics = [
            item["diagnostic"]
            for item in published
            if item["diagnostic"].get("code") == "execution_host_keepalive"
        ]
        assert published_stop_diagnostics[0]["reason_code"] == "heartbeat_validation_failed"
        assert excinfo.value.diagnostic["reason_code"] == "heartbeat_validation_failed"
        assert len(keepalive_diagnostics) == 1
        assert keepalive_diagnostics[0]["state"] == "stopped"
    finally:
        release_heartbeat.set()
        controller.close()
        engine.dispose()

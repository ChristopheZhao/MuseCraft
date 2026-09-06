"""Persistence adapter for execution-host attempt keepalive reporting."""

from __future__ import annotations

import logging
from typing import Any

from ..core.config import settings
from ..domain import JsonObjectPayload
from ..infrastructure import SqlAlchemyRuntimeAttemptStore
from .execution_host_lease import (
    AttemptLeaseKeepaliveController,
    execution_host_lease_heartbeat_interval_seconds,
)
from .runtime_attempt_control_plane import RuntimeAttemptControlPlane


def create_runtime_attempt_keepalive_controller(
    *,
    session_factory=None,
    interval_seconds: float | None = None,
    logger: logging.Logger | None = None,
) -> AttemptLeaseKeepaliveController:
    """Compose host liveness callbacks at the application/persistence boundary."""

    if session_factory is None:
        from ..core.database import SessionLocal

        session_factory = SessionLocal

    logger = logger or logging.getLogger("runtime_attempt_keepalive")

    def load_runtime_session(db, runtime_session_id: int):
        return SqlAlchemyRuntimeAttemptStore(db).load_session(runtime_session_id)

    def heartbeat_attempt(
        db,
        runtime_session,
        *,
        attempt_id: int,
        lease_token: str,
    ):
        store = SqlAlchemyRuntimeAttemptStore(db)
        control_plane = RuntimeAttemptControlPlane(store)
        attempt = control_plane.heartbeat_lease(
            session_id=runtime_session.session_id,
            attempt_id=attempt_id,
            lease_token=lease_token,
            lease_timeout_seconds=max(
                1,
                int(getattr(settings, "RUNTIME_ATTEMPT_LEASE_SECONDS", 300)),
            ),
        )
        db.commit()
        return attempt

    def publish_diagnostic(
        *, runtime_session_id: int, attempt_id: int, diagnostic: dict[str, Any]
    ) -> None:
        db = session_factory()
        try:
            SqlAlchemyRuntimeAttemptStore(db).upsert_node_diagnostic(
                session_id=runtime_session_id,
                attempt_id=attempt_id,
                diagnostic=JsonObjectPayload.from_mapping(
                    diagnostic,
                    field_path="execution_host_keepalive.diagnostic",
                ),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return AttemptLeaseKeepaliveController(
        session_factory=session_factory,
        load_session=load_runtime_session,
        heartbeat_attempt=heartbeat_attempt,
        interval_seconds=(
            interval_seconds
            if interval_seconds is not None
            else execution_host_lease_heartbeat_interval_seconds()
        ),
        publish_diagnostic=publish_diagnostic,
        logger=logger,
    )

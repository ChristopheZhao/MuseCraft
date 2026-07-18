from dataclasses import FrozenInstanceError

import pytest

from app.domain import (
    JsonObjectPayload,
    RuntimeAttemptHeartbeatCommand,
    RuntimeReadModel,
    RuntimeReadModelQuery,
    RuntimeSessionRecord,
    RuntimeStoreError,
    RuntimeStoreReason,
    WorkflowSessionStatus,
)


def test_runtime_session_record_uses_stable_task_id_and_strict_json_payloads():
    record = RuntimeSessionRecord(
        session_id=7,
        task_id="task-public-7",
        mode="quick",
        status=WorkflowSessionStatus.RUNNING,
        input_payload=JsonObjectPayload.from_mapping(
            {"user_prompt": "test"},
            field_path="runtime.input_payload",
        ),
    )

    assert record.task_id == "task-public-7"
    assert record.input_payload.to_dict() == {"user_prompt": "test"}
    with pytest.raises(FrozenInstanceError):
        record.status = WorkflowSessionStatus.COMPLETED


def test_runtime_session_record_rejects_database_identity_and_raw_status_strings():
    with pytest.raises(ValueError, match="task_id"):
        RuntimeSessionRecord(
            session_id=1,
            task_id="",
            mode="quick",
            status=WorkflowSessionStatus.QUEUED,
        )

    with pytest.raises(ValueError, match="WorkflowSessionStatus"):
        RuntimeSessionRecord(
            session_id=1,
            task_id="task-1",
            mode="quick",
            status="queued",
        )


def test_runtime_store_error_is_typed_and_does_not_prescribe_control_action():
    error = RuntimeStoreError(
        reason_code=RuntimeStoreReason.LEASE_CONFLICT,
        operation="heartbeat_attempt_lease",
        message="lease token mismatch",
    )

    assert error.reason_code == RuntimeStoreReason.LEASE_CONFLICT
    assert error.operation == "heartbeat_attempt_lease"
    assert "retry" not in str(error).lower()
    assert "resume" not in str(error).lower()


def test_runtime_heartbeat_command_requires_explicit_caller_facts():
    fields = set(RuntimeAttemptHeartbeatCommand.__dataclass_fields__)
    assert fields == {
        "session_id",
        "attempt_id",
        "lease_token",
        "heartbeat_at",
        "lease_expires_at",
    }


def test_runtime_read_model_is_explicit_not_an_orm_mapping():
    fields = set(RuntimeReadModel.__dataclass_fields__)
    assert fields == {
        "session",
        "nodes",
        "active_gate",
        "latest_decision",
        "resume_control",
    }
    assert RuntimeReadModelQuery.__name__ == "RuntimeReadModelQuery"

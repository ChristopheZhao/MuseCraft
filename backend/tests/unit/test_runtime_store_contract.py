from dataclasses import FrozenInstanceError

import pytest

from app.domain import (
    JsonObjectPayload,
    RuntimeAttemptCompletionCommand,
    RuntimeAttemptFailureCommand,
    RuntimeAttemptHeartbeatCommand,
    RuntimeGateDecisionApplyCommand,
    RuntimeGateOpenCommand,
    RuntimeNodeCreate,
    RuntimeReadModel,
    RuntimeReadModelQuery,
    RuntimeSessionRecord,
    RuntimeStoreError,
    RuntimeStoreReason,
    TaskStatus,
    WorkflowSessionStatus,
)


def test_runtime_session_record_uses_stable_task_id_and_strict_json_payloads():
    record = RuntimeSessionRecord(
        session_id=7,
        task_id="task-public-7",
        task_status=TaskStatus.IN_PROGRESS,
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
            task_status=TaskStatus.PENDING,
            mode="quick",
            status=WorkflowSessionStatus.QUEUED,
        )

    with pytest.raises(ValueError, match="WorkflowSessionStatus"):
        RuntimeSessionRecord(
            session_id=1,
            task_id="task-1",
            task_status=TaskStatus.PENDING,
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
        "expected_attempt_status",
    }


def test_runtime_session_blueprint_contains_no_persistence_identity():
    fields = set(RuntimeNodeCreate.__dataclass_fields__)
    assert fields == {
        "node_key",
        "node_type",
        "order_index",
        "scope_type",
        "target_status",
        "scope_ref",
        "revision_index",
        "gate_required",
    }
    assert "node_id" not in fields
    assert "session_id" not in fields


@pytest.mark.parametrize(
    ("command_type", "required_target_facts"),
    [
        (
            RuntimeAttemptCompletionCommand,
            {
                "observed_at",
                "expected_attempt_status",
                "target_attempt_status",
                "target_node_status",
                "target_session_status",
            },
        ),
        (
            RuntimeAttemptFailureCommand,
            {
                "observed_at",
                "expected_attempt_status",
                "target_attempt_status",
                "target_node_status",
                "target_session_status",
            },
        ),
        (
            RuntimeGateOpenCommand,
            {
                "observed_at",
                "target_gate_status",
                "target_node_status",
                "target_session_status",
                "result_code",
            },
        ),
        (
            RuntimeGateDecisionApplyCommand,
            {
                "expected_gate_status",
                "target_gate_status",
                "target_node_status",
                "target_node_revision_index",
                "target_session_status",
                "session_input_payload",
            },
        ),
    ],
)
def test_atomic_commands_carry_control_plane_selected_target_facts(
    command_type, required_target_facts
):
    assert required_target_facts <= set(command_type.__dataclass_fields__)


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

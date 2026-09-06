"""Database-independent policy for creating authoritative runtime sessions."""

from __future__ import annotations

from ..domain import (
    JsonObjectPayload,
    RuntimeNodeCreate,
    RuntimeSessionBootstrapStore,
    RuntimeSessionCreateCommand,
    RuntimeSessionRecord,
    TaskStatus,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)

DEFAULT_RUNTIME_NODES = (
    RuntimeNodeCreate("concept", "concept", 10, "episode", WorkflowNodeStatus.QUEUED, "episode"),
    RuntimeNodeCreate(
        "script",
        "script",
        20,
        "episode",
        WorkflowNodeStatus.QUEUED,
        "episode",
        gate_required=True,
    ),
    RuntimeNodeCreate("image", "image", 30, "episode", WorkflowNodeStatus.QUEUED, "episode"),
    RuntimeNodeCreate("video", "video", 40, "episode", WorkflowNodeStatus.QUEUED, "episode"),
    RuntimeNodeCreate("voice", "voice", 50, "episode", WorkflowNodeStatus.QUEUED, "episode"),
    RuntimeNodeCreate("compose", "compose", 60, "episode", WorkflowNodeStatus.QUEUED, "episode"),
    RuntimeNodeCreate("audio", "audio", 70, "episode", WorkflowNodeStatus.QUEUED, "episode"),
    RuntimeNodeCreate("quality", "quality", 80, "episode", WorkflowNodeStatus.QUEUED, "episode"),
)


class RuntimeSessionBootstrapControlPlane:
    """Builds the initial runtime graph and delegates one atomic create command."""

    def __init__(self, store: RuntimeSessionBootstrapStore) -> None:
        self._store = store

    def create_quick_session(
        self,
        *,
        task_id: str,
        expected_task_status: TaskStatus,
        expected_latest_session_id: int | None,
        input_payload: JsonObjectPayload,
        project_id: str | None = None,
        episode_id: str | None = None,
    ) -> RuntimeSessionRecord:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            raise ValueError("runtime session task_id is required")
        return self._store.create_session(
            RuntimeSessionCreateCommand(
                task_id=normalized_task_id,
                expected_task_status=expected_task_status,
                expected_latest_session_id=expected_latest_session_id,
                mode="quick",
                input_payload=input_payload,
                target_status=WorkflowSessionStatus.QUEUED,
                nodes=DEFAULT_RUNTIME_NODES,
                project_id=project_id,
                episode_id=episode_id,
                shared_memory_id=normalized_task_id,
                gate_policy=JsonObjectPayload.empty(),
            )
        )

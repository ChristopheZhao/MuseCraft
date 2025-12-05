from typing import Any, Dict, Optional

from .models import Event, EventKind
from .provider import get_event_bus


async def publish_event(
    *,
    kind: EventKind,
    payload: Dict[str, Any],
    task_id: Optional[str] = None,
    workflow_state_id: Optional[str] = None,
    agent_type: Optional[str] = None,
    agent_name: Optional[str] = None,
    iteration: Optional[int] = None,
    scene_number: Optional[int] = None,
    execution_order: Optional[int] = None,
    task_db_id: Optional[int] = None,
    execution_id: Optional[str] = None,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> None:
    merged_payload = dict(payload or {})
    if task_db_id is not None:
        merged_payload["task_db_id"] = task_db_id
    if execution_order is not None:
        merged_payload["execution_order"] = execution_order
    if execution_id:
        merged_payload.setdefault("execution_id", execution_id)
    if extra_payload:
        merged_payload.update(extra_payload)

    event = Event(
        event_kind=kind,
        payload=merged_payload,
        task_id=task_id,
        workflow_state_id=workflow_state_id,
        agent_type=agent_type,
        agent_name=agent_name,
        iteration=iteration,
        scene_number=scene_number,
        sequence=execution_order,
    )
    await get_event_bus().publish(event)


async def publish_state_event(
    *,
    status: str,
    error: Optional[str] = None,
    task_id: Optional[str] = None,
    task_db_id: Optional[int] = None,
    workflow_state_id: Optional[str] = None,
    agent_type: Optional[str] = None,
    agent_name: Optional[str] = None,
    execution_order: Optional[int] = None,
    execution_id: Optional[str] = None,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> None:
    await publish_event(
        kind=EventKind.STATE,
        payload={"status": status, "error": error},
        task_id=task_id,
        task_db_id=task_db_id,
        workflow_state_id=workflow_state_id,
        agent_type=agent_type,
        agent_name=agent_name,
        execution_order=execution_order,
        execution_id=execution_id,
        extra_payload=extra_payload,
    )


async def publish_error_event(
    *,
    error_message: str,
    error_type: Optional[str] = None,
    task_id: Optional[str] = None,
    task_db_id: Optional[int] = None,
    workflow_state_id: Optional[str] = None,
    agent_type: Optional[str] = None,
    agent_name: Optional[str] = None,
    execution_order: Optional[int] = None,
    execution_id: Optional[str] = None,
) -> None:
    await publish_event(
        kind=EventKind.ERROR,
        payload={
            "error_message": error_message,
            "error_type": error_type,
        },
        task_id=task_id,
        task_db_id=task_db_id,
        workflow_state_id=workflow_state_id,
        agent_type=agent_type,
        agent_name=agent_name,
        execution_order=execution_order,
        execution_id=execution_id,
        extra_payload={"error_type": error_type, "execution_order": execution_order},
    )

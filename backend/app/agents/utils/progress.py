import logging
from typing import Any, Optional

from ...events import EventKind
from ...events.publisher import publish_event


async def send_progress_event(
    agent: Any,
    status: str,
    progress: Optional[int] = None,
    substep: Optional[str] = None,
) -> None:
    """
    统一发布进度事件的辅助函数，避免在各 Agent 内重复组装上下文。
    依赖 Agent 上的上下文字段：_current_execution、_current_task、_task_db_id、
    workflow_state_id、agent_type、agent_name、_current_execution_order。
    """
    logger = getattr(agent, "logger", logging.getLogger(__name__))
    try:
        execution = getattr(agent, "_current_execution", {}) or {}
        task = getattr(agent, "_current_task", None)
        task_id = str(task.task_id) if task and getattr(task, "task_id", None) else None
        payload = {
            "status": status,
            "progress": progress if progress is not None else execution.get("progress_percentage"),
            "current_step": substep if substep is not None else execution.get("current_substep"),
        }
        await publish_event(
            kind=EventKind.PROGRESS,
            payload=payload,
            task_id=task_id,
            task_db_id=getattr(agent, "_task_db_id", None),
            workflow_state_id=getattr(agent, "workflow_state_id", None),
            agent_type=getattr(getattr(agent, "agent_type", None), "value", None),
            agent_name=getattr(agent, "agent_name", None),
            execution_order=getattr(agent, "_current_execution_order", None),
        )
    except Exception as exc:
        logger.warning("Failed to publish progress event: %s", exc)


async def update_progress(
    agent: Any,
    percentage: int,
    substep: Optional[str] = None,
) -> None:
    """
    更新当前执行的进度摘要并发布事件。
    """
    execution = getattr(agent, "_current_execution", {}) or {}
    try:
        execution["progress_percentage"] = min(100, max(0, int(percentage)))
    except Exception:
        execution["progress_percentage"] = percentage
    if substep:
        execution["current_substep"] = substep
    await send_progress_event(
        agent,
        status="progress",
        progress=execution.get("progress_percentage"),
        substep=execution.get("current_substep"),
    )

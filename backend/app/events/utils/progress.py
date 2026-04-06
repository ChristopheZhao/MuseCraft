import logging
from typing import Any, Optional, Union

from ..models import EventKind
from ..publisher import publish_event
from ..execution import ExecutionState


async def send_progress_event(
    exec_state: ExecutionState,
    agent_context: Any, # Pass agent instance or a context object with necessary IDs
    status: str,
    progress: Optional[int] = None,
    substep: Optional[str] = None,
) -> None:
    """
    统一发布进度事件的辅助函数。
    
    Args:
        exec_state: 当前的执行状态对象 (ExecutionState)
        agent_context: Agent实例或包含 task_id/workflow_id 等信息的对象
        status: 状态描述
    """
    logger = getattr(agent_context, "logger", logging.getLogger(__name__))
    try:
        # 优先使用传入的 progress/substep，否则从 exec_state 读取
        final_progress = progress if progress is not None else exec_state.progress
        final_substep = substep if substep is not None else exec_state.current_substep
        
        task_id = getattr(agent_context, "task_id", None)
        task_db_id = getattr(agent_context, "_task_db_id", None)
        workflow_state_id = getattr(agent_context, "workflow_state_id", None)
        
        # Handle agent type enum or string
        agent_type_obj = getattr(agent_context, "agent_type", None)
        agent_type_val = getattr(agent_type_obj, "value", agent_type_obj)
        
        payload = {
            "status": status,
            "progress": final_progress,
            "current_step": final_substep,
        }
        
        await publish_event(
            kind=EventKind.PROGRESS,
            payload=payload,
            task_id=task_id,
            task_db_id=task_db_id,
            workflow_state_id=workflow_state_id,
            agent_type=agent_type_val,
            agent_name=getattr(agent_context, "agent_name", None),
            execution_order=exec_state.execution_order,
        )
    except Exception as exc:
        logger.warning("Failed to publish progress event: %s", exc)


async def update_progress(
    exec_state: ExecutionState,
    agent_context: Any,
    percentage: int,
    substep: Optional[str] = None,
) -> None:
    """
    更新当前执行的进度摘要并发布事件。
    """
    exec_state.update_progress(percentage, substep)
    
    await send_progress_event(
        exec_state,
        agent_context,
        status="progress",
    )

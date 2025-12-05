from typing import Dict, Any
import logging
import asyncio
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models import Task, Resource, ResourceType, TaskStatus
from ..events.models import Event, EventKind

logger = logging.getLogger(__name__)

async def handle_persistence_event(event: Event) -> None:
    """
    Persistence sink: 接收事件并更新数据库 (Task, Resource)。
    使用同步 Session，通过线程池执行，避免跨事件循环的 async 会话冲突。
    """
    if event.event_kind not in [EventKind.PROGRESS, EventKind.STATE, EventKind.ARTIFACT, EventKind.ERROR]:
        return
    if not event.task_id:
        return

    def _sync_handle() -> None:
        with SessionLocal() as db:
            try:
                if event.event_kind == EventKind.PROGRESS:
                    _update_task_progress(db, event)
                elif event.event_kind == EventKind.STATE:
                    _update_task_status(db, event)
                elif event.event_kind == EventKind.ARTIFACT:
                    _create_resource(db, event)
                elif event.event_kind == EventKind.ERROR:
                    _handle_task_error(db, event)
                db.commit()
            except Exception:
                db.rollback()
                raise

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    try:
        if loop:
            await loop.run_in_executor(None, _sync_handle)
        else:
            _sync_handle()
    except Exception as e:
        logger.error(f"Persistence sink failed for event {event.event_kind}: {e}", exc_info=True)


def _update_task_progress(db: Session, event: Event):
    """更新任务进度"""
    payload = event.payload or {}
    progress = payload.get("progress")
    if progress is None:
        return

    stmt = (
        update(Task)
        .where(Task.task_id == str(event.task_id))
        .values(progress_percentage=int(progress))
    )
    db.execute(stmt)


def _update_task_status(db: Session, event: Event):
    """更新任务状态"""
    payload = event.payload or {}
    status = payload.get("status")
    if not status:
        return
    
    task_status = None
    if status == "failed":
        task_status = TaskStatus.FAILED
    elif status == "completed" and event.agent_type == "orchestrator":
        task_status = TaskStatus.COMPLETED
    elif status == "running" and event.agent_type == "orchestrator":
        task_status = TaskStatus.IN_PROGRESS
        
    if task_status:
        stmt = (
            update(Task)
            .where(Task.task_id == str(event.task_id))
            .values(status=task_status)
        )
        db.execute(stmt)


def _create_resource(db: Session, event: Event):
    """记录产物到 Resource 表"""
    payload = event.payload or {}
    file_path = payload.get("file_path") or payload.get("url")
    if not file_path:
        return

    kind = payload.get("kind", "unknown")
    res_type = ResourceType.UNKNOWN
    if kind == "video": res_type = ResourceType.VIDEO
    elif kind == "image": res_type = ResourceType.IMAGE
    elif kind == "audio": res_type = ResourceType.AUDIO
    elif kind == "text": res_type = ResourceType.TEXT

    stmt = select(Task.id).where(Task.task_id == str(event.task_id))
    result = db.execute(stmt)
    task_db_id = result.scalar_one_or_none()
    
    if not task_db_id:
        logger.warning(f"Cannot record resource: Task {event.task_id} not found in DB")
        return

    resource = Resource(
        task_id=task_db_id,
        resource_type=res_type,
        file_path=file_path,
        resource_metadata=payload.get("metadata", {})
    )
    db.add(resource)


def _handle_task_error(db: Session, event: Event):
    """记录错误信息"""
    payload = event.payload or {}
    error_msg = payload.get("error") or "Unknown error"
    
    stmt = (
        update(Task)
        .where(Task.task_id == str(event.task_id))
        .values(
            status=TaskStatus.FAILED,
            error_message=str(error_msg)[:500]
        )
    )
    db.execute(stmt)

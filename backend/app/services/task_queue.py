"""
Task Queue Service using Celery for background processing
"""
import logging
import time
from typing import Dict, Any
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from ..core.config import settings
from ..core.constants import GenerationMode
from ..core.generation_mode import resolve_generation_mode
from ..models import Task, TaskStatus
from ..services.runtime_session_service import RuntimeSessionService
from .queued_task_execution_host import run_generation_in_host
from .task_execution_policy import get_queue_execution_block_reason


# Create synchronous database session for Celery tasks
# Support both PostgreSQL and MySQL
sync_database_url = settings.DATABASE_URL
if settings.DATABASE_URL.startswith("mysql://"):
    sync_database_url = settings.DATABASE_URL.replace("mysql://", "mysql+pymysql://")

sync_engine = create_engine(sync_database_url)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


def _resolve_task_execution_route(payload: Dict[str, Any]) -> tuple[GenerationMode, str]:
    mode = resolve_generation_mode((payload or {}).get("mode"))
    if mode != GenerationMode.QUICK:
        return mode, "non_quick_mode"
    return mode, "orchestrator_mainline"


class TaskQueueService:
    """Service for managing task queue operations"""
    
    def __init__(self):
        self.logger = logging.getLogger("task_queue")
    
    async def queue_task(self, task_id: int):
        """Queue a task for background processing"""
        
        try:
            # Import here to avoid circular imports
            from .celery_app import process_video_task

            db = SyncSessionLocal()
            try:
                task = db.query(Task).filter(Task.id == task_id).first()
                if task is None:
                    self.logger.warning("Skip queueing task %s because it no longer exists", task_id)
                    return None
                task_payload = dict(task.input_parameters or {})
                mode = resolve_generation_mode(task_payload.get("mode"))
                runtime_session = None
                if mode == GenerationMode.QUICK:
                    runtime_session = RuntimeSessionService.get_latest_session_for_task_sync(db, task.id)

                block_reason = get_queue_execution_block_reason(task, runtime_session)
                if block_reason:
                    self.logger.info(
                        "Skip queueing task %s because it is not execution-eligible (%s)",
                        task_id,
                        block_reason,
                    )
                    return None
            
                # Queue the task with Celery
                result = process_video_task.delay(task_id)

                task = db.query(Task).filter(Task.id == task_id).first()
                if task is not None:
                    output_metadata = dict(task.output_metadata or {})
                    output_metadata["celery_task_id"] = result.id
                    task.output_metadata = output_metadata
                    if task.status == TaskStatus.PENDING.value:
                        task.status = TaskStatus.QUEUED.value
                    db.commit()
                self.logger.info(f"Queued task {task_id} for processing. Celery task ID: {result.id}")
                return result.id
            finally:
                db.close()
            
        except Exception as e:
            self.logger.error(f"Failed to queue task {task_id}: {str(e)}")
            raise


def sync_process_video_task(task_id: int):
    """
    Synchronous function to process video task - called by Celery worker
    """
    logger = logging.getLogger("celery_task")
    
    logger.info(f"=== 🔥 WORKER RESTART: sync_process_video_task called for task_id: {task_id} (v6.0 - MULTI-QUEUE WORKER!) ===")
    
    try:
        logger.info("Creating database session...")
        # Get database session
        db = SyncSessionLocal()
        
        logger.info(f"Querying task with id: {task_id}")
        
        # Get task with retry mechanism for database connection issues
        task = None
        max_db_retries = 3
        for attempt in range(max_db_retries):
            try:
                task = db.query(Task).filter(Task.id == task_id).first()
                break
            except Exception as e:
                if "MySQL server has gone away" in str(e) or "Broken pipe" in str(e):
                    logger.warning(f"Database connection lost, attempt {attempt + 1}/{max_db_retries}: {e}")
                    if attempt < max_db_retries - 1:
                        # 刷新数据库连接
                        try:
                            db.rollback()
                            db.close()
                        except:
                            pass
                        # 重新创建session
                        db = SyncSessionLocal()
                        time.sleep(1)  # 等待1秒后重试
                        continue
                    else:
                        logger.error(f"Database connection failed after {max_db_retries} attempts")
                        raise
                else:
                    # 其他类型的数据库错误直接抛出
                    raise
        
        if not task:
            logger.error(f"Task {task_id} not found in database")
            return {"error": "Task not found"}
        
        logger.info(f"Found task: {task.title} with status: {task.status}")
        logger.info(f"Task input parameters: {task.input_parameters}")

        task_payload = dict(task.input_parameters or {})
        mode, route = _resolve_task_execution_route(task_payload)
        runtime_session = None
        if mode == GenerationMode.QUICK:
            runtime_session = RuntimeSessionService.get_latest_session_for_task_sync(db, task.id)

        block_reason = get_queue_execution_block_reason(
            task,
            runtime_session if mode == GenerationMode.QUICK else None,
        )
        if block_reason:
            logger.info(
                "Skipping queued worker execution for task %s because it is not execution-eligible (%s)",
                task.id,
                block_reason,
            )
            db.close()
            return {
                "status": "skipped",
                "skip_reason": block_reason,
                "route": route,
                "mode": mode.value,
            }

        try:
            logger.info("=== Starting multi-agent execution ===")
            runtime_session, dispatch_payload = RuntimeSessionService.prepare_dispatch_payload_for_task_sync(
                db,
                task,
                mode=mode,
            )
            if runtime_session is not None:
                logger.info(f"Loaded runtime session {runtime_session.id} for task {task.id}")

            result = run_generation_in_host(
                mode,
                task=task,
                input_data=dispatch_payload,
                db=db,
                route=route,
                execution_order=1,
            )
            logger.info(f"=== Multi-agent execution completed ===")
            logger.info(f"Kernel result: {result}")
            
            return result
            
        finally:
            logger.info("Closing database session...")
            db.close()
            logger.info("Database session cleaned up")
    
    except Exception as e:
        logger.error(f"Error processing task {task_id}: {str(e)}", exc_info=True)
        
        # Update task with error
        try:
            logger.info("Updating task with error status...")
            db = SyncSessionLocal()
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                runtime_session = RuntimeSessionService.mark_task_execution_failed_sync(
                    db,
                    task,
                    error_message=str(e),
                )
                if runtime_session is not None:
                    logger.info("Task marked as failed with runtime session error message")
            db.close()
        except Exception as db_error:
            logger.error(f"Failed to update task with error: {str(db_error)}")
        
        return {"error": str(e)}


# Task status monitoring functions
def get_task_queue_stats() -> Dict[str, Any]:
    """Get statistics about the task queue"""
    
    try:
        from .celery_app import celery_app
        
        # Get active tasks
        active_tasks = celery_app.control.inspect().active()
        
        # Get scheduled tasks  
        scheduled_tasks = celery_app.control.inspect().scheduled()
        
        # Get reserved tasks
        reserved_tasks = celery_app.control.inspect().reserved()
        
        # Count tasks
        total_active = sum(len(tasks) for tasks in (active_tasks or {}).values())
        total_scheduled = sum(len(tasks) for tasks in (scheduled_tasks or {}).values())
        total_reserved = sum(len(tasks) for tasks in (reserved_tasks or {}).values())
        
        return {
            "active_tasks": total_active,
            "scheduled_tasks": total_scheduled,
            "reserved_tasks": total_reserved,
            "total_pending": total_active + total_scheduled + total_reserved,
            "worker_status": "online" if active_tasks is not None else "offline"
        }
        
    except Exception as e:
        logging.getLogger("task_queue").error(f"Failed to get queue stats: {str(e)}")
        return {
            "active_tasks": 0,
            "scheduled_tasks": 0,
            "reserved_tasks": 0,
            "total_pending": 0,
            "worker_status": "unknown",
            "error": str(e)
        }


def cancel_celery_task(celery_task_id: str) -> bool:
    """Cancel a Celery task by ID"""
    
    try:
        from .celery_app import celery_app
        
        celery_app.control.revoke(celery_task_id, terminate=True)
        return True
        
    except Exception as e:
        logging.getLogger("task_queue").error(f"Failed to cancel Celery task {celery_task_id}: {str(e)}")
        return False

"""
Task Queue Service using Celery for background processing
"""
import asyncio
import logging
import time
from typing import Dict, Any
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from ..core.config import settings
from ..core.database import get_sync_db
from ..models import Task, TaskStatus
from ..agents import OrchestratorAgent


# Create synchronous database session for Celery tasks
# Support both PostgreSQL and MySQL
sync_database_url = settings.DATABASE_URL
if settings.DATABASE_URL.startswith("mysql://"):
    sync_database_url = settings.DATABASE_URL.replace("mysql://", "mysql+pymysql://")

sync_engine = create_engine(sync_database_url)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


class TaskQueueService:
    """Service for managing task queue operations"""
    
    def __init__(self):
        self.logger = logging.getLogger("task_queue")
    
    async def queue_task(self, task_id: int):
        """Queue a task for background processing"""
        
        try:
            # Import here to avoid circular imports
            from .celery_app import process_video_task
            
            # Queue the task with Celery
            result = process_video_task.delay(task_id)
            
            self.logger.info(f"Queued task {task_id} for processing. Celery task ID: {result.id}")
            
            return result.id
            
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
        # CRITICAL: Initialize tool registry for Celery worker
        logger.info("Initializing tool registry for Celery worker...")
        from ..agents.tools import register_default_tools
        register_default_tools()
        logger.info("✅ Tool registry initialized for Celery worker")
        
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
        
        logger.info(f"Updating task status to IN_PROGRESS...")
        # Update task status
        task.status = TaskStatus.IN_PROGRESS.value
        db.commit()
        logger.info("Task status updated successfully")
        
        logger.info("Setting up asyncio event loop...")
        # Convert async execution to sync using asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("Event loop created and set")
        
        logger.info("Creating OrchestratorAgent...")
        # Create orchestrator and run workflow
        orchestrator = OrchestratorAgent()
        logger.info(f"OrchestratorAgent created: {orchestrator}")
        
        try:
            logger.info("=== Starting multi-agent execution ===")
            # Execute the workflow
            result = loop.run_until_complete(
                orchestrator.execute(
                    task=task,
                    input_data=task.input_parameters or {},
                    db=db,
                    execution_order=0
                )
            )
            
            logger.info(f"=== Multi-agent execution completed ===")
            logger.info(f"Orchestrator result: {result}")
            
            # Update task status to completed
            task.status = TaskStatus.COMPLETED.value
            db.commit()
            logger.info(f"Task {task_id} marked as completed")
            
            return {"status": "completed", "result": result}
            
        finally:
            logger.info("Closing event loop and database session...")
            loop.close()
            db.close()
            logger.info("Resources cleaned up")
    
    except Exception as e:
        logger.error(f"Error processing task {task_id}: {str(e)}", exc_info=True)
        
        # Update task with error
        try:
            logger.info("Updating task with error status...")
            db = SyncSessionLocal()
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED.value
                task.error_message = str(e)
                db.commit()
                logger.info("Task marked as failed with error message")
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
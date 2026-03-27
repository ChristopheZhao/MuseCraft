"""
Sibling project-job queue service for project-level workflow handlers.
"""
from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..core.config import settings
from ..core.story_plan import ProjectOperationState, project_state_repository
from ..models import Task, TaskStatus
from .project_job_contract import resolve_project_job_contract
from .project_job_execution_host import run_project_job_in_host
from .task_execution_policy import get_queue_execution_block_reason


sync_database_url = settings.DATABASE_URL
if settings.DATABASE_URL.startswith("mysql://"):
    sync_database_url = settings.DATABASE_URL.replace("mysql://", "mysql+pymysql://")

sync_engine = create_engine(sync_database_url)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


class ProjectJobQueueService:
    """Queue service for project-level workflow handlers."""

    def __init__(self):
        self.logger = logging.getLogger("project_job_queue")

    def queue_task(self, task_id: int):
        try:
            from .celery_app import process_project_job

            db = SyncSessionLocal()
            try:
                task = db.query(Task).filter(Task.id == task_id).first()
                if task is None:
                    self.logger.warning("Skip queueing project job %s because it no longer exists", task_id)
                    return None

                task_payload = dict(task.input_parameters or {})
                job_kind, handler_key = resolve_project_job_contract(task_payload)

                block_reason = get_queue_execution_block_reason(task)
                if block_reason:
                    self.logger.info(
                        "Skip queueing project job %s because it is not execution-eligible (%s)",
                        task_id,
                        block_reason,
                    )
                    return None

                result = process_project_job.delay(task_id)

                task = db.query(Task).filter(Task.id == task_id).first()
                if task is not None:
                    output_metadata = dict(task.output_metadata or {})
                    output_metadata["celery_task_id"] = result.id
                    output_metadata["project_job"] = {
                        "job_kind": job_kind,
                        "handler_key": handler_key,
                    }
                    task.output_metadata = output_metadata
                    if task.status == TaskStatus.PENDING.value:
                        task.status = TaskStatus.QUEUED.value
                    db.commit()

                self.logger.info(
                    "Queued project job %s for processing. Celery task ID: %s (job_kind=%s, handler_key=%s)",
                    task_id,
                    result.id,
                    job_kind,
                    handler_key,
                )
                return result.id
            finally:
                db.close()

        except Exception as exc:
            self.logger.error("Failed to queue project job %s: %s", task_id, exc)
            raise


def sync_process_project_job(task_id: int):
    """Synchronous worker-side project-job execution entrypoint."""

    logger = logging.getLogger("project_job")
    logger.info("=== Starting sync_process_project_job for task_id=%s ===", task_id)
    db = None

    try:
        db = SyncSessionLocal()
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.error("Project job task %s not found in database", task_id)
            db.close()
            return {"error": "Task not found"}

        task_payload = dict(task.input_parameters or {})
        job_kind, handler_key = resolve_project_job_contract(task_payload)

        block_reason = get_queue_execution_block_reason(task)
        if block_reason:
            logger.info(
                "Skipping project-job worker execution for task %s because it is not execution-eligible (%s)",
                task.id,
                block_reason,
            )
            db.close()
            return {
                "status": "skipped",
                "skip_reason": block_reason,
                "job_kind": job_kind,
                "handler_key": handler_key,
            }

        project_id = task_payload.get("project_id")
        task.status = TaskStatus.IN_PROGRESS.value
        task.update_progress("Project planning started", 1)
        db.commit()

        if project_id:
            project_state = project_state_repository.get(str(project_id))
            if project_state:
                project_state.progress.planning.status = ProjectOperationState.IN_PROGRESS
                project_state.progress.planning.task_id = str(task.task_id)
                project_state.progress.planning.error = None
                project_state_repository.save(project_state)

        try:
            result = run_project_job_in_host(
                job_kind,
                handler_key,
                task=task,
                input_data=task_payload,
                db=db,
                execution_order=1,
            )

            task.status = TaskStatus.COMPLETED.value
            task.error_message = None
            output_metadata = dict(task.output_metadata or {})
            output_metadata["project_id"] = task_payload.get("project_id")
            output_metadata["project_job"] = {
                "job_kind": job_kind,
                "handler_key": handler_key,
            }
            task.output_metadata = output_metadata
            task.update_progress("Project planning completed", 100)
            db.commit()

            if project_id:
                project_state = project_state_repository.get(str(project_id))
                if project_state:
                    project_state.progress.planning.status = ProjectOperationState.COMPLETED
                    project_state.progress.planning.task_id = str(task.task_id)
                    project_state.progress.planning.error = None
                    project_state_repository.save(project_state)

            return result

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    except Exception as exc:
        logger.error("Error processing project job %s: %s", task_id, exc, exc_info=True)
        try:
            if db is not None:
                try:
                    db.close()
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to close stale DB session for project job %s", task_id)
            db = SyncSessionLocal()
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED.value
                task.error_message = str(exc)
                task.update_progress("Project planning failed", task.progress_percentage or 1)
                db.commit()

                project_id = (task.input_parameters or {}).get("project_id")
                if project_id:
                    project_state = project_state_repository.get(str(project_id))
                    if project_state:
                        project_state.progress.planning.status = ProjectOperationState.FAILED
                        project_state.progress.planning.error = str(exc)
                        project_state_repository.save(project_state)
            db.close()
        except Exception as db_error:  # noqa: BLE001
            logger.error("Failed to update project job %s with error: %s", task_id, db_error)

        return {"error": str(exc)}

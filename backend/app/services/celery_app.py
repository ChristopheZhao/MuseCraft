"""
Celery application configuration
"""
from celery import Celery
from ..core.config import settings

# Create Celery app
celery_app = Celery(
    "short_video_maker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.services.task_queue"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    result_expires=3600,  # 1 hour
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        'process_video_task': {'queue': 'video_processing'},
    },
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
)


@celery_app.task(bind=True, name="process_video_task")
def process_video_task(self, task_id: int):
    """Celery task for processing video generation"""
    
    import logging
    logger = logging.getLogger("celery_task")
    
    logger.info(f"=== Starting Celery task for task_id: {task_id} ===")
    
    # Update task state
    self.update_state(
        state='PROGRESS',
        meta={'current': 0, 'total': 100, 'status': 'Starting video processing...'}
    )
    
    try:
        logger.info("Importing sync_process_video_task function...")
        from .task_queue import sync_process_video_task
        logger.info("Successfully imported sync_process_video_task")
        
        logger.info(f"Calling sync_process_video_task with task_id: {task_id}")
        # Process the task
        result = sync_process_video_task(task_id)
        logger.info(f"sync_process_video_task returned: {result}")
        
        # Update final state
        if isinstance(result, dict) and "error" in result:
            logger.error(f"Task failed with error: {result['error']}")
            self.update_state(
                state='FAILURE',
                meta={'error': result["error"]}
            )
            raise Exception(result["error"])
        else:
            logger.info("Task completed successfully")
            self.update_state(
                state='SUCCESS',
                meta={'result': result, 'status': 'Video processing completed'}
            )
            return result
            
    except ImportError as e:
        error_msg = f"Failed to import sync_process_video_task: {str(e)}"
        logger.error(error_msg)
        self.update_state(
            state='FAILURE',
            meta={'error': error_msg}
        )
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error in Celery task: {str(e)}"
        logger.error(error_msg, exc_info=True)
        self.update_state(
            state='FAILURE',
            meta={'error': error_msg}
        )
        raise


# Task monitoring and management tasks
@celery_app.task(name="cleanup_temp_files")
def cleanup_temp_files():
    """Periodic task to clean up temporary files"""
    
    import asyncio
    from ..services.file_storage import FileStorageService
    
    file_storage = FileStorageService()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        deleted_count = loop.run_until_complete(file_storage.cleanup_temp_files())
        return f"Cleaned up {deleted_count} temporary files"
    finally:
        loop.close()


@celery_app.task(name="health_check")
def health_check():
    """Health check task for monitoring"""
    
    import time
    
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "worker_id": health_check.request.hostname
    }


# Periodic task schedule
celery_app.conf.beat_schedule = {
    'cleanup-temp-files': {
        'task': 'cleanup_temp_files',
        'schedule': 3600.0,  # Every hour
    },
    'health-check': {
        'task': 'health_check', 
        'schedule': 300.0,  # Every 5 minutes
    },
}
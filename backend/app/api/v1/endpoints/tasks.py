"""
Task management API endpoints
"""
import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, Field

from ....core.database import get_db
from ....models import Task, TaskStatus, TaskType, Scene, Resource, AgentExecution
from ....agents import OrchestratorAgent
from ....services.task_queue import TaskQueueService


router = APIRouter()


# Helpers to safely extract enum/string values
def _val(x):
    """Return the string value regardless of Enum or raw string."""
    return getattr(x, "value", x)


# Pydantic models for request/response
class TaskCreateRequest(BaseModel):
    user_prompt: str = Field(..., description="User's video generation request")
    style_preference: Optional[str] = Field(None, description="Optional user style preference hint")
    duration: int = Field(default=30, ge=5, le=300, description="Video duration in seconds")
    aspect_ratio: str = Field(default="16:9", description="Video aspect ratio")
    session_id: Optional[str] = Field(None, description="Session ID for tracking")


class TaskResponse(BaseModel):
    id: int
    task_id: str
    title: str
    status: str
    progress_percentage: int
    current_step: Optional[str]
    created_at: str
    updated_at: str
    estimated_duration: Optional[int]
    error_message: Optional[str]


class TaskDetailResponse(TaskResponse):
    description: Optional[str]
    input_parameters: dict
    output_metadata: dict
    scenes_count: int
    resources_count: int
    agent_executions_count: int


class SceneResponse(BaseModel):
    id: int
    scene_number: int
    scene_type: str
    title: Optional[str]
    description: Optional[str]
    duration: Optional[float]
    start_time: Optional[float]
    end_time: Optional[float]


class ResourceResponse(BaseModel):
    id: int
    filename: str
    resource_type: str
    file_size: Optional[int]
    file_url: Optional[str]
    is_final_output: bool
    processing_status: str


@router.post("/", response_model=TaskResponse)
async def create_task(
    request: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Create a new video generation task"""
    
    import logging
    logger = logging.getLogger("tasks_api")
    logger.info(f"Creating task with request: {request}")
    
    try:
        # Create task record
        logger.info("Creating task record in database...")
        task = Task(
            title=f"Video: {request.user_prompt[:50]}...",
            description=request.user_prompt,
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.PENDING.value,
            session_id=request.session_id,
            input_parameters={
                "user_prompt": request.user_prompt,
                "style_preference": request.style_preference,
                "duration": request.duration,
                "aspect_ratio": request.aspect_ratio
            },
            estimated_duration=request.duration * 10  # Rough estimate: 10 seconds processing per 1 second video
        )
        
        db.add(task)
        await db.commit()
        await db.refresh(task)
        logger.info(f"Task created with ID: {task.id}")
        
        # DEBUG MODE: 直接同步执行，绕过Celery调试
        logger.info("=== DEBUG MODE: 直接执行multi-agent，绕过Celery ===")
        
        try:
            from ....services.task_queue import sync_process_video_task
            logger.info(f"直接调用 sync_process_video_task for task {task.id}")
            
            # 在后台线程中执行，避免阻塞API响应
            import threading
            def run_task():
                try:
                    result = sync_process_video_task(task.id)
                    logger.info(f"直接执行结果: {result}")
                except Exception as e:
                    logger.error(f"直接执行异常: {str(e)}", exc_info=True)
            
            thread = threading.Thread(target=run_task)
            thread.start()
            
            logger.info("Task started in background thread (DEBUG MODE)")
            
        except Exception as e:
            logger.error(f"启动调试执行失败: {str(e)}", exc_info=True)
            
            # 如果调试模式失败，还是走Celery
            logger.info("Fallback to Celery queue...")
            task_queue = TaskQueueService()
            background_tasks.add_task(task_queue.queue_task, task.id)
        
        response = TaskResponse(
            id=task.id,
            task_id=str(task.task_id),
            title=task.title,
            status=_val(task.status),
            progress_percentage=task.progress_percentage,
            current_step=task.current_step,
            created_at=task.created_at.isoformat(),
            updated_at=task.updated_at.isoformat(),
            estimated_duration=task.estimated_duration,
            error_message=task.error_message
        )
        logger.info("Returning response")
        return response
        
    except Exception as e:
        logger.error(f"Error creating task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")


@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    skip: int = 0,
    limit: int = 20,
    status: Optional[TaskStatus] = None,
    session_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List tasks with optional filtering"""
    
    query = select(Task).order_by(desc(Task.created_at))
    
    if status:
        query = query.where(Task.status == status)
    
    if session_id:
        query = query.where(Task.session_id == session_id)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return [
        TaskResponse(
            id=task.id,
            task_id=str(task.task_id),
            title=task.title,
            status=_val(task.status),
            progress_percentage=task.progress_percentage,
            current_step=task.current_step,
            created_at=task.created_at.isoformat(),
            updated_at=task.updated_at.isoformat(),
            estimated_duration=task.estimated_duration,
            error_message=task.error_message
        )
        for task in tasks
    ]


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get detailed information about a specific task"""
    
    # Get task
    query = select(Task).where(Task.task_id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Count related records
    from sqlalchemy import func
    scenes_count = await db.scalar(
        select(func.count(Scene.id)).where(Scene.task_id == task.id)
    ) or 0
    
    resources_count = await db.scalar(
        select(func.count(Resource.id)).where(Resource.task_id == task.id)
    ) or 0
    
    agent_executions_count = await db.scalar(
        select(func.count(AgentExecution.id)).where(AgentExecution.task_id == task.id)
    ) or 0
    
    return TaskDetailResponse(
        id=task.id,
        task_id=str(task.task_id),
        title=task.title,
        description=task.description,
        status=_val(task.status),
        progress_percentage=task.progress_percentage,
        current_step=task.current_step,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
        estimated_duration=task.estimated_duration,
        error_message=task.error_message,
        input_parameters=task.input_parameters or {},
        output_metadata=task.output_metadata or {},
        scenes_count=scenes_count,
        resources_count=resources_count,
        agent_executions_count=agent_executions_count
    )


@router.get("/{task_id}/scenes", response_model=List[SceneResponse])
async def get_task_scenes(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all scenes for a task"""
    
    # Get task
    query = select(Task).where(Task.task_id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Get scenes
    scenes_query = select(Scene).where(Scene.task_id == task.id).order_by(Scene.scene_number)
    scenes_result = await db.execute(scenes_query)
    scenes = scenes_result.scalars().all()
    
    return [
        SceneResponse(
            id=scene.id,
            scene_number=scene.scene_number,
            scene_type=_val(scene.scene_type),
            title=scene.title,
            description=scene.description,
            duration=scene.duration,
            start_time=scene.start_time,
            end_time=scene.end_time
        )
        for scene in scenes
    ]


@router.get("/{task_id}/resources", response_model=List[ResourceResponse])
async def get_task_resources(
    task_id: str,
    resource_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all resources for a task"""
    
    # Get task
    query = select(Task).where(Task.task_id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Get resources
    resources_query = select(Resource).where(Resource.task_id == task.id)
    
    if resource_type:
        resources_query = resources_query.where(Resource.resource_type == resource_type)
    
    resources_query = resources_query.order_by(desc(Resource.created_at))
    resources_result = await db.execute(resources_query)
    resources = resources_result.scalars().all()
    
    return [
        ResourceResponse(
            id=resource.id,
            filename=resource.filename,
            resource_type=_val(resource.resource_type),
            file_size=resource.file_size,
            file_url=resource.get_public_url(),
            is_final_output=resource.is_final_output,
            processing_status=resource.processing_status
        )
        for resource in resources
    ]


@router.get("/{task_id}/status")
async def get_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get current status and progress of a task"""
    
    # Get task
    query = select(Task).where(Task.task_id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Get agent executions
    executions_query = select(AgentExecution).where(
        AgentExecution.task_id == task.id
    ).order_by(AgentExecution.execution_order)
    executions_result = await db.execute(executions_query)
    executions = executions_result.scalars().all()
    
    # Get workflow status from orchestrator
    orchestrator = OrchestratorAgent()
    workflow_status = orchestrator.get_workflow_status(task, db)
    
    return {
        "task_id": str(task.task_id),
        "status": _val(task.status),
        "progress_percentage": task.progress_percentage,
        "current_step": task.current_step,
        "error_message": task.error_message,
        "workflow_status": workflow_status,
        "agent_executions": [
            {
                "agent_type": _val(exec.agent_type),
                "status": _val(exec.status),
                "progress": exec.progress_percentage,
                "duration": exec.duration,
                "error": exec.error_message
            }
            for exec in executions
        ]
    }


@router.post("/{task_id}/retry")
async def retry_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Retry a failed task"""
    
    # Get task
    query = select(Task).where(Task.task_id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.FAILED.value:
        raise HTTPException(status_code=400, detail="Task is not in failed state")
    
    if not task.can_retry:
        raise HTTPException(status_code=400, detail="Task has exceeded maximum retry attempts")
    
    # Reset task for retry
    task.reset_for_retry()
    await db.commit()
    
    # Queue task for processing
    task_queue = TaskQueueService()
    background_tasks.add_task(task_queue.queue_task, task.id)
    
    return {"message": "Task queued for retry", "task_id": str(task.task_id)}


@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Cancel a task"""
    
    # Get task
    query = select(Task).where(Task.task_id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.is_completed:
        raise HTTPException(status_code=400, detail="Cannot cancel completed task")
    
    # Update task status
    task.status = TaskStatus.CANCELLED.value
    await db.commit()
    
    return {"message": "Task cancelled", "task_id": str(task.task_id)}
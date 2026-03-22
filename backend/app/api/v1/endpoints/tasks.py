"""
Task management API endpoints
"""
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, Field

from ....core.database import get_db
from ....models import Task, TaskStatus, TaskType, Scene, Resource, WorkflowSession, WorkflowSessionStatus
from ....services.task_queue import TaskQueueService, cancel_celery_task
from ....services.runtime_session_service import RuntimeSessionService
from ....services.task_execution_policy import (
    is_terminal_task_status,
    is_terminal_runtime_status,
)
from ....core.config import settings


router = APIRouter()


# Helpers to safely extract enum/string values
def _val(x):
    """Return the string value regardless of Enum or raw string."""
    return getattr(x, "value", x)


def _schedule_task_execution(background_tasks: BackgroundTasks, task_db_id: int) -> None:
    """Queue tasks by default; allow local in-process execution only via explicit debug switch."""
    logger = logging.getLogger("tasks_api")
    if not bool(getattr(settings, "TASKS_API_ENABLE_IN_PROCESS_RUNNER", False)):
        task_queue = TaskQueueService()
        background_tasks.add_task(task_queue.queue_task, task_db_id)
        logger.info("Task %s queued through background worker", task_db_id)
        return

    try:
        from ....services.task_queue import sync_process_video_task
    except Exception as exc:
        logger.warning("Debug in-process runner unavailable for task %s: %s", task_db_id, exc, exc_info=True)
        task_queue = TaskQueueService()
        background_tasks.add_task(task_queue.queue_task, task_db_id)
        return

    def run_task() -> None:
        try:
            result = sync_process_video_task(task_db_id)
            logger.info("Direct runtime execution result for task %s: %s", task_db_id, result)
        except Exception as exc:
            logger.error("Direct runtime execution failed for task %s: %s", task_db_id, exc, exc_info=True)

    threading.Thread(target=run_task, daemon=True).start()
    logger.info("Task %s started in background thread (debug in-process runner enabled)", task_db_id)


# Pydantic models for request/response
class VoiceSettings(BaseModel):
    voice_id: Optional[str] = Field(None, description="Preferred voice identifier (forces selection if auto_select=False)")
    language: Optional[str] = Field(None, description="Language code")
    speed: Optional[float] = Field(1.0, ge=0.5, le=1.5, description="Speech rate multiplier")
    pitch: Optional[float] = Field(1.0, ge=0.5, le=1.5, description="Pitch multiplier")
    sample_rate: Optional[int] = Field(None, description="Sample rate in Hz")
    audio_format: Optional[str] = Field(None, description="Audio format, e.g., wav/mp3")
    style: Optional[str] = Field(None, description="Supplier specific style hint")
    auto_select: Optional[bool] = Field(True, description="Whether the agent should auto-select the best voice for each scene")
    preferred_voice_ids: Optional[List[str]] = Field(None, description="Candidate voice ids the agent should prioritise when auto-selecting")

    class Config:
        extra = "ignore"


class TaskCreateRequest(BaseModel):
    user_prompt: str = Field(..., description="User's video generation request")
    style_preference: Optional[str] = Field(None, description="Optional user style preference hint")
    duration: int = Field(default=30, ge=5, le=300, description="Video duration in seconds")
    resolution: Optional[str] = Field(default=None, description="Preferred output resolution (e.g., 720p, 1080p)")
    aspect_ratio: str = Field(default="16:9", description="Video aspect ratio")
    session_id: Optional[str] = Field(None, description="Session ID for tracking")
    voice_settings: Optional[VoiceSettings] = Field(None, description="Voice synthesis configuration")


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


class QuickRunSummaryResponse(BaseModel):
    id: int
    task_id: str
    title: str
    description: Optional[str]
    status: str
    session_id: Optional[str]
    input_parameters: Dict[str, Any]
    created_at: str
    updated_at: str
    error_message: Optional[str]


class QuickCurrentRunResponse(BaseModel):
    task: Optional[QuickRunSummaryResponse]
    workflow_status: Optional[Dict[str, Any]]


class TaskDetailResponse(TaskResponse):
    description: Optional[str]
    input_parameters: dict
    output_metadata: dict
    scenes_count: int
    resources_count: int
    agent_executions_count: int = 0


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


class TaskRuntimeDecisionRequest(BaseModel):
    action: str = Field(..., description="Gate decision action: approve, revise, or replan")
    feedback_text: Optional[str] = Field(None, description="Optional human feedback")
    structured_constraints: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional structured constraints for the next attempt",
    )
    actor_id: Optional[str] = Field(None, description="Optional reviewer identifier")


def _get_task_celery_task_id(task: Task) -> Optional[str]:
    output_metadata = dict(task.output_metadata or {})
    celery_task_id = str(output_metadata.get("celery_task_id") or "").strip()
    return celery_task_id or None


def _set_task_queue_handle(task: Task, celery_task_id: Optional[str], *, status: Optional[str] = None) -> None:
    output_metadata = dict(task.output_metadata or {})
    if celery_task_id:
        output_metadata["celery_task_id"] = celery_task_id
    elif "celery_task_id" in output_metadata:
        output_metadata.pop("celery_task_id", None)
    task.output_metadata = output_metadata
    if status is not None:
        task.status = status


def _serialize_quick_run_summary(task: Task) -> QuickRunSummaryResponse:
    return QuickRunSummaryResponse(
        id=task.id,
        task_id=str(task.task_id),
        title=task.title,
        description=task.description,
        status=_val(task.status),
        session_id=task.session_id,
        input_parameters=task.input_parameters or {},
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
        error_message=task.error_message,
    )


async def _find_unfinished_quick_task_for_session(
    db: AsyncSession,
    session_id: str,
) -> Tuple[Optional[Task], Optional[WorkflowSession]]:
    result = await db.execute(
        select(Task)
        .where(Task.session_id == session_id)
        .order_by(desc(Task.created_at), desc(Task.id))
        .limit(20)
    )
    candidate_tasks = list(result.scalars().all())

    for task in candidate_tasks:
        runtime_session = await RuntimeSessionService.get_latest_session_for_task(db, task.id)
        if runtime_session is not None:
            if runtime_session.mode != "quick":
                continue
            if not is_terminal_runtime_status(runtime_session.status):
                return task, runtime_session
            continue

        if not is_terminal_task_status(task.status):
            return task, None

    return None, None


async def _cancel_task_for_replacement(
    db: AsyncSession,
    task: Task,
    *,
    reason: str,
) -> None:
    celery_task_id = _get_task_celery_task_id(task)
    output_metadata = dict(task.output_metadata or {})
    output_metadata["superseded_reason"] = reason
    output_metadata["superseded_at"] = datetime.now(timezone.utc).isoformat()
    task.output_metadata = output_metadata

    if celery_task_id:
        cancelled = cancel_celery_task(celery_task_id)
        if not cancelled:
            logging.getLogger("tasks_api").warning(
                "Failed to revoke celery task %s while replacing task %s",
                celery_task_id,
                task.id,
            )

    _set_task_queue_handle(task, None)
    await RuntimeSessionService.mark_session_cancelled_for_task(db, task)


@router.post("/", response_model=TaskResponse)
async def create_task(
    request: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Create a new video generation task"""
    
    logger = logging.getLogger("tasks_api")
    logger.info(f"Creating task with request: {request}")
    
    try:
        if request.session_id:
            existing_task, _existing_session = await _find_unfinished_quick_task_for_session(db, request.session_id)
            if existing_task is not None:
                logger.info(
                    "Replacing unfinished quick task %s for workspace session %s before creating a new run",
                    existing_task.id,
                    request.session_id,
                )
                await _cancel_task_for_replacement(
                    db,
                    existing_task,
                    reason="superseded_by_new_run",
                )

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
                "resolution": request.resolution or settings.DEFAULT_VIDEO_RESOLUTION,
                "aspect_ratio": request.aspect_ratio,
                "voice_settings": request.voice_settings.dict(exclude_none=True) if request.voice_settings else None
            },
            estimated_duration=request.duration * 10  # Rough estimate: 10 seconds processing per 1 second video
        )
        
        db.add(task)
        await db.commit()
        await db.refresh(task)
        logger.info(f"Task created with ID: {task.id}")

        runtime_session = await RuntimeSessionService.create_session_for_task(
            db,
            task,
            mode="quick",
        )
        logger.info(f"Runtime session created with ID: {runtime_session.id} for task {task.id}")
        
        logger.info("Dispatching task execution for task %s", task.id)
        _schedule_task_execution(background_tasks, task.id)
        
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


@router.get("/quick/current", response_model=QuickCurrentRunResponse)
async def get_current_quick_run(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Discover the latest unfinished quick run for the current workspace session."""

    task, _runtime_session = await _find_unfinished_quick_task_for_session(db, session_id)
    if task is None:
        return QuickCurrentRunResponse(task=None, workflow_status=None)

    runtime_view = await RuntimeSessionService.build_runtime_view_for_task(db, task)
    return QuickCurrentRunResponse(
        task=_serialize_quick_run_summary(task),
        workflow_status=runtime_view,
    )


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
        agent_executions_count=0
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
    
    runtime_view = await RuntimeSessionService.build_runtime_view_for_task(db, task)
    workflow_status = runtime_view or {
        "task_id": str(task.task_id),
        "overall_status": _val(task.status),
        "overall_progress": task.progress_percentage,
        "current_step": task.current_step,
        "total_steps": task.total_steps,
        "completed_steps": 0,
        "failed_steps": 0,
        "steps": [],
    }

    return {
        "task_id": str(task.task_id),
        "status": _val(task.status),
        "progress_percentage": task.progress_percentage,
        "current_step": task.current_step,
        "error_message": task.error_message,
        "workflow_status": workflow_status,
        "agent_executions": []
    }


@router.get("/{task_id}/runtime")
async def get_task_runtime(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get runtime session summary for a task."""

    query = select(Task).where(Task.task_id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    runtime_view = await RuntimeSessionService.build_runtime_view_for_task(db, task)
    if runtime_view is None:
        raise HTTPException(status_code=404, detail="Runtime session not found")

    return runtime_view


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
    await RuntimeSessionService.create_session_for_task(
        db,
        task,
        mode="quick",
    )

    # Queue task for processing
    _schedule_task_execution(background_tasks, task.id)
    
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

    await _cancel_task_for_replacement(db, task, reason="cancelled_by_user")
    
    return {"message": "Task cancelled", "task_id": str(task.task_id)}


@router.post("/{task_id}/runtime/script/decision")
async def submit_script_gate_decision(
    task_id: str,
    request: TaskRuntimeDecisionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Submit a human decision for the script review gate and resume execution."""

    query = select(Task).where(Task.task_id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    runtime_session = await RuntimeSessionService.get_latest_session_for_task(db, task.id)
    if runtime_session is None:
        raise HTTPException(status_code=404, detail="Runtime session not found")

    try:
        await db.run_sync(
            lambda sync_db: RuntimeSessionService.submit_gate_decision_sync(
                sync_db,
                runtime_session.id,
                node_key="script",
                action=request.action,
                feedback_text=request.feedback_text,
                structured_constraints=request.structured_constraints,
                actor_type="human",
                actor_id=request.actor_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _schedule_task_execution(background_tasks, task.id)
    runtime_view = await RuntimeSessionService.build_runtime_view_for_task(db, task)
    return {
        "message": "Script gate decision accepted",
        "task_id": str(task.task_id),
        "workflow_status": runtime_view,
    }

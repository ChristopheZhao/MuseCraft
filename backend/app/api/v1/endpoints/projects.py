"""Project definition commands and immutable execution projections."""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ....core.constants import GenerationMode
from ....core.story_plan import EpisodePlan, ProjectDefinition, StoryPlan
from ....domain import ProjectDefinitionError, ProjectDefinitionReason, ProjectExecutionReadModel
from ....infrastructure.project_definition_composition import (
    build_project_definition_service,
    build_project_execution_read_model_query,
    build_project_workflow_service,
)
from ....services.project_job_contract import attach_project_plan_contract
from ....services.project_job_queue import ProjectJobQueueService
from ....services.task_queue import TaskQueueService

router = APIRouter()


class EpisodePlanModel(BaseModel):
    episode_id: str
    sequence_index: int
    title: str
    target_duration_seconds: int
    summary: str = ""
    narrative_purpose: str = ""
    continuity_notes: Dict[str, Any] = Field(default_factory=dict)
    required_assets: Dict[str, Any] = Field(default_factory=dict)
    script_draft: str = ""
    approved_script: str = ""
    editorial_revision: int = 0
    status: str


class StoryPlanModel(BaseModel):
    project_id: str
    user_prompt: str
    target_duration_seconds: int
    aspect_ratio: str
    episodes: List[EpisodePlanModel]
    global_theme: str = ""
    character_bible: Dict[str, Any] = Field(default_factory=dict)
    visual_style: Dict[str, Any] = Field(default_factory=dict)
    tone_and_mood: str = ""
    additional_notes: Dict[str, Any] = Field(default_factory=dict)


class EpisodeRuntimeModel(BaseModel):
    episode_id: str
    status: str
    approved_script: str = ""
    workflow_task_id: Optional[str] = None
    aggregated_cost: float = 0.0
    aggregated_tokens: int = 0
    output_assets: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class ProjectOperationStatusModel(BaseModel):
    status: str
    task_id: Optional[str] = None
    error: Optional[str] = None


class ProjectProgressModel(BaseModel):
    planning: ProjectOperationStatusModel
    character_references: ProjectOperationStatusModel


class ProjectResponse(BaseModel):
    project_id: str
    mode: str
    version: int
    story_plan: StoryPlanModel
    episodes_runtime: Dict[str, EpisodeRuntimeModel] = Field(default_factory=dict)
    progress: ProjectProgressModel
    global_settings: Dict[str, Any] = Field(default_factory=dict)
    cost_budget: Optional[float] = None
    total_cost: float = 0.0
    total_tokens: int = 0
    completed_episodes: int = 0
    style_profile: Dict[str, Any] = Field(default_factory=dict)
    character_bible: Dict[str, Any] = Field(default_factory=dict)


class ProjectCreateRequest(BaseModel):
    user_prompt: str
    target_duration_seconds: int = Field(..., ge=60)
    mode: str = Field("project", pattern="^(project|quick)$")
    aspect_ratio: str = "16:9"
    resolution: Optional[str] = None
    style_preference: Optional[str] = None
    episode_cap_seconds: int = Field(60, ge=30, le=120)
    episode_min_seconds: int = Field(45, ge=20, le=90)
    global_theme: Optional[str] = None
    character_bible: Dict[str, Any] = Field(default_factory=dict)
    visual_style: Dict[str, Any] = Field(default_factory=dict)
    tone_and_mood: Optional[str] = None
    additional_notes: Dict[str, Any] = Field(default_factory=dict)
    project_id: Optional[str] = None
    auto_generate_scripts: bool = True
    generate_character_references: bool = True


class ProjectCreateResponse(BaseModel):
    project: ProjectResponse
    task_id: str
    status: str


class EpisodeScriptRequest(BaseModel):
    script_text: str
    expected_version: int = Field(..., ge=1)
    approve: bool = False
    additional_notes: Dict[str, str] = Field(default_factory=dict)


class EpisodeGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=1)
    episode_ids: List[str] = Field(default_factory=list)
    episode_indices: List[int] = Field(default_factory=list)
    auto_approve: bool = False
    force_rerun: bool = False
    project_character_reference_images_enabled: Optional[bool] = None


class EpisodeGenerationResponse(BaseModel):
    task_id: str
    status: str
    result: Dict[str, Any]
    project: ProjectResponse


def _serialize_project_read_model(model: ProjectExecutionReadModel) -> ProjectResponse:
    definition = model.definition.to_dict()
    story_dict = dict(definition.get("story_plan") or {})
    story_dict["episodes"] = [
        EpisodePlanModel(**episode) for episode in story_dict.get("episodes", [])
    ]
    story_dict.setdefault("global_theme", "")
    story_dict.setdefault("tone_and_mood", "")
    story_dict.setdefault("character_bible", {})
    story_dict.setdefault("visual_style", {})
    story_dict.setdefault("additional_notes", {})
    runtime = {
        episode.episode_id: EpisodeRuntimeModel(
            episode_id=episode.episode_id,
            status=episode.status,
            approved_script=episode.approved_script,
            workflow_task_id=episode.workflow_task_id,
            aggregated_cost=episode.aggregated_cost,
            aggregated_tokens=episode.aggregated_tokens,
            output_assets=episode.output_assets.to_dict(),
            error=episode.error,
        )
        for episode in model.episodes
    }
    return ProjectResponse(
        project_id=model.project_id,
        mode=model.mode,
        version=model.definition_version,
        story_plan=StoryPlanModel(**story_dict),
        episodes_runtime=runtime,
        progress=ProjectProgressModel(
            planning=ProjectOperationStatusModel(
                status=model.planning.status,
                task_id=model.planning.task_id,
                error=model.planning.error,
            ),
            character_references=ProjectOperationStatusModel(
                status=model.character_references.status,
                task_id=model.character_references.task_id,
                error=model.character_references.error,
            ),
        ),
        global_settings=dict(definition.get("global_settings") or {}),
        cost_budget=definition.get("cost_budget"),
        total_cost=model.total_cost,
        total_tokens=model.total_tokens,
        completed_episodes=model.completed_episodes,
        style_profile=dict(definition.get("style_profile") or {}),
        character_bible=dict(definition.get("character_bible") or {}),
    )


def _project_definition(request: ProjectCreateRequest, project_id: str) -> ProjectDefinition:
    target_duration = max(60, int(request.target_duration_seconds))
    episode_cap = int(request.episode_cap_seconds)
    episode_min = int(request.episode_min_seconds)
    episode_count = max(1, math.ceil(target_duration / episode_cap))
    planned_duration = max(episode_min, min(episode_cap, target_duration // episode_count))
    story_plan = StoryPlan(
        project_id=project_id,
        user_prompt=request.user_prompt,
        target_duration_seconds=target_duration,
        aspect_ratio=request.aspect_ratio,
        global_theme=request.global_theme or "",
        character_bible=request.character_bible,
        visual_style=request.visual_style,
        tone_and_mood=request.tone_and_mood or "",
        additional_notes=request.additional_notes,
    )
    remainder = target_duration
    for index in range(episode_count):
        duration = remainder if index == episode_count - 1 else planned_duration
        remainder = max(0, remainder - duration)
        story_plan.add_episode(
            EpisodePlan.create(index, f"Episode {index + 1}", duration, summary="")
        )
    return ProjectDefinition(
        project_id=project_id,
        mode=request.mode,
        story_plan=story_plan,
        global_settings={
            "resolution": request.resolution,
            "style_preference": request.style_preference,
        },
        style_profile=request.visual_style,
        character_bible=request.character_bible,
    )


def _planning_payload(request: ProjectCreateRequest, project_id: str) -> dict[str, object]:
    return attach_project_plan_contract(
        {
            "project_id": project_id,
            "user_prompt": request.user_prompt,
            "target_duration_seconds": request.target_duration_seconds,
            "mode": request.mode,
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
            "style_preference": request.style_preference,
            "episode_cap_seconds": request.episode_cap_seconds,
            "episode_min_seconds": request.episode_min_seconds,
            "global_theme": request.global_theme,
            "character_bible": request.character_bible,
            "visual_style": request.visual_style,
            "tone_and_mood": request.tone_and_mood,
            "additional_notes": request.additional_notes,
            "auto_generate_scripts": request.auto_generate_scripts,
            "generate_character_references": request.generate_character_references,
        }
    )


def _http_project_error(exc: ProjectDefinitionError) -> HTTPException:
    if exc.reason_code is ProjectDefinitionReason.RECORD_NOT_FOUND:
        code = status.HTTP_404_NOT_FOUND
    elif exc.reason_code in {
        ProjectDefinitionReason.VERSION_CONFLICT,
        ProjectDefinitionReason.ALREADY_EXISTS,
    }:
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=code,
        detail={"reason_code": exc.reason_code.value, "message": str(exc)},
    )


def _read_project(project_id: str) -> ProjectResponse:
    try:
        return _serialize_project_read_model(
            build_project_execution_read_model_query().get(project_id)
        )
    except ProjectDefinitionError as exc:
        raise _http_project_error(exc) from exc


@router.post("/", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_project(request: ProjectCreateRequest) -> ProjectCreateResponse:
    if request.mode != GenerationMode.PROJECT.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only project mode supports episode orchestration in this endpoint.",
        )
    project_id = request.project_id or str(uuid.uuid4())
    try:
        receipt = build_project_workflow_service().create_project(
            definition=_project_definition(request, project_id),
            planning_input=_planning_payload(request, project_id),
            title=f"Project plan {project_id}",
            description=request.user_prompt,
        )
        transport_id = ProjectJobQueueService().queue_task(receipt.task.task_id)
        if not transport_id:
            raise RuntimeError("Project planning transport returned no dispatch receipt")
    except ProjectDefinitionError as exc:
        raise _http_project_error(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"reason_code": "project_planning_dispatch_failed", "message": str(exc)},
        ) from exc
    return ProjectCreateResponse(
        project=_read_project(project_id),
        task_id=receipt.task.task_id,
        status=receipt.task.status.value,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str) -> ProjectResponse:
    return _read_project(project_id)


@router.put("/{project_id}/episodes/{episode_id}/script", response_model=ProjectResponse)
async def update_episode(
    project_id: str,
    episode_id: str,
    request: EpisodeScriptRequest,
) -> ProjectResponse:
    try:
        build_project_definition_service().update_episode_script(
            project_id=project_id,
            episode_id=episode_id,
            script_text=request.script_text,
            approve=request.approve,
            expected_version=request.expected_version,
            additional_notes=request.additional_notes or None,
        )
    except ProjectDefinitionError as exc:
        raise _http_project_error(exc) from exc
    return _read_project(project_id)


@router.post("/{project_id}/orchestrate", response_model=EpisodeGenerationResponse)
async def orchestrate_project(
    project_id: str,
    request: EpisodeGenerationRequest,
    background_tasks: BackgroundTasks,
) -> EpisodeGenerationResponse:
    current = _read_project(project_id)
    if current.progress.planning.status in {"pending", "queued", "in_progress"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason_code": "project_planning_in_progress",
                "message": "Project planning must complete before episode execution",
            },
        )
    payload = request.model_dump()
    payload["mode"] = GenerationMode.PROJECT.value
    try:
        receipt = build_project_workflow_service().enqueue_episode_execution(
            project_id=project_id,
            expected_version=request.expected_version,
            episode_ids=request.episode_ids,
            episode_indices=request.episode_indices,
            auto_approve=request.auto_approve,
            execution_input=payload,
            title=f"Episode orchestration {project_id}",
            description=(f"Episodes: {request.episode_ids or request.episode_indices or 'all'}"),
        )
    except ProjectDefinitionError as exc:
        raise _http_project_error(exc) from exc

    queue = TaskQueueService()
    background_tasks.add_task(queue.queue_task, receipt.task.task_id)
    return EpisodeGenerationResponse(
        task_id=receipt.task.task_id,
        status=receipt.task.status.value,
        result={},
        project=_read_project(project_id),
    )

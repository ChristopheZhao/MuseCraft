"""Helper functions for project-mode state management."""

from __future__ import annotations

from typing import Dict, Optional

from ..core.story_plan import (
    EpisodePlan,
    EpisodeStatus,
    ProjectState,
    project_state_repository,
)
from ..agents.base import AgentError


def get_project_state(project_id: str) -> ProjectState:
    project_state = project_state_repository.get(project_id)
    if not project_state:
        raise AgentError(f"Project state not found: {project_id}")
    return project_state


def update_episode_script(
    project_id: str,
    episode_id: str,
    script_text: str,
    approve: bool = False,
    additional_notes: Optional[Dict[str, str]] = None,
) -> ProjectState:
    project_state = get_project_state(project_id)
    episode = _locate_episode(project_state, episode_id)
    if not episode:
        raise AgentError(f"Episode not found: {episode_id}")

    episode.script_draft = script_text
    runtime = project_state.ensure_runtime_state(episode_id)
    runtime.approved_script = script_text

    if approve:
        episode.status = EpisodeStatus.APPROVED
        runtime.status = EpisodeStatus.APPROVED
        runtime.error = None
    else:
        if runtime.status in {EpisodeStatus.COMPLETED, EpisodeStatus.GENERATING}:
            runtime.status = EpisodeStatus.NEEDS_REVISION
        else:
            runtime.status = EpisodeStatus.PENDING_APPROVAL
        episode.status = runtime.status

    if additional_notes:
        runtime.output_assets.setdefault("notes", {}).update(additional_notes)

    project_state_repository.save(project_state)
    return project_state


def mark_episode_status(
    project_id: str,
    episode_id: str,
    status: EpisodeStatus,
    error: Optional[str] = None,
) -> ProjectState:
    project_state = get_project_state(project_id)
    episode = _locate_episode(project_state, episode_id)
    if not episode:
        raise AgentError(f"Episode not found: {episode_id}")

    episode.status = status
    runtime = project_state.ensure_runtime_state(episode_id)
    runtime.status = status
    runtime.error = error
    project_state.mark_episode_status(episode_id, status, error)
    project_state_repository.save(project_state)
    return project_state


def _locate_episode(project_state: ProjectState, episode_id: str) -> Optional[EpisodePlan]:
    for episode in project_state.story_plan.episodes:
        if episode.episode_id == episode_id:
            return episode
    return None

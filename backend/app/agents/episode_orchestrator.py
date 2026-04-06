"""EpisodeOrchestratorAgent bridges project-mode episodes with the MAS pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from .orchestrator import OrchestratorAgent
from ..models import Task, AgentType, TaskStatus, TaskType
from ..core.config import settings
from ..core.story_plan import (
    EpisodePlan,
    EpisodeEditorialStatus,
    EpisodeExecutionStatus,
    ProjectState,
    merge_character_bibles,
    project_state_repository,
)
from ..services.character_reference_images import ensure_project_character_reference_images
from ..services.memory_provider import MemoryServices, build_memory_services


class EpisodeOrchestratorAgent(BaseAgent):
    """Sequentially executes approved episodes while reusing the 1-minute MAS workflow."""

    @classmethod
    def create_default(cls) -> "EpisodeOrchestratorAgent":
        return cls(memory_services=build_memory_services())

    def __init__(
        self,
        memory_services: Optional[MemoryServices] = None,
        llms=None,
        orchestrator: Optional[OrchestratorAgent] = None,
    ) -> None:
        if memory_services is None:
            raise ValueError("memory_services is required for EpisodeOrchestratorAgent")
        self._memory_services = memory_services
        super().__init__(
            agent_type=AgentType.EPISODE_ORCHESTRATOR,
            agent_name="episode_orchestrator",
            timeout_seconds=3600,
            max_retries=1,
            tools=[],
            llms=llms,
            memory_services=self._memory_services,
        )
        self._base_orchestrator = orchestrator or OrchestratorAgent(memory_services=self._memory_services)

    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        self._validate_input(input_data, ["project_id"])

        project_id = input_data["project_id"]
        project_state = project_state_repository.get(project_id)
        if not project_state:
            raise AgentError(f"Project state not found: {project_id}")

        task.error_message = None
        task.status = TaskStatus.IN_PROGRESS.value
        task.update_progress("Episode orchestration started", 0)
        db.commit()

        self._sync_project_foundation(project_state)
        await self._ensure_project_character_reference_images(project_state, input_data)

        episodes_to_run = self._resolve_episode_selection(project_state, input_data)
        if not episodes_to_run:
            raise AgentError("No episodes selected for orchestration")

        auto_approve = bool(input_data.get("auto_approve", False))
        force_rerun = bool(input_data.get("force_rerun", False))

        results: List[Dict[str, Any]] = []
        total = len(episodes_to_run)

        for idx, episode in enumerate(episodes_to_run, start=1):
            runtime = project_state.ensure_runtime_state(episode.episode_id)

            if auto_approve and episode.status in {
                EpisodeEditorialStatus.DRAFT,
                EpisodeEditorialStatus.PENDING_APPROVAL,
            }:
                episode.status = EpisodeEditorialStatus.APPROVED

            if runtime.status == EpisodeExecutionStatus.GENERATING:
                runtime.status = EpisodeExecutionStatus.STALE

            if episode.status != EpisodeEditorialStatus.APPROVED:
                results.append(
                    {
                        "episode_id": episode.episode_id,
                        "status": runtime.status.value,
                        "skipped": True,
                        "reason": "Episode script not approved for generation",
                    }
                )
                continue

            if not force_rerun and runtime.status not in {
                EpisodeExecutionStatus.IDLE,
                EpisodeExecutionStatus.STALE,
                EpisodeExecutionStatus.FAILED,
                EpisodeExecutionStatus.COMPLETED,
            }:
                results.append(
                    {
                        "episode_id": episode.episode_id,
                        "status": runtime.status.value,
                        "skipped": True,
                        "reason": "Episode runtime is not ready for generation",
                    }
                )
                continue

            await self._update_progress(int((idx - 1) / total * 90), f"Generating episode {idx}/{total}", db)
            task.update_progress(f"Generating episode {idx}/{total}", int((idx - 1) / total * 90))
            db.commit()

            episode_result = await self._run_single_episode(
                base_task=task,
                episode=episode,
                project_state=project_state,
                db=db,
            )
            results.append(episode_result)

            await self._update_progress(int(idx / total * 90), f"Episode {idx}/{total} completed", db)
            task.update_progress(f"Episode {idx}/{total} completed", int(idx / total * 90))
            db.commit()

        project_state_repository.save(project_state)
        db.commit()

        await self._update_progress(100, "Episode orchestration finished", db)
        task.update_progress("Episode orchestration finished", 100)

        if any(res.get("status") == EpisodeExecutionStatus.FAILED.value for res in results):
            task.status = TaskStatus.FAILED.value
            task.error_message = "One or more episodes failed during orchestration"
        else:
            task.status = TaskStatus.COMPLETED.value
            task.error_message = None
        db.commit()

        return {
            "status": task.status,
            "project_id": project_id,
            "episodes": results,
            "total_completed": project_state.completed_episodes,
            "total_cost": project_state.total_cost,
        }

    def _resolve_episode_selection(
        self, project_state: ProjectState, input_data: Dict[str, Any]
    ) -> List[EpisodePlan]:
        story_plan = project_state.story_plan
        if not story_plan.episodes:
            return []

        requested_ids = set(input_data.get("episode_ids", []) or [])
        requested_indices = set(input_data.get("episode_indices", []) or [])

        if not requested_ids and not requested_indices:
            return list(story_plan.episodes)

        selected: List[EpisodePlan] = []
        for episode in story_plan.episodes:
            if requested_ids and episode.episode_id in requested_ids:
                selected.append(episode)
            elif requested_indices and episode.sequence_index in requested_indices:
                selected.append(episode)
        return selected

    def _sync_project_foundation(self, project_state: ProjectState) -> None:
        """Keep project-level foundation aligned with the canonical story-plan surface."""

        story_plan = project_state.story_plan
        changed = False

        merged_characters = merge_character_bibles(
            story_plan.character_bible or {},
            project_state.character_bible or {},
        )
        if (
            merged_characters != (project_state.character_bible or {})
            or project_state.character_bible is not merged_characters
        ):
            project_state.character_bible = merged_characters
            changed = True
        if (
            merged_characters != (story_plan.character_bible or {})
            or story_plan.character_bible is not merged_characters
        ):
            story_plan.character_bible = merged_characters
            changed = True

        style_profile = dict(project_state.style_profile or {})
        story_style = dict(story_plan.visual_style or {})
        if not style_profile and story_style:
            project_state.style_profile = dict(story_style)
            changed = True
        elif style_profile and style_profile != story_style:
            story_plan.visual_style = dict(style_profile)
            changed = True

        if changed:
            project_state_repository.save(project_state)

    async def _ensure_project_character_reference_images(
        self,
        project_state: ProjectState,
        input_data: Dict[str, Any],
    ) -> None:
        """Delegate optional character-reference generation to the project service."""

        requested = input_data.get("project_character_reference_images_enabled")
        enabled = (
            bool(requested)
            if requested is not None
            else bool(getattr(settings, "PROJECT_CHARACTER_REFERENCE_IMAGES_ENABLED", False))
        )
        await ensure_project_character_reference_images(
            project_state.project_id,
            enabled=enabled,
            logger=self.logger,
        )
        refreshed_state = project_state_repository.get(project_state.project_id)
        if refreshed_state is not None:
            project_state.sync_from(refreshed_state)


    async def _run_single_episode(
        self,
        base_task: Task,
        episode: EpisodePlan,
        project_state: ProjectState,
        db: Session,
    ) -> Dict[str, Any]:
        runtime_state = project_state.ensure_runtime_state(episode.episode_id)
        runtime_state.status = EpisodeExecutionStatus.GENERATING
        runtime_state.error = None

        episode_payload = self._build_episode_payload(
            episode=episode,
            project_state=project_state,
        )

        episode_task = Task(
            title=f"Episode {episode.sequence_index + 1} workflow",
            description=f"Project {project_state.project_id} episode {episode.sequence_index + 1}",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.PENDING.value,
            session_id=base_task.session_id,
            user_id=base_task.user_id,
            input_parameters=episode_payload.copy(),
        )
        db.add(episode_task)
        db.commit()
        db.refresh(episode_task)

        try:
            if hasattr(self._base_orchestrator, "reset_repeat_counters"):
                self._base_orchestrator.reset_repeat_counters()
            orchestrator_result = await self._base_orchestrator.execute(
                task=episode_task,
                input_data=episode_payload,
                db=db,
                execution_order=1,
            )
        except Exception as exc:  # noqa: BLE001 - preserve MAS errors
            runtime_state.status = EpisodeExecutionStatus.FAILED
            runtime_state.error = str(exc)
            episode_task.status = TaskStatus.FAILED.value
            episode_task.error_message = str(exc)
            db.commit()
            project_state_repository.save(project_state)
            return {
                "episode_id": episode.episode_id,
                "status": EpisodeExecutionStatus.FAILED.value,
                "error": str(exc),
            }

        runtime_state.status = EpisodeExecutionStatus.COMPLETED
        runtime_state.workflow_task_id = orchestrator_result.get("workflow_state_id")
        runtime_state.output_assets = self._extract_episode_assets(orchestrator_result)
        episode_task.status = TaskStatus.COMPLETED.value
        db.commit()

        project_state.mark_episode_runtime_status(episode.episode_id, EpisodeExecutionStatus.COMPLETED)
        project_state_repository.save(project_state)

        return {
            "episode_id": episode.episode_id,
            "status": EpisodeExecutionStatus.COMPLETED.value,
            "assets": runtime_state.output_assets,
            "workflow_state_id": runtime_state.workflow_task_id,
            "task_id": episode_task.task_id,
        }

    def _build_episode_payload(
        self,
        episode: EpisodePlan,
        project_state: ProjectState,
    ) -> Dict[str, Any]:
        story_plan = project_state.story_plan
        runtime_state = project_state.ensure_runtime_state(episode.episode_id)

        # Compose a minimal, episode-focused textual prompt. Project-level background stays out of the prompt.
        summary_text = (episode.summary or "").strip() or "N/A"
        episode_title = (episode.title or "").strip() or f"Episode {episode.sequence_index + 1}"
        narrative_purpose = (episode.narrative_purpose or "").strip()
        total_episodes = len(story_plan.episodes)
        episode_index_display = episode.sequence_index + 1

        prompt_lines: List[str] = [
            f"Episode {episode_index_display}/{total_episodes}: {episode_title}",
            f"Episode summary: {summary_text}",
        ]
        if narrative_purpose:
            prompt_lines.append(f"Narrative purpose: {narrative_purpose}")
        prompt_lines.append(f"Target duration: {episode.target_duration_seconds}s")
        if episode.continuity_notes:
            prompt_lines.append("Continuity notes: " + str(episode.continuity_notes))

        episode_prompt = "\n".join(prompt_lines)

        payload = {
            "user_prompt": episode_prompt,
            "duration": episode.target_duration_seconds,
            "aspect_ratio": story_plan.aspect_ratio,
            "style_preference": project_state.global_settings.get("style_preference"),
        }
        if project_state.global_settings.get("resolution"):
            payload["resolution"] = project_state.global_settings["resolution"]

        if project_state.style_profile:
            payload["intelligent_style_design"] = project_state.style_profile
            payload["predefined_style_profile"] = project_state.style_profile

        # Project-wide canonical characters help downstream agents maintain consistency.
        if project_state.character_bible:
            character_source = project_state.character_bible
        else:
            character_source = story_plan.character_bible

        character_payload = {
            cid: (profile.to_dict() if hasattr(profile, "to_dict") else profile)
            for cid, profile in (character_source or {}).items()
        }
        if character_payload:
            payload["character_bible"] = character_payload
        if story_plan.visual_style:
            payload["visual_style"] = story_plan.visual_style

        episode_context: Dict[str, Any] = {
            "episode_index": episode_index_display,
            "sequence_index": episode.sequence_index,
            "episode_count": total_episodes,
            "title": episode_title,
            "summary": summary_text,
            "narrative_purpose": narrative_purpose,
            "target_duration_seconds": episode.target_duration_seconds,
            "continuity_notes": episode.continuity_notes or {},
        }
        if runtime_state.approved_script:
            episode_context["approved_script"] = runtime_state.approved_script
        if episode.required_assets:
            episode_context["required_assets"] = episode.required_assets
        relevant_character_ids = self._extract_episode_characters(episode, character_payload)
        if relevant_character_ids:
            episode_context["character_ids"] = relevant_character_ids
        if project_state.style_profile:
            episode_context["style_profile"] = project_state.style_profile
        payload["episode_context"] = episode_context

        user_prompt_brief = (story_plan.user_prompt or "").strip()
        project_context: Dict[str, Any] = {
            "project_brief": user_prompt_brief[:200] if user_prompt_brief else "",
            "global_theme": story_plan.global_theme or "",
            "character_bible": character_payload,
            "visual_style": story_plan.visual_style or {},
            "tone_and_mood": story_plan.tone_and_mood or "",
            "additional_notes": story_plan.additional_notes or {},
        }
        if project_state.style_profile:
            project_context["style_profile"] = project_state.style_profile
        payload["project_context"] = project_context

        payload.setdefault("concept_mode", "episode")
        return payload

    def _extract_episode_characters(
        self,
        episode: EpisodePlan,
        character_payload: Dict[str, Dict[str, Any]],
    ) -> List[str]:
        if not character_payload:
            return []

        name_lookup: Dict[str, str] = {}
        for canonical_id, profile in character_payload.items():
            display_name = str(profile.get("display_name") or "").strip()
            if display_name:
                name_lookup.setdefault(display_name, canonical_id)
            for alias in profile.get("aliases") or []:
                alias_name = str(alias).strip()
                if alias_name:
                    name_lookup.setdefault(alias_name, canonical_id)

        referenced: List[str] = []

        alias_lookup: Dict[str, str] = {}
        for cid, profile in (character_payload or {}).items():
            if not isinstance(profile, dict):
                continue
            display = str(profile.get("display_name") or "").strip()
            if display:
                alias_lookup.setdefault(display.casefold(), cid)
            alias_lookup.setdefault(str(cid).casefold(), cid)
            for alias in profile.get("aliases") or []:
                alias_name = str(alias).strip()
                if alias_name:
                    alias_lookup.setdefault(alias_name.casefold(), cid)

        def _register(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    _register(item)
                return
            if isinstance(value, dict):
                for nested in value.values():
                    _register(nested)
                return
            candidate = str(value).strip()
            if not candidate:
                return
            canonical_id = name_lookup.get(candidate) or alias_lookup.get(candidate.casefold())
            if not canonical_id:
                # Attempt case-insensitive lookup
                lower_candidate = candidate.casefold()
                if lower_candidate in alias_lookup:
                    canonical_id = alias_lookup[lower_candidate]
            if canonical_id and canonical_id not in referenced:
                referenced.append(canonical_id)

        _register(episode.required_assets or {})
        _register(episode.continuity_notes or {})

        # Textual heuristics：从摘要 / 目的 / 脚本草稿中检索角色别名
        text_candidates: List[str] = []
        for blob in [
            getattr(episode, "summary", ""),
            getattr(episode, "narrative_purpose", ""),
            getattr(episode, "script_draft", ""),
        ]:
            if isinstance(blob, str) and blob.strip():
                text_candidates.append(blob.strip().lower())

        for cid, profile in (character_payload or {}).items():
            if cid in referenced:
                continue
            display = str(profile.get("display_name") or "").strip().lower()
            aliases = [display] if display else []
            aliases += [str(a).strip().lower() for a in profile.get("aliases") or [] if str(a).strip()]
            aliases.append(str(cid).strip().lower())
            for text_blob in text_candidates:
                if not text_blob:
                    continue
                if any(alias and alias in text_blob for alias in aliases if alias):
                    referenced.append(cid)
                    break

        if not referenced:
            # 兜底：若无法识别具体角色，则默认返回全部角色，避免完全失配
            referenced = list(character_payload.keys())

        return referenced

    def _extract_episode_assets(self, orchestrator_result: Dict[str, Any]) -> Dict[str, Any]:
        results = orchestrator_result.get("results", {}) or {}
        composer_output = results.get("video_composer", {}) or {}
        quality_output = results.get("quality_checker", {}) or {}

        return {
            "final_video_url": orchestrator_result.get("final_video_url")
            or composer_output.get("final_video_url"),
            "final_video_path": composer_output.get("final_video_path"),
            "quality": quality_output,
        }

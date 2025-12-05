"""EpisodeOrchestratorAgent bridges project-mode episodes with the MAS pipeline."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from .concept_planner import ConceptPlannerAgent
from .orchestrator import OrchestratorAgent
from .utils.llm_policy import LLMPolicyManager
from ..models import Task, AgentType, TaskStatus, TaskType
from ..core.config import settings
from ..core.workflow_state import workflow_manager
from ..core.story_plan import (
    EpisodePlan,
    EpisodeStatus,
    ProjectState,
    merge_character_bibles,
    normalize_character_elements,
    project_state_repository,
)
from ..services.style_taxonomy import summarize_style_taxonomy


class EpisodeOrchestratorAgent(BaseAgent):
    """Sequentially executes approved episodes while reusing the 1-minute MAS workflow."""

    def __init__(
        self,
        llms=None,
        orchestrator: Optional[OrchestratorAgent] = None,
        concept_planner: Optional[ConceptPlannerAgent] = None,
    ) -> None:
        super().__init__(
            agent_type=AgentType.EPISODE_ORCHESTRATOR,
            agent_name="episode_orchestrator",
            timeout_seconds=3600,
            max_retries=1,
            tools=[],
            llms=llms,
        )
        self._base_orchestrator = orchestrator or OrchestratorAgent()
        base_policy = getattr(self._base_orchestrator, "_llm_policy", None)
        if base_policy is None:
            policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
            base_policy = LLMPolicyManager(policy_file)
        self._llm_policy = base_policy

        if concept_planner is not None:
            self._concept_agent = concept_planner
        else:
            llms = None
            try:
                llms = self._llm_policy.build_llms_for_agent("concept_planner")
            except Exception:
                llms = None
            self._concept_agent = ConceptPlannerAgent(llms=llms)

        try:
            concept_llms = self._llm_policy.build_llms_for_agent("concept_planner")
            existing_llms = getattr(self._concept_agent, "_llms", {}) or {}
            merged = dict(concept_llms)
            merged.update(existing_llms)
            self._concept_agent._llms = merged
        except Exception:
            pass

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

        await self._ensure_project_foundation(task, project_state, db)

        episodes_to_run = self._resolve_episode_selection(project_state, input_data)
        if not episodes_to_run:
            raise AgentError("No episodes selected for orchestration")

        auto_approve = bool(input_data.get("auto_approve", False))
        force_rerun = bool(input_data.get("force_rerun", False))

        results: List[Dict[str, Any]] = []
        total = len(episodes_to_run)

        task.error_message = None
        
        task.status = TaskStatus.IN_PROGRESS.value
        task.update_progress("Episode orchestration started", 0)
        db.commit()

        for idx, episode in enumerate(episodes_to_run, start=1):
            runtime = project_state.ensure_runtime_state(episode.episode_id)

            if auto_approve and runtime.status in {
                EpisodeStatus.DRAFT,
                EpisodeStatus.PENDING_APPROVAL,
            }:
                runtime.status = EpisodeStatus.APPROVED
                episode.status = EpisodeStatus.APPROVED

            if runtime.status == EpisodeStatus.GENERATING:
                runtime.status = EpisodeStatus.APPROVED
                episode.status = EpisodeStatus.APPROVED

            if not force_rerun and runtime.status not in {
                EpisodeStatus.APPROVED,
                EpisodeStatus.NEEDS_REVISION,
            }:
                results.append(
                    {
                        "episode_id": episode.episode_id,
                        "status": runtime.status.value,
                        "skipped": True,
                        "reason": "Episode not approved for generation",
                    }
                )
                continue

            await self._update_progress(
                execution,
                int((idx - 1) / total * 90),
                f"Generating episode {idx}/{total}",
                db,
            )
            task.update_progress(f"Generating episode {idx}/{total}", int((idx - 1) / total * 90))
            db.commit()

            episode_result = await self._run_single_episode(
                base_task=task,
                episode=episode,
                project_state=project_state,
                runtime_overrides=input_data.get("runtime_overrides", {}),
                db=db,
            )
            results.append(episode_result)

            await self._update_progress(
                execution,
                int(idx / total * 90),
                f"Episode {idx}/{total} completed",
                db,
            )
            task.update_progress(f"Episode {idx}/{total} completed", int(idx / total * 90))
            db.commit()

        project_state_repository.save(project_state)
        execution.output_data = {"episodes": results}
        db.commit()

        await self._update_progress(100, "Episode orchestration finished", db)
        task.update_progress("Episode orchestration finished", 100)

        if any(res.get("status") == EpisodeStatus.FAILED.value for res in results):
            task.status = TaskStatus.FAILED.value
            task.error_message = "One or more episodes failed during orchestration"
        else:
            task.status = TaskStatus.COMPLETED.value
            task.error_message = None
        db.commit()

        return {
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

    async def _ensure_project_foundation(
        self,
        base_task: Task,
        project_state: ProjectState,
        db: Session,
    ) -> None:
        """Run a project-level concept pass to lock style and character bible."""

        if project_state.style_profile and project_state.character_bible:
            return

        story_plan = project_state.story_plan
        taxonomy_summary = summarize_style_taxonomy()
        style_preference = project_state.global_settings.get("style_preference")

        workflow_state = workflow_manager.create_workflow(
            user_prompt=story_plan.user_prompt,
            style_preference=style_preference,
            duration=story_plan.target_duration_seconds,
            aspect_ratio=story_plan.aspect_ratio,
            resolution=project_state.global_settings.get("resolution")
            or settings.DEFAULT_VIDEO_RESOLUTION,
        )

        concept_payload = {
            "user_prompt": story_plan.user_prompt,
            "duration": story_plan.target_duration_seconds,
            "aspect_ratio": story_plan.aspect_ratio,
            "workflow_state_id": workflow_state.task_id,
            "style_preference": style_preference,
            "concept_mode": "project",
            "style_taxonomy_summary": taxonomy_summary,
        }

        concept_task = Task(
            title=f"Project concept foundation {project_state.project_id}",
            description=story_plan.user_prompt,
            # 使用现有类型以避免数据库 ENUM 迁移需求
            task_type=TaskType.SCRIPT_WRITING,
            status=TaskStatus.PENDING.value,
            session_id=base_task.session_id,
            user_id=base_task.user_id,
            input_parameters=concept_payload.copy(),
        )
        db.add(concept_task)
        db.commit()
        db.refresh(concept_task)

        try:
            result = await self._concept_agent.execute(
                task=concept_task,
                input_data=concept_payload,
                db=db,
            )
            concept_task.status = TaskStatus.COMPLETED.value
            concept_task.error_message = None
            db.commit()
        except Exception as concept_exc:
            concept_task.status = TaskStatus.FAILED.value
            concept_task.error_message = str(concept_exc)
            db.commit()
            workflow_manager.remove_workflow(workflow_state.task_id)
            raise
        else:
            workflow_manager.remove_workflow(workflow_state.task_id)

        concept_plan = result.get("concept_plan", {}) or {}
        style_profile = concept_plan.get("intelligent_style_design") or {}
        if style_profile:
            project_state.style_profile = style_profile
            project_state.story_plan.visual_style = dict(style_profile)

        content_elements = concept_plan.get("content_elements")
        characters_payload = None
        if isinstance(content_elements, dict):
            characters_payload = content_elements.get("characters")

        sanitized_characters, normalized_characters = normalize_character_elements(characters_payload)

        if isinstance(content_elements, dict) and characters_payload is not None:
            content_elements["characters"] = sanitized_characters

        if normalized_characters:
            project_state.character_bible = merge_character_bibles(
                project_state.character_bible,
                normalized_characters,
            )
            project_state.story_plan.merge_character_profiles(normalized_characters)

        project_state_repository.save(project_state)


    async def _run_single_episode(
        self,
        base_task: Task,
        episode: EpisodePlan,
        project_state: ProjectState,
        runtime_overrides: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        runtime_state = project_state.ensure_runtime_state(episode.episode_id)
        runtime_state.status = EpisodeStatus.GENERATING
        runtime_state.error = None
        episode.status = EpisodeStatus.GENERATING

        episode_payload = self._build_episode_payload(
            episode=episode,
            project_state=project_state,
            runtime_overrides=runtime_overrides,
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
            runtime_state.status = EpisodeStatus.FAILED
            runtime_state.error = str(exc)
            episode.status = EpisodeStatus.FAILED
            episode_task.status = TaskStatus.FAILED.value
            episode_task.error_message = str(exc)
            db.commit()
            project_state_repository.save(project_state)
            return {
                "episode_id": episode.episode_id,
                "status": EpisodeStatus.FAILED.value,
                "error": str(exc),
            }

        runtime_state.status = EpisodeStatus.COMPLETED
        runtime_state.workflow_task_id = orchestrator_result.get("workflow_state_id")
        runtime_state.output_assets = self._extract_episode_assets(orchestrator_result)
        episode.status = EpisodeStatus.COMPLETED
        episode_task.status = TaskStatus.COMPLETED.value
        db.commit()

        project_state.mark_episode_status(episode.episode_id, EpisodeStatus.COMPLETED)
        project_state_repository.save(project_state)

        return {
            "episode_id": episode.episode_id,
            "status": EpisodeStatus.COMPLETED.value,
            "assets": runtime_state.output_assets,
            "workflow_state_id": runtime_state.workflow_task_id,
            "task_id": episode_task.task_id,
        }

    def _build_episode_payload(
        self,
        episode: EpisodePlan,
        project_state: ProjectState,
        runtime_overrides: Dict[str, Any],
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
        payload.update(runtime_overrides or {})
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

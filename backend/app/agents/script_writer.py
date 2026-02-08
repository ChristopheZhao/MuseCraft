"""
Script Writer Agent - 简化版批量脚本生成
移除复杂的ReAct接口，直接实现批量处理
"""
import json
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentType
from .adapters.video.models import SceneSnapshot
from ..core.consistency_policy import get_consistency_policy
from ..services.style_taxonomy import match_style_taxonomy
from .utils.artifacts import extract_tool_payload
from .adapters.memory_views import load_scene_overview, load_concept_plan
from .utils.memory_helpers import read_shared_fact, write_shared_fact


class ScriptWriterAgent(BaseAgent):
    """
    Script Writer Agent - 简化版批量脚本生成
    专注于场景脚本、叙事结构和连续性分析，但使用BaseAgent接口
    """
    
    def __init__(self, llms=None, memory_services=None):
        super().__init__(
            agent_type=AgentType.SCRIPT_WRITER,
            agent_name="script_writer",
            timeout_seconds=600,
            max_retries=2,
            tools=[
                # 使用已注册名称，避免依赖校验回退：
                "script_generation",
                "scene_continuity_analysis_tool",
                "narrative_structure_generation_tool",
                "role_analysis_tool",
            ],
            llms=llms,
            memory_services=memory_services,
        )
        
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session = None,
    ) -> Dict[str, Any]:
        """批量脚本生成 - 实现在 _execute_impl，使用 BaseAgent.execute 统一包装"""
        try:
            from ..core.config import settings

            # 动态超时：基于.env配置的基数、每场景增量和最大值
            scene_count = self._estimate_scene_count(input_data)
            base = getattr(settings, 'SCRIPT_WRITER_TIMEOUT_BASE', 180)
            per_scene = getattr(settings, 'SCRIPT_WRITER_TIMEOUT_PER_SCENE', 30)
            max_timeout = getattr(settings, 'SCRIPT_WRITER_TIMEOUT_MAX', 900)
            if scene_count > 0:
                dynamic_timeout = min(max_timeout, base + scene_count * per_scene)
                self.timeout_seconds = int(dynamic_timeout)

            workflow_state_id = input_data.get("workflow_state_id")
            wf_id_str = str(workflow_state_id) if workflow_state_id else ""
            if not wf_id_str:
                raise AgentError("workflow_state_id missing")

            # 读取 MAS WM 作为上下文
            overview = load_scene_overview(wf_id_str, service=self.short_term_service)
            scenes_payload = overview.get("scenes") if isinstance(overview, dict) else []
            scenes: List[SceneSnapshot] = []
            for entry in scenes_payload or []:
                if not isinstance(entry, dict):
                    continue
                try:
                    scenes.append(
                        SceneSnapshot(
                            scene_number=int(entry.get("scene_number")),
                            depends_on_scene=entry.get("depends_on_scene"),
                            duration=float(entry.get("duration") or 0.0),
                            visual_description=entry.get("visual_description", "") or "",
                            narrative_description=entry.get("narrative_description", "") or "",
                            image_url=entry.get("image_url", "") or "",
                            motion_beats=entry.get("motion_beats") or [],
                        )
                    )
                except Exception:
                    continue

            episode_context = input_data.get("episode_context")
            if episode_context is None:
                episode_context = read_shared_fact(wf_id_str, "episode_context", None, service=self.short_term_service)

            project_context = input_data.get("project_context")
            if project_context is None:
                project_context = read_shared_fact(wf_id_str, "project_context", None, service=self.short_term_service)
            approved_script_text = ""
            if episode_context:
                approved_script_text = str(episode_context.get("approved_script", "") or "").strip()

            episode_character_ids: List[str] = []
            if episode_context:
                self.logger.info(
                    "🧠 ScriptWriter received episode_context (approved_script=%s)",
                    bool(approved_script_text),
                )
                episode_character_ids = [
                    str(cid).strip()
                    for cid in episode_context.get("character_ids", []) or []
                    if str(cid).strip()
                ]

            concept_plan = load_concept_plan(wf_id_str, service=self.short_term_service) or {}

            if not scenes:
                raise AgentError("No scenes available for script generation")

            # 批量生成脚本
            return await self._batch_generate_scripts(
                scenes,
                concept_plan,
                str(workflow_state_id),
                task,
                episode_context=episode_context,
                project_context=project_context,
                approved_script_text=approved_script_text,
            )

        except AgentError:
            raise
        except Exception as e:
            self.logger.error("ScriptWriter execution failed: %s", e, exc_info=True)
            raise AgentError(f"ScriptWriter execution failed: {e}") from e

    async def _batch_generate_scripts(
        self,
        scenes: List[SceneSnapshot],
        concept_plan: Dict[str, Any],
        workflow_state_id: str,
        task: Task,
        *,
        episode_context: Optional[Dict[str, Any]] = None,
        project_context: Optional[Dict[str, Any]] = None,
        approved_script_text: str = "",
    ) -> Dict[str, Any]:
        """批量生成场景脚本"""
        # 从入参 episode_context 推导本集涉及的角色ID（若存在）
        episode_character_ids: List[str] = []
        try:
            if isinstance(episode_context, dict):
                raw_ids = episode_context.get("character_ids") or []
                if isinstance(raw_ids, list):
                    episode_character_ids = [
                        str(cid).strip() for cid in raw_ids if str(cid).strip()
                    ]
        except Exception:
            episode_character_ids = []

        # 旁白规划从记忆槽读取
        try:
            voice_plan = read_shared_fact(workflow_state_id, "project.voice_plan", {}, service=self.short_term_service) or {}
        except Exception:
            voice_plan = {}
        voice_plan_enabled = True
        if isinstance(voice_plan, dict):
            enabled_raw = voice_plan.get("enabled")
            if isinstance(enabled_raw, str):
                voice_plan_enabled = enabled_raw.strip().lower() not in {"false", "0", "no", "off"}
            elif isinstance(enabled_raw, bool):
                voice_plan_enabled = enabled_raw
            mode = str(voice_plan.get("mode", "narration")).strip().lower()
            if mode == "none":
                voice_plan_enabled = False
        else:
            voice_plan_enabled = True

        voice_guidance_map: Dict[int, Dict[str, Any]] = {}
        if isinstance(voice_plan, dict):
            for entry in voice_plan.get("scene_guidance", []) or []:
                if not isinstance(entry, dict):
                    continue
                try:
                    sn = int(entry.get("scene_number"))
                except (TypeError, ValueError):
                    continue
                if sn <= 0:
                    continue
                voice_guidance_map[sn] = entry

        # 筛选需要脚本的场景（兼容 SceneSnapshot：可能没有 script_text/title 字段）
        scenes_needing_scripts = []
        for scene in scenes:
            try:
                script_text = getattr(scene, "script_text", None)
                needs = (not script_text) or (isinstance(script_text, str) and len(script_text.strip()) < 50)
            except Exception:
                needs = True
            if needs:
                scenes_needing_scripts.append(scene)
        
        if not scenes_needing_scripts:
            return {
                "success": True,
                "message": "所有场景脚本已完成",
                "scenes_generated": 0,
                "workflow_state_updated": False
            }
        
        try:
            self.logger.info(f"开始批量生成{len(scenes_needing_scripts)}个场景脚本")
            
            # 准备批量生成参数
            batch_scenes = []
            for scene in scenes_needing_scripts:
                try:
                    batch_scenes.append(
                        {
                            "scene_number": int(getattr(scene, "scene_number")),
                            "title": str(getattr(scene, "title", "") or ""),
                            "duration": float(getattr(scene, "duration", 0.0) or 0.0),
                            "narrative_description": str(getattr(scene, "narrative_description", "") or ""),
                        }
                    )
                except Exception:
                    # 遇到异常时尽力而为，填充最小字段以不中断批量
                    batch_scenes.append(
                        {
                            "scene_number": getattr(scene, "scene_number", None),
                            "title": "",
                            "duration": 0.0,
                            "narrative_description": "",
                        }
                    )
            
            # 批量生成脚本（使用 script_generation 工具的 generate_scene_scripts_batch 动作）
            scripts_map: Dict[str, Any] = {}
            hard_failed_voice_scenes: List[Dict[str, Any]] = []
            warning_voice_scenes: List[Dict[str, Any]] = []
            voice_guidance_by_scene: Dict[str, Dict[str, Any]] = {}
            batch_inputs: List[Dict[str, Any]] = []
            failed_scene_numbers: set[str] = set()

            def _scene_key(value: Any) -> str:
                return str(value) if value is not None else "unknown"

            def _record_failure(scene_number: Any, reason: str) -> None:
                key = _scene_key(scene_number)
                if key in failed_scene_numbers:
                    return
                failed_scene_numbers.add(key)
                hard_failed_voice_scenes.append(
                    {
                        "scene_number": scene_number,
                        "reason": reason,
                    }
                )
            intelligent_style = concept_plan.get('intelligent_style_design', {}) if isinstance(concept_plan, dict) else {}
            if isinstance(intelligent_style, dict) and intelligent_style:
                taxonomy_match = match_style_taxonomy(intelligent_style)
                if taxonomy_match:
                    enriched_style = dict(intelligent_style)
                    enriched_style['taxonomy'] = taxonomy_match
                    intelligent_style = enriched_style
                    if isinstance(concept_plan, dict):
                        concept_plan['intelligent_style_design'] = enriched_style
                        try:
                            write_shared_fact(workflow_state_id, "project.concept_plan", concept_plan, service=self.short_term_service)
                        except Exception as slot_err:
                            raise AgentError(
                                f"Failed to persist enriched concept_plan: {slot_err}"
                            ) from slot_err
            # 读取脚本写作模型与token预算（来自ai_config）
            try:
                from ..core.ai_config import get_ai_config
                from ..core.config import settings as _settings
                ai_cfg = get_ai_config()
                script_model = ai_cfg.get_model_for_agent("script_writer")
                model_cfg = ai_cfg.get_model_config(script_model)
                max_tokens_budget = int(model_cfg.max_tokens) if model_cfg and getattr(model_cfg, 'max_tokens', None) else int(getattr(_settings, 'LLM_MAX_TOKENS_STANDARD', 2048))
            except Exception:
                script_model = None
                max_tokens_budget = 1500
            try:
                from ..core.config import settings as _settings
                max_concurrency = int(getattr(_settings, "SCRIPT_GENERATION_MAX_CONCURRENCY", 3))
            except Exception:
                max_concurrency = 3
            for scene in scenes_needing_scripts:
                try:
                    guidance = voice_guidance_map.get(scene.scene_number)
                    if guidance:
                        should_narrate = bool(guidance.get("should_narrate", voice_plan_enabled))
                    else:
                        should_narrate = bool(voice_plan_enabled)

                    if should_narrate:
                        if not guidance:
                            self.logger.warning(
                                "Scene %s voice plan 缺少 guidance，跳过旁白规划",
                                scene.scene_number,
                            )
                            should_narrate = False

                    if should_narrate:
                        pace_tag = str(guidance.get("pace_tag", "")).strip().lower() if guidance else ""
                        if not pace_tag:
                            raise AgentError(
                                f"Scene {scene.scene_number} voice plan 缺少 pace_tag"
                            )
                        target_char_count = guidance.get("target_char_count")
                        if target_char_count is None:
                            raise AgentError(
                                f"Scene {scene.scene_number} voice plan 缺少 target_char_count"
                            )
                        try:
                            target_char_count = int(target_char_count)
                        except (TypeError, ValueError):
                            raise AgentError(
                                f"Scene {scene.scene_number} voice plan target_char_count 非法"
                            )
                    else:
                        pace_tag = ""
                        target_char_count = None

                    context_payload: Dict[str, Any] = {
                        "previous_scene": "",
                        "narrative_arc": concept_plan.get('genre_and_theme', {}).get('theme', '')
                    }
                    if episode_context:
                        context_payload["episode_context"] = episode_context
                    if episode_character_ids:
                        context_payload["episode_characters"] = episode_character_ids
                    if project_context:
                        context_payload["project_context"] = project_context
                        char_bible = project_context.get("character_bible") if isinstance(project_context, dict) else {}
                        if isinstance(char_bible, dict) and char_bible:
                            context_payload["character_bible"] = char_bible
                    if approved_script_text:
                        context_payload["approved_script"] = approved_script_text

                    tool_params = {
                        "scene_number": scene.scene_number,
                        "scene_data": {
                            "scene_number": scene.scene_number,
                            "visual_description": scene.visual_description,
                            "narrative_description": scene.narrative_description,
                            "duration": scene.duration,
                        },
                        "intelligent_style_design": intelligent_style,
                        "context": context_payload,
                        # 让工具按配置使用模型和token预算，替代内部默认值
                        "model": script_model,
                        "max_tokens": max_tokens_budget,
                    }
                    if episode_character_ids:
                        tool_params["scene_data"]["character_ids"] = episode_character_ids
                    if project_context:
                        char_bible = project_context.get("character_bible") if isinstance(project_context, dict) else {}
                        if isinstance(char_bible, dict) and char_bible:
                            tool_params["character_bible"] = char_bible
                    gd = guidance or {}
                    tool_params["voice_guidance"] = {
                        "should_narrate": should_narrate,
                        "pace_tag": pace_tag,
                        "target_char_count": target_char_count,
                        "key_points": gd.get("key_points", []),
                        "emotion": gd.get("emotion", ""),
                        "objective": gd.get("objective", ""),
                    }
                    batch_inputs.append(tool_params)
                    voice_guidance_by_scene[_scene_key(scene.scene_number)] = tool_params["voice_guidance"]
                except AgentError as ae:
                    _record_failure(scene.scene_number, str(ae))
                    self.logger.warning(f"场景 {scene.scene_number} 脚本生成失败: {ae}")
                except Exception as se:
                    _record_failure(scene.scene_number, str(se))
                    self.logger.warning(f"场景 {scene.scene_number} 脚本生成失败: {se}")

            batch_payload: Dict[str, Any] = {"scripts": {}, "failures": []}
            if batch_inputs:
                call = {
                    "function": {
                        "name": "script_generation.generate_scene_scripts_batch",
                        "arguments": {
                            "scenes": batch_inputs,
                            "max_concurrency": max_concurrency,
                        },
                    }
                }
                executed = await self.execute_tool_calls([call])
                if not executed:
                    raise AgentError("批量脚本生成失败：无执行结果")
                rec = executed[0]
                payload = extract_tool_payload(rec.get('result')) if isinstance(rec, dict) else None
                if not isinstance(payload, dict):
                    raise AgentError("批量脚本生成失败: payload_not_dict")
                batch_payload = payload

            failures = batch_payload.get("failures", []) if isinstance(batch_payload, dict) else []
            if isinstance(failures, list):
                for failure in failures:
                    if not isinstance(failure, dict):
                        continue
                    _record_failure(failure.get("scene_number"), failure.get("error", "script_generation_failed"))

            batch_scripts = batch_payload.get("scripts", {}) if isinstance(batch_payload, dict) else {}
            for scene in scenes_needing_scripts:
                if _scene_key(scene.scene_number) in failed_scene_numbers:
                    continue
                script_payload = None
                if isinstance(batch_scripts, dict):
                    script_payload = batch_scripts.get(str(scene.scene_number))
                    if script_payload is None:
                        script_payload = batch_scripts.get(scene.scene_number)
                if not isinstance(script_payload, dict):
                    _record_failure(scene.scene_number, "script_generation_failed_or_empty")
                    continue
                try:
                    script_section = script_payload.get("script") if isinstance(script_payload.get("script"), dict) else {}
                    voice_line = (
                        script_payload.get("voice_over_text")
                        or script_payload.get("voice_over")
                        or script_section.get("voice_over")
                        or script_section.get("voiceover")
                    )
                    if isinstance(voice_line, list):
                        voice_line = " ".join(str(v).strip() for v in voice_line if str(v).strip())
                    elif voice_line is not None:
                        voice_line = str(voice_line).strip()

                    motion_beats = self._sanitize_motion_beats(
                        script_payload.get("motion_beats"),
                        scene.duration,
                    )
                    guidance_payload = voice_guidance_by_scene.get(_scene_key(scene.scene_number), {})
                    is_valid_voice, warning_msg = self._validate_voice_line(
                        scene.scene_number, voice_line, guidance_payload
                    )
                    if not is_valid_voice and warning_msg:
                        warning_voice_scenes.append({
                            "scene_number": scene.scene_number,
                            "warning": warning_msg,
                        })
                        self.logger.warning(
                            "场景 %s 旁白字数与规划存在偏差：%s",
                            scene.scene_number,
                            warning_msg,
                        )
                    scripts_map[str(scene.scene_number)] = {
                        "script_text": script_payload.get("script_text", script_payload.get("content", "") or script_section.get("script_text", "")),
                        "narrative_description": script_payload.get("narrative_description", scene.narrative_description),
                        "background_music_style": script_payload.get("background_music_style", ""),
                        "sound_effects": script_payload.get("sound_effects", []),
                        "voice_over_text": voice_line or "",
                        "voice_guidance": guidance_payload,
                        "motion_beats": motion_beats,
                    }
                except AgentError as ae:
                    _record_failure(scene.scene_number, str(ae))
                    self.logger.warning(f"场景 {scene.scene_number} 脚本生成失败: {ae}")
                except Exception as se:
                    _record_failure(scene.scene_number, str(se))
                    self.logger.warning(f"场景 {scene.scene_number} 脚本生成失败: {se}")
            script_results = {
                "success": True,
                "scripts": scripts_map,
                "failed_voice_scenes": hard_failed_voice_scenes,
                "voice_over_warnings": warning_voice_scenes,
            }
            
            # 连续性分析（可选），调用统一的 analyze_all_scenes_continuity
            try:
                cont_params = {
                    "scenes": [
                        {
                            "scene_number": s["scene_number"],
                            "title": s.get("title", ""),
                            "description": s.get("narrative_description", "") or "",
                            "script_text": scripts_map.get(str(s["scene_number"])) and scripts_map[str(s["scene_number"])].get("script_text", "") or "",
                            "narrative_description": s.get("narrative_description", "") or "",
                            "mood_and_atmosphere": ""
                        } for s in batch_scenes
                    ],
                    "overall_narrative": concept_plan.get('overview', ''),
                    "narrative_flow": concept_plan.get('genre_and_theme', {}).get('theme', ''),
                    "main_message": ":".join(concept_plan.get('key_messages', [])) if concept_plan.get('key_messages') else ""
                }
                call = {
                    "function": {
                        "name": "scene_continuity_analysis_tool.analyze_all_scenes_continuity",
                        "arguments": cont_params,
                    }
                }
                cont_exec = await self.execute_tool_calls([call])
                continuity_analysis = {}
                if cont_exec and isinstance(cont_exec[0], dict):
                    payload = extract_tool_payload(cont_exec[0].get('result'))
                    if isinstance(payload, dict):
                        continuity_analysis = payload
                if not isinstance(continuity_analysis, dict) or not continuity_analysis:
                    continuity_analysis = {"warning": "连续性分析失败"}
            except Exception as e:
                self.logger.warning(f"连续性分析失败，继续脚本生成: {e}")
                continuity_analysis = {"warning": "连续性分析失败"}

            # 更新workflow_state
            generated_count = 0
            # 标准化回合结果：供编排器统计 success/failed
            generation_results: List[Dict[str, Any]] = []
            if scripts_map:
                for scene in scenes_needing_scripts:
                    scene_script_data = script_results["scripts"].get(str(scene.scene_number))
                    if scene_script_data:
                        voice_guidance = scene_script_data.get("voice_guidance", {})
                        warning_note = next(
                            (w.get("warning") for w in warning_voice_scenes if w.get("scene_number") == scene.scene_number),
                            None,
                        )
                        # 将脚本结果写入项目级脚本槽
                        entry = {}
                        try:
                            existing_scripts = read_shared_fact(workflow_state_id, "project.scene_scripts", {}, service=self.short_term_service) or {}
                            entry = dict(existing_scripts.get(str(scene.scene_number), {}))
                            entry.update({
                                "script_text": scene_script_data.get("script_text", ""),
                                "voice_over_text": scene_script_data.get("voice_over_text", getattr(scene, "voice_over_text", "")),
                                "narrative_description": scene_script_data.get("narrative_description", scene.narrative_description),
                                "background_music_style": scene_script_data.get("background_music_style", ""),
                                "sound_effects": scene_script_data.get("sound_effects", []),
                                "pacing_and_timing": {
                                    "pace_tag": voice_guidance.get("pace_tag"),
                                    "target_char_count": voice_guidance.get("target_char_count"),
                                    "should_narrate": voice_guidance.get("should_narrate"),
                                },
                                "motion_beats": scene_script_data.get("motion_beats", []),
                            })
                            merged = dict(existing_scripts)
                            merged[str(scene.scene_number)] = entry
                            write_shared_fact(workflow_state_id, "project.scene_scripts", merged, service=self.short_term_service)
                        except Exception as err:
                            raise AgentError(
                                f"Failed to persist scene_scripts for scene {scene.scene_number}: {err}"
                            ) from err
                        try:
                            if isinstance(concept_plan, dict):
                                for sc_def in concept_plan.get('scenes', []) or []:
                                    if sc_def.get('scene_number') == scene.scene_number:
                                        sc_def['motion_beats'] = scene_script_data.get("motion_beats", [])
                                        break
                        except Exception:
                            pass
                        generated_count += 1
                        result_entry = {
                            "scene_number": scene.scene_number,
                            "success": True,
                            "prompt_text": scene_script_data.get("script_text", "")[:120] or "script_generated",
                        }
                        if warning_note:
                            result_entry["warning"] = warning_note
                        generation_results.append(result_entry)
                    else:
                        failure_reason = next(
                            (f.get("reason") for f in hard_failed_voice_scenes if f.get("scene_number") == scene.scene_number),
                            "script_generation_failed_or_empty",
                        )
                        generation_results.append({
                            "scene_number": scene.scene_number,
                            "success": False,
                            "error": failure_reason
                        })
            else:
                # 工具层未返回结构化脚本映射时，按尝试的场景全部视为失败
                for scene in scenes_needing_scripts:
                    generation_results.append({
                        "scene_number": scene.scene_number,
                        "success": False,
                        "error": "no_scripts_map"
                    })

            # 将连续性分析结果写回 MAS WM 场景视图（用于 Image/Video 连续性处理）
            try:
                decisions = (continuity_analysis or {}).get("continuity_decisions", {}) if isinstance(continuity_analysis, dict) else {}
                if decisions:
                    scene_view = load_scene_overview(str(workflow_state_id), service=self.short_term_service)
                    scenes_payload = scene_view.get("scenes") if isinstance(scene_view, dict) else []
                    indexed: Dict[int, Dict[str, Any]] = {}
                    for entry in scenes_payload or []:
                        if not isinstance(entry, dict):
                            continue
                        try:
                            sn = int(entry.get("scene_number"))
                        except Exception:
                            continue
                        indexed[sn] = dict(entry)
                    for sn, entry in indexed.items():
                        d = decisions.get(str(sn))
                        if not isinstance(d, dict):
                            continue
                        strategy = d.get("strategy", "new")
                        depends = (sn - 1) if (strategy == "continue_from_previous" and sn > 1) else None
                        entry["depends_on_scene"] = depends
                        if d.get("motion_beats") is not None:
                            entry["motion_beats"] = d.get("motion_beats") or []
                        if d.get("reason"):
                            entry["continuity_reason"] = d.get("reason")
                    updated_scenes = [indexed[k] for k in sorted(indexed.keys())]
                    updated_view = {
                        "scenes": updated_scenes,
                        "completed_scene_numbers": scene_view.get("completed_scene_numbers", []) if isinstance(scene_view, dict) else [],
                        "failed_scene_numbers": scene_view.get("failed_scene_numbers", []) if isinstance(scene_view, dict) else [],
                    }
                    write_shared_fact(workflow_state_id, "scene_overview", updated_view, service=self.short_term_service)
                    self.logger.info("✅ 连续性决策已写回 MAS WM 场景概览")
            except Exception as ce:
                self.logger.warning(f"连续性结果写回失败：{ce}")

            # 角色一致性：基于概念角色库与场景文本，填充每个场景的 characters_present 与 character_descriptions
            try:
                # 提取角色库（来自概念规划）
                # 通用化：优先使用 canonical_name/display_name/aliases，其次回退 identity 解析
                char_lib = {}
                try:
                    chars = ((concept_plan or {}).get('content_elements') or {}).get('characters') or []
                except Exception:
                    chars = []
                import re
                for c in chars:
                    # 1) 高层特征优先（抽象且通用）
                    traits = []
                    try:
                        traits = [str(t).strip() for t in (c.get('abstract_traits') or []) if str(t).strip()]
                    except Exception:
                        traits = []
                    # 2) 视觉标识（可选）
                    vis_ids = []
                    try:
                        vis_ids = [str(t).strip() for t in (c.get('visual_identity') or []) if str(t).strip()]
                    except Exception:
                        vis_ids = []
                    # 3) 回退：appearance（字符串或对象）/ background / role
                    appearance = None
                    app_raw = c.get('appearance')
                    if isinstance(app_raw, dict):
                        # 尝试提取少量抽象要点（而非细节清单）
                        try:
                            abstract_bits = [app_raw.get('physique'), app_raw.get('distinguishing_marks')]
                            palette = app_raw.get('color_palette') or {}
                            if palette.get('primary'):
                                abstract_bits.append(f"主色:{palette.get('primary')}")
                            appearance = '；'.join([str(p) for p in abstract_bits if p])
                        except Exception:
                            appearance = None
                    if not appearance and app_raw is not None:
                        try:
                            appearance = str(app_raw).strip()
                        except Exception:
                            appearance = None
                    background = (c.get('background') or '').strip()
                    role_fn = (c.get('role') or '').strip()

                    # 4) 生成简明描述（限制长度，保持抽象）
                    parts = []
                    if traits:
                        parts.append('，'.join(traits[:5]))
                    if vis_ids:
                        parts.append('，'.join(vis_ids[:3]))
                    if appearance:
                        parts.append(appearance)
                    if background and (not parts):
                        parts.append(background)
                    if role_fn and (not parts):
                        parts.append(role_fn)
                    desc = '；'.join([p for p in parts if p]).strip()
                    if len(desc) > 120:
                        desc = desc[:120]

                    # 名称集合：canonical/display/aliases/identity短名（兼容历史）
                    canonical = (c.get('canonical_name') or '').strip()
                    display = (c.get('display_name') or '').strip()
                    aliases = [str(a).strip() for a in (c.get('aliases') or []) if str(a).strip()]
                    identity = (c.get('identity') or '').strip()
                    id_short = ''
                    if identity:
                        m = re.search(r'“([^”]+)”', identity) or re.search(r'"([^"]+)"', identity)
                        id_short = m.group(1) if m else (identity[-2:] if len(identity) >= 2 else identity)
                    names = [canonical, display, id_short] + aliases
                    names = [n for n in names if n]
                    for n in names:
                        if n and desc:
                            char_lib[n] = desc

                # 基于脚本文本标注每个场景
                scene_view = load_scene_overview(str(workflow_state_id), service=self.short_term_service)
                for scene_entry in (scene_view.get("scenes") or []) if isinstance(scene_view, dict) else []:
                    text = (scene_entry.get('script_text', '') or '') + ' ' + (scene_entry.get('narrative_description', '') or '')
                    present = []
                    descs = []
                    for name, desc in char_lib.items():
                        if not name:
                            continue
                        # 名称包含或近似匹配（前缀/后缀），提升跨语言/缩写鲁棒性
                        if (name in text) or text.startswith(name) or text.endswith(name):
                            present.append(name)
                            descs.append(f"{name}：{desc}")
                    if present:
                        try:
                            sn = int(scene_entry.get('scene_number', 0))
                        except Exception as parse_err:
                            raise AgentError("Failed to parse scene_number during character consistency sync") from parse_err
                        if sn:
                            existing_scripts = read_shared_fact(workflow_state_id, "project.scene_scripts", {}, service=self.short_term_service) or {}
                            entry = dict(existing_scripts.get(str(sn), {}))
                            entry.update({"characters_present": present, "character_descriptions": descs})
                            merged = dict(existing_scripts)
                            merged[str(sn)] = entry
                            write_shared_fact(workflow_state_id, "project.scene_scripts", merged, service=self.short_term_service)
                self.logger.info("✅ 角色一致性标注已写回 scene_scripts")
            except Exception as ce:
                self.logger.error(f"角色一致性标注失败: {ce}")
                raise AgentError("Shared WM update failed during scene character annotation") from ce

            self.logger.info(f"批量脚本生成完成: {generated_count}/{len(scenes_needing_scripts)}")
            
            # role consistency memory sync (concept -> WF.scene)
            try:
                cp = concept_plan or {}
                scene_defs = (cp.get('scenes') or [])
                if scene_defs:
                    # build maps from global characters: identity->appearance and short->appearance
                    name2appearance = {}
                    short2appearance = {}
                    for rc in ((cp.get('content_elements') or {}).get('characters') or []):
                        ident = str((rc.get('identity') or '')).strip()
                        app = str((rc.get('appearance') or '')).strip()
                        if ident:
                            name2appearance[ident] = app or ident
                            # derive a short display name from quoted alias or tail segments
                            try:
                                import re
                                m = re.search(r'“([^”]+)”', ident) or re.search(r'"([^"]+)"', ident)
                                short = m.group(1) if m else ''
                                if not short:
                                    short = ident[-2:] if len(ident) >= 2 else ident
                                if short:
                                    short2appearance[short] = app or ident
                            except Exception:
                                pass
                    # 额外构建名称与特征描述映射：
                    # - 将场景出现名单标准化为本地化展示名（display_name优先）
                    # - 为每个角色准备“简明特征摘要”，用于下游生成作为角色设定
                    canonical_to_display = {}
                    alias_to_display = {}
                    char_desc_map = {}
                    for rc in ((cp.get('content_elements') or {}).get('characters') or []):
                        cano = str((rc.get('canonical_name') or '')).strip()
                        disp = str((rc.get('display_name') or '')).strip()
                        aliases = [str(a).strip() for a in (rc.get('aliases') or []) if str(a).strip()]
                        # 生成简明特征摘要（不依赖任何供应商）：
                        parts = []
                        # 1) 原型/身份与物种/品种（若提供）
                        arche = str((rc.get('archetype_or_identity') or rc.get('identity') or '')).strip()
                        if (not arche) and aliases:
                            # 作为弱回退：若无结构化原型字段，取首个别名作为身份/原型线索
                            arche = aliases[0]
                        species = str((rc.get('species_or_breed') or '')).strip()
                        if arche:
                            parts.append(f"原型：{arche}")
                        if species:
                            parts.append(f"物种：{species}")
                        try:
                            traits = [str(t).strip() for t in (rc.get('abstract_traits') or []) if str(t).strip()]
                        except Exception:
                            traits = []
                        try:
                            vis = [str(v).strip() for v in (rc.get('visual_identity') or []) if str(v).strip()]
                        except Exception:
                            vis = []
                        try:
                            sig = [str(v).strip() for v in (rc.get('signature_outfit_or_props') or []) if str(v).strip()]
                        except Exception:
                            sig = []
                        role_fn = str((rc.get('role') or '')).strip()
                        if traits:
                            parts.append('，'.join(traits[:5]))
                        if vis:
                            parts.append('，'.join(vis[:3]))
                        if sig:
                            parts.append('，'.join(sig[:2]))
                        if role_fn:
                            parts.append(role_fn)
                        brief = '；'.join([p for p in parts if p]).strip()
                        # 名称映射
                        if cano and disp:
                            canonical_to_display[cano] = disp
                        for al in aliases:
                            if disp:
                                alias_to_display[al] = disp
                        # 描述映射（多键指向同一摘要）
                        keys = set([k for k in [cano, disp] + aliases if k])
                        for k in keys:
                            if brief:
                                char_desc_map[k] = brief
                    # write per-scene presence into WF（名称优先归一到 display_name）
                    for sdef in scene_defs:
                        try:
                            sn = int(sdef.get('scene_number')) if sdef.get('scene_number') is not None else None
                        except Exception:
                            sn = None
                        if sn is None:
                            continue
                        present_raw = (((sdef.get('content_elements') or {}).get('characters_present')) or [])
                        # 将出现名单优先映射为 display_name（若存在），否则保持原样
                        present = []
                        for nm in present_raw:
                            nm_str = str(nm).strip()
                            if not nm_str:
                                continue
                            mapped = canonical_to_display.get(nm_str) or alias_to_display.get(nm_str)
                            present.append(mapped or nm_str)
                        # 构建角色特征描述：使用 display 名 + 摘要（若有）
                        descs = []
                        for nm in present:
                            nm_str = str(nm).strip()
                            if not nm_str:
                                continue
                            brief = char_desc_map.get(nm_str) or ''
                            descs.append(f"{nm_str}：{brief}" if brief else nm_str)
                        # sn 已在上方解析得到，避免引用未定义变量
                        try:
                            sn = int(sn)
                        except Exception:
                            continue
                        # 将角色提示写到 facts.scene_scripts 下以场景为键
                        existing_scripts = read_shared_fact(workflow_state_id, "project.scene_scripts", {}, service=self.short_term_service) or {}
                        entry = dict(existing_scripts.get(str(sn), {}))
                        entry.update({"characters_present": present, "character_descriptions": descs})
                        merged = dict(existing_scripts)
                        merged[str(sn)] = entry
                        write_shared_fact(workflow_state_id, "project.scene_scripts", merged, service=self.short_term_service)
                self.logger.info("✅ 角色记忆已写回（concept→WF.scene）")
            except Exception as ce:
                self.logger.error(f"角色记忆写回失败: {ce}")
                raise AgentError("Shared WM update failed during concept-to-scene character sync") from ce

            # 角色分析工具（结构化）：不改变 Agent 自主性，仅调用工具并将结果写回 WF
            try:
                # 组装场景文本
                scene_payload: List[Dict[str, Any]] = []
                scene_view = load_scene_overview(str(workflow_state_id), service=self.short_term_service)
                for scene_entry in (scene_view.get("scenes") or []) if isinstance(scene_view, dict) else []:
                    scene_payload.append({
                        "scene_number": scene_entry.get('scene_number'),
                        "title": scene_entry.get('title', ''),
                        "description": scene_entry.get('description', '') or scene_entry.get('visual_description', ''),
                        "narrative_description": scene_entry.get('narrative_description', ''),
                        "script_text": scene_entry.get('script_text', '')
                    })
                # 抽取通用风格/场景线索
                style_hint = ""
                try:
                    # 1) 项目上下文/Shared WM中的风格偏好（若存在）
                    if isinstance(project_context, dict):
                        sw = (
                            project_context.get('style_preference')
                            or project_context.get('style')
                            or project_context.get('video_style')
                            or ''
                        )
                        if isinstance(sw, str) and sw.strip():
                            style_hint = sw.strip()
                    if not style_hint:
                        sw = read_shared_fact(str(workflow_state_id), "project.style_preference", "", service=self.short_term_service)
                        if isinstance(sw, str) and sw.strip():
                            style_hint = sw.strip()
                        elif isinstance(sw, dict):
                            raw_hint = sw.get("value") if isinstance(sw.get("value"), str) else None
                            if raw_hint and raw_hint.strip():
                                style_hint = raw_hint.strip()
                    # 2) 概念计划智能风格设计摘要（作为补充）
                    if not style_hint and isinstance(concept_plan, dict):
                        isd = (concept_plan or {}).get('intelligent_style_design') or {}
                        if isinstance(isd, dict) and isd:
                            # 尝试拼接关键词/主风格
                            primary = (isd.get('primary_style') or isd.get('style') or '')
                            keywords = isd.get('keywords') or isd.get('style_keywords') or []
                            if isinstance(primary, str) and primary.strip():
                                style_hint = primary.strip()
                                if isinstance(keywords, list) and keywords:
                                    try:
                                        style_hint = f"{style_hint} | " + ", ".join([str(k) for k in keywords[:5]])
                                    except Exception:
                                        pass
                except Exception:
                    pass
                scenario_hint = ""
                try:
                    if isinstance(concept_plan, dict):
                        overview = (concept_plan.get('overview') or '').strip()
                        setting = ''
                        try:
                            setting = (concept_plan.get('setting') or concept_plan.get('world_setting') or '').strip()
                        except Exception:
                            setting = ''
                        genre = ''
                        try:
                            g = (concept_plan.get('genre_and_theme') or {}).get('genre')
                            genre = g.strip() if isinstance(g, str) else ''
                        except Exception:
                            genre = ''
                        mood = ''
                        try:
                            mood = (concept_plan.get('mood_and_tone') or '').strip()
                        except Exception:
                            mood = ''
                        candidates = [overview, setting, genre, mood]
                        scenario_hint = ' | '.join([c for c in candidates if c])[:240]
                except Exception:
                    pass

                role_call = {
                    "function": {
                        "name": "role_analysis_tool.analyze_roles_and_scenes",
                        "arguments": {
                            "scenes": scene_payload,
                            "concept_plan": concept_plan or {},
                            "target_style": style_hint,
                            "scenario_hint": scenario_hint
                        }
                    }
                }
                role_exec = await self.execute_tool_calls([role_call])
                payload = extract_tool_payload(role_exec[0].get('result')) if (role_exec and isinstance(role_exec[0], dict)) else None
                if not isinstance(payload, dict):
                    self.logger.warning(
                        "角色分析返回结构异常（跳过写回）：type=%s preview=%s",
                        type(payload).__name__,
                        (str(payload)[:200].replace('\n',' ') if payload is not None else 'None')
                    )
                    per_scene = {}
                    global_roles = []
                else:
                    per_scene = payload.get('per_scene_roles') or {}
                    global_roles = payload.get('roles') or []
                # 合并写回各场景（不覆盖已有字段，仅对角色字段做并集）
                existing_scripts = read_shared_fact(
                    workflow_state_id,
                    "project.scene_scripts",
                    {},
                    service=self.short_term_service,
                ) or {}
                merged_scripts = dict(existing_scripts) if isinstance(existing_scripts, dict) else {}
                for sc in (scene_payload or []):
                    if not isinstance(sc, dict):
                        continue
                    try:
                        sn = int(sc.get("scene_number") or 0)
                    except Exception:
                        sn = 0
                    if not sn:
                        continue
                    key = str(sn)
                    scene_roles = per_scene.get(key) or []
                    names: List[str] = []
                    descs: List[str] = []
                    for item in scene_roles:
                        if isinstance(item, str):
                            if item.strip():
                                names.append(item.strip())
                        elif isinstance(item, dict):
                            nm = item.get('display_name') or item.get('name')
                            if isinstance(nm, str) and nm.strip():
                                names.append(nm.strip())
                            parts = []
                            # 优先使用 visual_description 作为合成描述
                            vis = item.get('visual_description')
                            if isinstance(vis, str) and vis.strip():
                                parts.append(vis.strip())
                            for k in ("archetype_or_identity", "species_or_breed"):
                                v = item.get(k)
                                if isinstance(v, str) and v.strip():
                                    parts.append(v.strip())
                            sig = item.get('signature_outfit_or_props') or []
                            if isinstance(sig, list) and sig:
                                parts.append("/".join([str(x) for x in sig[:2]]))
                            traits = item.get('key_traits') or []
                            if isinstance(traits, list) and traits:
                                parts.append("/".join([str(x) for x in traits[:3]]))
                            if parts:
                                descs.append("；".join(parts))
                    if not (names or descs):
                        continue
                    entry = dict(merged_scripts.get(key, {})) if isinstance(merged_scripts.get(key), dict) else {}
                    merged_names = list(set((entry.get('characters_present', []) or []) + names))
                    merged_descs = list(set((entry.get('character_descriptions', []) or []) + descs))
                    entry.update({"characters_present": merged_names, "character_descriptions": merged_descs})
                    merged_scripts[key] = entry
                if merged_scripts != existing_scripts:
                    write_shared_fact(
                        workflow_state_id,
                        "project.scene_scripts",
                        merged_scripts,
                        service=self.short_term_service,
                    )
                self.logger.info("✅ 角色分析结果已写回 scene_scripts slot")

                # 将角色一致性快照作为 EPISODIC 记忆写入（无开关，作为系统保障；若记忆不可用则优雅降级）
                try:
                    wf_id = str(workflow_state_id or "")
                    if wf_id:
                        from ..services.memory_writer import MemoryWriter
                        from ..models.task import TaskType
                        writer = MemoryWriter(self._memory_services)
                        await writer.write(
                            TaskType.SCRIPT_WRITING,
                            workflow_id=str(wf_id),
                            scene_number=None,
                            output={
                                "roles": global_roles,
                                "per_scene_roles": per_scene
                            }
                        )
                        self.logger.info("🧠 角色一致性快照已存入EPISODIC记忆（roles_snapshot）")
                except Exception as _mw:
                    self.logger.warning(f"角色一致性快照写入记忆失败（跳过）：{_mw}")
            except Exception as re:
                # 仅在错误路径输出 traceback，便于定位根因（例如 NameError: view 未定义）
                self.logger.exception("角色分析执行/写回失败")
                raise AgentError("Role analysis failed to execute or persist results") from re

            overall_success = len(hard_failed_voice_scenes) == 0
            if hard_failed_voice_scenes:
                self.logger.error(
                    "脚本生成存在未通过的旁白场景: %s",
                    [f.get("scene_number") for f in hard_failed_voice_scenes],
                )
            if warning_voice_scenes:
                self.logger.warning(
                    "旁白字数与规划存在偏差: %s",
                    [w.get("scene_number") for w in warning_voice_scenes],
                )

            return {
                "success": overall_success,
                "message": f"批量生成{generated_count}个场景脚本",
                "scenes_generated": generated_count,
                "script_results": script_results,
                "continuity_analysis": continuity_analysis,
                "generation_results": generation_results,
                "workflow_state_updated": generated_count > 0,
                "total_scenes": len(scenes_needing_scripts),
                "failed_voice_scenes": hard_failed_voice_scenes,
                "voice_over_warnings": warning_voice_scenes,
            }
            
        except AgentError:
            # Fail-fast：交由 BaseAgent.execute 统一上抛，保证 orchestrator 可感知失败并停止工作流
            raise
        except Exception as e:
            self.logger.error(f"批量脚本生成失败: {str(e)}")
            raise AgentError(f"批量脚本生成失败: {e}") from e

    def _sanitize_motion_beats(self, beats: Any, scene_duration: float) -> List[Dict[str, Any]]:
        if not isinstance(beats, list):
            return []

        def _coerce_seconds(value: Any) -> Optional[float]:
            try:
                if value is None:
                    return None
                if isinstance(value, (int, float)):
                    return float(value)
                text = str(value).strip().lower()
                if not text:
                    return None
                text = text.replace('秒', '').replace('s', '').replace('sec', '')
                text = text.replace('：', ':').replace('，', ',')
                if '-' in text and text.count('-') == 1 and text.replace('-', '').replace('.', '').isdigit():
                    parts = text.split('-')
                    return float(parts[0])
                return float(text)
            except Exception:
                return None

        sanitized: List[Dict[str, Any]] = []
        total_duration = float(scene_duration or 0.0)
        fallback_span = total_duration / max(len(beats), 1) if total_duration > 0 else 0.0
        cursor = 0.0

        for idx, raw in enumerate(beats):
            if not isinstance(raw, dict):
                continue
            start = _coerce_seconds(
                raw.get('start')
                or raw.get('start_seconds')
                or raw.get('begin')
                or raw.get('timecode_start')
            )
            end = _coerce_seconds(
                raw.get('end')
                or raw.get('end_seconds')
                or raw.get('stop')
                or raw.get('timecode_end')
            )
            duration_hint = _coerce_seconds(raw.get('duration'))

            if start is None:
                start = cursor
            if duration_hint is not None and end is None:
                end = start + max(duration_hint, 0.0)
            if end is None:
                end = start + fallback_span
            if total_duration > 0:
                start = max(0.0, min(start, total_duration))
                end = max(start, min(end, total_duration))
            if end <= start and total_duration > 0:
                end = min(total_duration, start + max(fallback_span, 0.5))

            beat_summary = str(raw.get('description') or raw.get('beat_summary') or raw.get('action') or '').strip()
            visual_focus = str(raw.get('visual_focus') or raw.get('focus') or raw.get('subject') or '').strip()

            sanitized.append({
                'index': idx + 1,
                'start': round(start, 3),
                'end': round(end, 3),
                'duration': round(max(0.0, end - start), 3),
                'beat_summary': beat_summary,
                'visual_focus': visual_focus,
            })
            cursor = end
            if len(sanitized) >= 6:
                break

        return sanitized

    def _validate_voice_line(
        self,
        scene_number: int,
        voice_line: Optional[str],
        guidance: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        should_narrate = bool(guidance.get("should_narrate", True))
        if not should_narrate:
            return True, None

        text = (voice_line or "").strip()
        if not text:
            raise AgentError(f"Scene {scene_number} voice_over_text 缺失，脚本生成失败")

        target_char_count = guidance.get("target_char_count")
        if target_char_count is None:
            raise AgentError(f"Scene {scene_number} voice plan 缺少 target_char_count")
        try:
            target_char_count = int(target_char_count)
        except (TypeError, ValueError):
            raise AgentError(f"Scene {scene_number} voice plan target_char_count 非法")

        tolerance = max(6, int(round(target_char_count * 0.2)))
        diff = abs(len(text) - target_char_count)
        if diff > tolerance:
            return False, f"实际 {len(text)} / 目标 {target_char_count}"

        return True, None

    def _estimate_scene_count(self, input_data: Dict[str, Any]) -> int:
        """估算场景数量用于动态超时"""
        try:
            workflow_state_id = input_data.get("workflow_state_id")
            if workflow_state_id:
                overview = load_scene_overview(str(workflow_state_id), service=self.short_term_service)
                scenes = overview.get("scenes") if isinstance(overview, dict) else []
                if scenes:
                    return len(scenes)
            return 6  # 默认估算
        except Exception:
            return 6

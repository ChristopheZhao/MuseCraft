"""
Script Writer Agent - 简化版批量脚本生成
移除复杂的ReAct接口，直接实现批量处理
"""
import json
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene
from ..core.workflow_state import WorkflowState, SceneData
from .tools.tool_registry import get_tool_registry
from .tools.base_tool import ToolInput as TI


class ScriptWriterAgent(BaseAgent):
    """
    Script Writer Agent - 简化版批量脚本生成
    专注于场景脚本、叙事结构和连续性分析，但使用BaseAgent接口
    """
    
    def __init__(self, llms=None):
        super().__init__(
            agent_type=AgentType.SCRIPT_WRITER,
            agent_name="script_writer",
            timeout_seconds=600,
            max_retries=2,
            tools=[
                "scene_continuity_analysis_tool",
                "script_generation_tool", 
                "narrative_structure_generation_tool"
            ],
            llms=llms
        )
        
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
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

            # 获取workflow_state
            workflow_state_id = input_data.get("workflow_state_id")
            from ..core.workflow_state import workflow_manager
            workflow_state = workflow_manager.get_workflow(workflow_state_id) if workflow_state_id else None

            if not workflow_state:
                return {
                    "success": False,
                    "error": "No workflow state available",
                    "workflow_state_updated": False,
                    "results": []
                }

            # 获取场景和概念规划
            scenes = getattr(workflow_state, 'scenes', [])
            concept_plan = getattr(workflow_state, 'concept_plan', {})

            if not scenes:
                return {
                    "success": False,
                    "error": "No scenes available for script generation",
                    "workflow_state_updated": False,
                    "results": []
                }

            # 批量生成脚本
            return await self._batch_generate_scripts(scenes, concept_plan, workflow_state, task)

        except Exception as e:
            self.logger.error(f"ScriptWriter execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "workflow_state_updated": False,
                "fallback_applied": True,
                "results": []
            }

    async def _batch_generate_scripts(
        self, 
        scenes: List[SceneData], 
        concept_plan: Dict[str, Any],
        workflow_state: WorkflowState,
        task: Task
    ) -> Dict[str, Any]:
        """批量生成场景脚本"""
        
        voice_plan = getattr(workflow_state, "voice_plan", {}) or {}
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

        # 筛选需要脚本的场景
        scenes_needing_scripts = [
            scene for scene in scenes 
            if not scene.script_text or len(scene.script_text.strip()) < 50
        ]
        
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
            batch_scenes = [
                {
                    "scene_number": scene.scene_number,
                    "title": scene.title,
                    "duration": scene.duration,
                    "narrative_description": scene.narrative_description
                } for scene in scenes_needing_scripts
            ]
            
            # 逐场景生成脚本（使用 script_generation 工具的 generate_scene_script 动作）
            scripts_map: Dict[str, Any] = {}
            hard_failed_voice_scenes: List[Dict[str, Any]] = []
            warning_voice_scenes: List[Dict[str, Any]] = []
            intelligent_style = concept_plan.get('intelligent_style_design', {})
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

                    tool_params = {
                        "scene_data": {
                            "scene_number": scene.scene_number,
                            "visual_description": scene.visual_description,
                            "narrative_description": scene.narrative_description,
                            "duration": scene.duration,
                        },
                        "intelligent_style_design": intelligent_style,
                        "context": {
                            "previous_scene": "",
                            "narrative_arc": concept_plan.get('genre_and_theme', {}).get('theme', '')
                        },
                        # 让工具按配置使用模型和token预算，替代内部默认值
                        "model": script_model,
                        "max_tokens": max_tokens_budget,
                    }
                    tool_params["voice_guidance"] = {
                        "should_narrate": should_narrate,
                        "pace_tag": pace_tag,
                        "target_char_count": target_char_count,
                        "key_points": guidance.get("key_points", []),
                        "emotion": guidance.get("emotion", ""),
                        "objective": guidance.get("objective", ""),
                    }
                    one = await self.use_tool(
                        "script_generation",
                        "generate_scene_script",
                        tool_params
                    )
                    payload = getattr(one, 'result', one)
                    if isinstance(payload, dict):
                        if not payload.get("success", True):
                            raise AgentError(
                                f"场景 {scene.scene_number} 脚本生成失败: {payload.get('error', 'unknown error')}"
                            )
                        script_section = payload.get("script") if isinstance(payload.get("script"), dict) else {}
                        voice_line = (
                            payload.get("voice_over_text")
                            or payload.get("voice_over")
                            or script_section.get("voice_over")
                            or script_section.get("voiceover")
                        )
                        if isinstance(voice_line, list):
                            voice_line = " ".join(str(v).strip() for v in voice_line if str(v).strip())
                        elif voice_line is not None:
                            voice_line = str(voice_line).strip()

                        is_valid_voice, warning_msg = self._validate_voice_line(
                            scene.scene_number, voice_line, tool_params["voice_guidance"]
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
                            "script_text": payload.get("script_text", payload.get("content", "") or script_section.get("script_text", "")),
                            "narrative_description": payload.get("narrative_description", scene.narrative_description),
                            "background_music_style": payload.get("background_music_style", ""),
                            "sound_effects": payload.get("sound_effects", []),
                            "voice_over_text": voice_line or "",
                            "voice_guidance": tool_params["voice_guidance"],
                        }
                except AgentError as ae:
                    hard_failed_voice_scenes.append({
                        "scene_number": scene.scene_number,
                        "reason": str(ae),
                    })
                    self.logger.warning(f"场景 {scene.scene_number} 脚本生成失败: {ae}")
                except Exception as se:
                    hard_failed_voice_scenes.append({
                        "scene_number": scene.scene_number,
                        "reason": str(se),
                    })
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
                cont_res = await self.use_tool(
                    "scene_continuity_analysis_tool",
                    "analyze_all_scenes_continuity",
                    cont_params
                )
                continuity_analysis = getattr(cont_res, 'result', cont_res)
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
                        workflow_state.update_scene(
                            scene.scene_number,
                            script_text=scene_script_data.get("script_text", ""),
                            voice_over_text=scene_script_data.get("voice_over_text", getattr(scene, "voice_over_text", "")),
                            narrative_description=scene_script_data.get("narrative_description", scene.narrative_description),
                            background_music_style=scene_script_data.get("background_music_style", ""),
                            sound_effects=scene_script_data.get("sound_effects", []),
                            pacing_and_timing={
                                "pace_tag": voice_guidance.get("pace_tag"),
                                "target_char_count": voice_guidance.get("target_char_count"),
                                "should_narrate": voice_guidance.get("should_narrate"),
                            },
                        )
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

            # 将连续性分析结果写回到 WorkflowState.scenes（用于 Image/Video 连续性处理）
            try:
                decisions = (continuity_analysis or {}).get("continuity_decisions", {}) if isinstance(continuity_analysis, dict) else {}
                if decisions:
                    # 遍历所有场景，依据决策落地字段
                    for sc in getattr(workflow_state, 'scenes', []) or []:
                        sn = getattr(sc, 'scene_number', None)
                        if not sn:
                            continue
                        key = str(sn)
                        d = decisions.get(key)
                        if not isinstance(d, dict):
                            # 对缺失决策的场景，保持现状，不强行覆盖
                            continue
                        strategy = d.get("strategy", "new")
                        reason = d.get("reason", "")
                        try:
                            confidence = float(d.get("confidence", 0.8))
                        except Exception:
                            confidence = 0.8

                        if strategy == "continue_from_previous" and sn > 1:
                            depends = sn - 1
                            workflow_state.update_scene(
                                sn,
                                depends_on_scene=depends,
                                requires_continuity_from=depends,
                                continuity_reason=reason,
                                continuity_confidence=confidence,
                                image_generation_strategy="continue_from_previous",
                            )
                        else:
                            # 标记为独立生成；清理依赖
                            workflow_state.update_scene(
                                sn,
                                depends_on_scene=None,
                                requires_continuity_from=None,
                                continuity_reason=reason,
                                continuity_confidence=confidence,
                                image_generation_strategy="new",
                            )
                    self.logger.info("✅ 连续性决策已写回 WorkflowState.scenes")
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
                for sc in getattr(workflow_state, 'scenes', []) or []:
                    try:
                        text = (getattr(sc, 'script_text', '') or '') + ' ' + (getattr(sc, 'narrative_description', '') or '')
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
                            workflow_state.update_scene(sc.scene_number, characters_present=present, character_descriptions=descs)
                    except Exception:
                        continue
                self.logger.info("✅ 角色一致性标注已写回 WorkflowState.scenes")
            except Exception as ce:
                self.logger.warning(f"角色一致性标注失败（跳过）：{ce}")

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
                        workflow_state.update_scene(sn, characters_present=present, character_descriptions=descs)
                self.logger.info("✅ 角色记忆已写回（concept→WF.scene）")
            except Exception as ce:
                self.logger.warning(f"角色记忆写回失败（跳过）：{ce}")

            # 角色分析工具（结构化）：不改变 Agent 自主性，仅调用工具并将结果写回 WF
            try:
                registry = get_tool_registry()
                role_tool = registry.get_tool("role_analysis_tool")
                # 组装场景文本
                scene_payload: List[Dict[str, Any]] = []
                for sc in getattr(workflow_state, 'scenes', []) or []:
                    scene_payload.append({
                        "scene_number": getattr(sc, 'scene_number', None),
                        "title": getattr(sc, 'title', ''),
                        "description": getattr(sc, 'description', '') or getattr(sc, 'visual_description', ''),
                        "narrative_description": getattr(sc, 'narrative_description', ''),
                        "script_text": getattr(sc, 'script_text', '')
                    })
                # 抽取通用风格/场景线索，参数化传入，保持工具通用性
                style_hint = ""
                try:
                    # workflow_state 风格偏好
                    sw = getattr(workflow_state, 'style_preference', '') or ''
                    if isinstance(sw, str) and sw.strip():
                        style_hint = sw.strip()
                    # 概念计划智能风格设计摘要
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

                res = await role_tool.execute(TI(action="analyze_roles_and_scenes", parameters={
                    "scenes": scene_payload,
                    "concept_plan": concept_plan or {},
                    "target_style": style_hint,
                    "scenario_hint": scenario_hint
                }))
                payload = getattr(res, 'result', res)
                per_scene = (payload or {}).get('per_scene_roles') or {}
                global_roles = (payload or {}).get('roles') or []
                # 合并写回各场景（不覆盖已有，做集合并集）
                for sc in getattr(workflow_state, 'scenes', []) or []:
                    sn = getattr(sc, 'scene_number', None)
                    if sn is None:
                        continue
                    key = str(sn)
                    scene_roles = per_scene.get(key) or []
                    names: List[str] = []
                    descs: List[str] = []
                    for item in scene_roles:
                        if isinstance(item, str):
                            names.append(item)
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
                    if names or descs:
                        merged_names = list(set((getattr(sc, 'characters_present', []) or []) + names))
                        merged_descs = list(set((getattr(sc, 'character_descriptions', []) or []) + descs))
                        workflow_state.update_scene(sn, characters_present=merged_names, character_descriptions=merged_descs)
                self.logger.info("✅ 角色分析结果已写回 WorkflowState.scenes")

                # 将角色一致性快照作为 EPISODIC 记忆写入（无开关，作为系统保障；若记忆不可用则优雅降级）
                try:
                    # Prefer workflow_state.task_id; fallback to task.task_id if available
                    wf_id = (
                        getattr(workflow_state, 'task_id', None)
                        or (str(getattr(task, 'task_id', '')) if task else "")
                        or ""
                    )
                    if wf_id:
                        from ..services.memory_writer import memory_writer
                        from ..models.task import TaskType
                        await memory_writer.write(
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
                self.logger.warning(f"角色分析执行/写回失败（跳过，不阻断）：{re}")

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
            
        except Exception as e:
            self.logger.error(f"批量脚本生成失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "scenes_generated": 0,
                "workflow_state_updated": False
            }

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
                from ..core.workflow_state import workflow_manager
                ws = workflow_manager.get_workflow(workflow_state_id)
                if ws and getattr(ws, 'scenes', None):
                    return len(ws.scenes)
            return 6  # 默认估算
        except:
            return 6

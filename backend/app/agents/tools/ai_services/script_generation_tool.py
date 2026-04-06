"""
Script Generation Tool - 封装脚本生成业务逻辑
"""

import asyncio
import json
from typing import Dict, Any, List, Optional

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolError, ToolValidationError
from ....services.script_review_contract import format_script_review_guidance


class ScriptGenerationTool(AsyncTool):
    """
    脚本生成工具 - 封装脚本生成业务逻辑
    
    提供脚本生成相关的业务功能（供应商无关，通过统一服务/注册器调用）
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="script_generation",
            version="1.0.0",
            description="使用LLM生成视频脚本，包括场景脚本、整体叙事结构等",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["脚本生成", "叙事分析", "LLM"],
            capabilities=["场景脚本生成", "叙事结构分析", "对话优化", "脚本连续性检查"],
            dependencies=[]
        )
    
    def __init__(self, **kwargs):
        # 从kwargs中移除metadata，使用classmethod获取
        kwargs.pop('metadata', None)
        metadata = self.get_metadata()
        super().__init__(metadata=metadata, **kwargs)
        # 供应商无关，运行时选择provider
    
    def get_available_actions(self) -> List[str]:
        return [
            "generate_scene_script",
            "generate_scene_scripts_batch",
            "generate_narrative_structure", 
            "optimize_dialogue",
            "analyze_script_continuity"
        ]
    
    def _initialize(self):
        """初始化工具"""
        pass
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """获取指定操作的参数架构"""
        base_schema = {
            "type": "object",
            "properties": {}
        }
        
        if action == "generate_scene_script":
            base_schema["properties"] = {
                "scene_data": {
                    "type": "object",
                    "description": "场景数据，包含视觉描述、内容重点等",
                    "properties": {
                        "scene_thesis": {"type": "string"},
                        "script_text": {"type": "string"},
                        "title": {"type": "string"},
                        "visual_description": {"type": "string"},
                        "narrative_description": {"type": "string"},
                        "duration": {"type": "number"},
                        "mood_and_atmosphere": {"type": "string"},
                        "camera_angle": {"type": "string"},
                        "creative_intent": {"type": "string"},
                        "characters_present": {"type": "array", "items": {"type": "string"}},
                        "character_descriptions": {"type": "array", "items": {"type": "string"}},
                    }
                },
                "video_style": {
                    "type": "string", 
                    "description": "视频风格"
                },
                "context": {
                    "type": "object",
                    "description": "上下文信息"
                },
                "script_review_contract": {
                    "type": "object",
                    "description": "脚本审阅阶段生成的显式修订/重规划约束"
                },
                "review_guidance": {
                    "type": "string",
                    "description": "面向脚本生成的可读审阅指导文本"
                },
                # 允许调用方（Agent）通过配置传入模型与token预算
                "model": {
                    "type": "string",
                    "description": "用于脚本生成的模型（来自ai_config映射）"
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "最大token数（来自模型配置），用于替代工具内硬编码"
                }
            }
            base_schema["required"] = ["scene_data"]

        elif action == "generate_scene_scripts_batch":
            base_schema["properties"] = {
                "scenes": {
                    "type": "array",
                    "description": "批量场景参数列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "scene_number": {"type": "integer"},
                            "scene_data": {
                                "type": "object",
                                "description": "场景数据，包含视觉描述、内容重点等",
                                "properties": {
                                    "scene_thesis": {"type": "string"},
                                    "script_text": {"type": "string"},
                                    "title": {"type": "string"},
                                    "visual_description": {"type": "string"},
                                    "narrative_description": {"type": "string"},
                                    "duration": {"type": "number"},
                                    "mood_and_atmosphere": {"type": "string"},
                                    "camera_angle": {"type": "string"},
                                    "creative_intent": {"type": "string"},
                                    "characters_present": {"type": "array", "items": {"type": "string"}},
                                    "character_descriptions": {"type": "array", "items": {"type": "string"}},
                                }
                            },
                            "video_style": {"type": "string"},
                            "context": {"type": "object"},
                            "script_review_contract": {"type": "object"},
                            "review_guidance": {"type": "string"},
                            "voice_guidance": {"type": "object"},
                            "intelligent_style_design": {"type": "object"},
                            "model": {"type": "string"},
                            "max_tokens": {"type": "integer"},
                        }
                    },
                },
                "max_concurrency": {
                    "type": "integer",
                    "description": "批量并发上限（来自配置，必要时可覆盖）",
                },
            }
            base_schema["required"] = ["scenes"]
            
        elif action == "generate_narrative_structure":
            base_schema["properties"] = {
                "scenes_data": {
                    "type": "array",
                    "description": "场景数据列表"
                },
                "video_style": {
                    "type": "string",
                    "description": "视频风格" 
                }
            }
            base_schema["required"] = ["scenes_data"]
            
        elif action == "optimize_dialogue":
            base_schema["properties"] = {
                "script_text": {
                    "type": "string",
                    "description": "脚本文本"
                },
                "target_tone": {
                    "type": "string", 
                    "description": "目标语调"
                }
            }
            base_schema["required"] = ["script_text"]
            
        elif action == "analyze_script_continuity":
            base_schema["properties"] = {
                "scripts": {
                    "type": "array",
                    "description": "脚本列表"
                }
            }
            base_schema["required"] = ["scripts"]
        
        return base_schema
    
    async def _execute_impl(self, tool_input) -> Dict[str, Any]:
        """执行脚本生成相关操作"""
        
        action = tool_input.action
        parameters = tool_input.parameters
        
        if action == "generate_scene_script":
            return await self._generate_scene_script(parameters)
        elif action == "generate_scene_scripts_batch":
            return await self._generate_scene_scripts_batch(parameters)
        elif action == "generate_narrative_structure":
            return await self._generate_narrative_structure(parameters)
        elif action == "optimize_dialogue":
            return await self._optimize_dialogue(parameters)
        elif action == "analyze_script_continuity":
            return await self._analyze_script_continuity(parameters)
        else:
            raise ValueError(f"Unknown action: {action}")

    @staticmethod
    def _clip_text(value: Any, max_len: int = 180) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        if max_len <= 3:
            return text[:max_len]
        return text[: max_len - 3] + "..."

    def _build_context_blocks(self, context: Dict[str, Any], scene_data: Dict[str, Any]) -> Dict[str, str]:
        if not isinstance(context, dict):
            context = {}
        if not isinstance(scene_data, dict):
            scene_data = {}

        lines: List[str] = []

        narrative_arc = self._clip_text(context.get("narrative_arc"), 140)
        if narrative_arc:
            lines.append(f"- 全片主线：{narrative_arc}")

        episode_context = context.get("episode_context")
        if isinstance(episode_context, dict):
            title = self._clip_text(episode_context.get("title"), 60)
            summary = self._clip_text(episode_context.get("summary"), 120)
            purpose = self._clip_text(episode_context.get("narrative_purpose"), 100)
            if title or summary or purpose:
                segments = [seg for seg in [title, summary, purpose] if seg]
                lines.append("- 所属篇章：" + "；".join(segments))

        project_context = context.get("project_context")
        if isinstance(project_context, dict):
            project_brief = self._clip_text(
                project_context.get("project_brief") or project_context.get("summary"),
                120,
            )
            global_theme = self._clip_text(project_context.get("global_theme"), 80)
            if project_brief or global_theme:
                segments = [seg for seg in [project_brief, global_theme] if seg]
                lines.append("- 项目基线：" + "；".join(segments))

        approved_script = self._clip_text(context.get("approved_script"), 160)
        if approved_script:
            lines.append(f"- 已确认脚本片段：{approved_script}")

        previous_scene = self._clip_text(context.get("previous_scene"), 120)
        if previous_scene:
            lines.append(f"- 上一场承接：{previous_scene}")

        target_duration = scene_data.get("duration")
        try:
            target_duration = float(target_duration)
        except (TypeError, ValueError):
            target_duration = None

        duration_guidance = ""
        if target_duration and target_duration > 0:
            duration_text = (
                str(int(target_duration))
                if float(target_duration).is_integer()
                else f"{target_duration:g}"
            )
            duration_guidance = (
                f"本场目标时长为 {duration_text}s。脚本必须产出能支撑该时长的局部事件弧线，"
                "不要只写人物状态、情绪说明或镜头展示。"
            )

        return {
            "story_context_block": "\n".join(lines).strip(),
            "duration_guidance": duration_guidance,
        }
    
    async def _generate_scene_script(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成场景脚本 - 使用专业提示词模板和LLM智能决策"""

        scene_data = params.get("scene_data", {})
        intelligent_style_design = params.get("intelligent_style_design", {})
        video_style = params.get("video_style", "professional")  # 向后兼容
        context = params.get("context", {})
        script_review_contract = params.get("script_review_contract") or {}
        review_guidance = str(params.get("review_guidance") or "").strip()
        if not review_guidance:
            review_guidance = format_script_review_guidance(script_review_contract)
        voice_guidance = params.get("voice_guidance", {}) or {}
        should_narrate = bool(voice_guidance.get("should_narrate", True))
        pace_tag = str(voice_guidance.get("pace_tag", "")).strip().lower()
        target_char_count = voice_guidance.get("target_char_count")
        try:
            target_char_count = int(target_char_count) if target_char_count is not None else None
        except (TypeError, ValueError):
            target_char_count = None

        # 从参数或全局配置确定模型与token预算（优先 tool_model_mapping，其次 agent 映射）
        try:
            from ....core.ai_config import get_ai_config
            from ....core.config import settings as _settings
            ai_cfg = get_ai_config()
            model_name = params.get("model") or ai_cfg.get_model_for_tool("script_generation_tool") or ai_cfg.get_model_for_agent("script_writer")
            model_cfg = ai_cfg.get_model_config(model_name) if model_name else None
            req_model = model_name or None
            # 选择预算：优先参数传入，其次模型配置，最后使用全局standard作为兜底
            req_max_tokens = params.get("max_tokens")
            if not (isinstance(req_max_tokens, int) and req_max_tokens > 0):
                if model_cfg and getattr(model_cfg, 'max_tokens', None):
                    req_max_tokens = int(model_cfg.max_tokens)
                else:
                    req_max_tokens = int(getattr(_settings, 'LLM_MAX_TOKENS_STANDARD', 2048))
        except Exception:
            req_model = params.get("model") or None
            req_max_tokens = params.get("max_tokens") or 1000
        
        # MAS智能风格适配：优先使用intelligent_style_design
        if intelligent_style_design:
            style_context = f"""风格设计: {intelligent_style_design.get('style_name', '智能风格')}
            视觉表现: {intelligent_style_design.get('visual_approach', '')}  
            情感基调: {intelligent_style_design.get('emotional_tone', '')}"""
        else:
            style_context = f"视频风格: {video_style}"
        
        # 动态读取视频能力（离散时长列表）并构建中性提示
        from ....core.video_config_manager import get_video_config
        _prov = get_video_config().get_current_provider_config()
        _vcaps = _prov.duration_capabilities
        _default_dur = _prov.default_duration

        voice_expectations: List[str] = []
        if should_narrate:
            if pace_tag:
                voice_expectations.append(f"节奏：{pace_tag}")
            if target_char_count:
                voice_expectations.append(f"目标字数：约 {target_char_count} 字（允许±20% 浮动）")
            emotion = voice_guidance.get("emotion")
            if emotion:
                voice_expectations.append(f"情绪：{emotion}")
            objective = voice_guidance.get("objective")
            if objective:
                voice_expectations.append(f"目的：{objective}")
            key_points = voice_guidance.get("key_points", [])
            if key_points:
                voice_expectations.append("包含要点：" + "、".join(str(k) for k in key_points if k))

        from ...prompts.template_manager import get_template_manager

        template_manager = get_template_manager("script_writer")
        duration_caps_str = "、".join(str(int(cap)) for cap in _vcaps)
        context_blocks = self._build_context_blocks(context, scene_data)
        prompt = template_manager.render_template(
            "scene_script_generation",
            {
                "scene_number": scene_data.get("scene_number", 1),
                "scene_thesis": scene_data.get("scene_thesis", ""),
                "title": scene_data.get("title", ""),
                "visual_description": scene_data.get("visual_description", ""),
                "narrative_description": scene_data.get("narrative_description", ""),
                "mood_and_atmosphere": scene_data.get("mood_and_atmosphere", ""),
                "camera_angle": scene_data.get("camera_angle", ""),
                "creative_intent": scene_data.get("creative_intent", ""),
                "characters_present": scene_data.get("characters_present", []) or [],
                "character_descriptions": scene_data.get("character_descriptions", []) or [],
                "style_context": style_context,
                "duration_capabilities": duration_caps_str,
                "voice_expectations": voice_expectations,
                "should_narrate": should_narrate,
                "target_char_count": target_char_count,
                "pace_tag": pace_tag,
                "video_style": video_style,
                "review_guidance": review_guidance,
                "story_context_block": context_blocks.get("story_context_block", ""),
                "duration_guidance": context_blocks.get("duration_guidance", ""),
            },
        )

        try:
            # 使用统一 LLM 服务
            from .service_interfaces import get_llm_service
            llm = get_llm_service()
            res = await llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=int(req_max_tokens or 1000),
                model=req_model,
                response_format={"type": "json_object"},
                thinking={"type": "disabled"}
            )
            llm_content = (res.get("content") or "").strip()
            finish_reason = res.get("finish_reason")
            
            # 解析JSON响应
            try:
                script_data = json.loads(llm_content)
                
                # ✅ MAS设计原则3：验证LLM的智能决策结果
                if "duration" not in script_data or script_data["duration"] not in _vcaps:
                    # LLM返回无效值时，回退到provider默认值
                    script_data["duration"] = _default_dur
                    script_data["duration_reasoning"] = f"自动调整为API支持的默认时长: {script_data['duration']}s"
                
                if "success" not in script_data:
                    script_data["success"] = True
                # 附带基础元信息，便于上层诊断长度截断等问题
                script_data.setdefault("_meta", {})
                try:
                    script_data["_meta"].update({
                        "finish_reason": finish_reason,
                        "model": res.get("model"),
                        "requested_max_tokens": int(req_max_tokens or 0)
                    })
                except Exception:
                    pass
                if should_narrate and not (script_data.get("voice_over_text") or "voice_over_text" in script_data):
                    raise ValueError("voice_over_text missing in script_generation response")

                return script_data

            except json.JSONDecodeError as exc:
                raise ValueError(f"Failed to parse LLM response as JSON: {exc}")
                
        except Exception as e:
            raise ToolError(
                f"场景脚本生成失败: {str(e)}",
                error_code="scene_script_failed",
                details={
                    "duration": _default_dur,
                    "duration_reasoning": "发生错误，使用默认时长",
                },
            )

    async def _generate_scene_scripts_batch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """批量生成场景脚本"""

        scenes = params.get("scenes", [])
        if not isinstance(scenes, list) or not scenes:
            raise ToolValidationError("scenes must be a non-empty list", self.metadata.name)

        max_concurrency = params.get("max_concurrency")
        if not (isinstance(max_concurrency, int) and max_concurrency > 0):
            try:
                from ....core.config import settings as _settings
                max_concurrency = int(getattr(_settings, "SCRIPT_GENERATION_MAX_CONCURRENCY", 3))
            except Exception:
                max_concurrency = 3
        if max_concurrency < 1:
            max_concurrency = 1

        semaphore = asyncio.Semaphore(max_concurrency)
        scripts: Dict[str, Any] = {}
        failures: List[Dict[str, Any]] = []

        async def _run_scene(scene_params: Dict[str, Any], scene_index: int) -> None:
            async with semaphore:
                scene_number = scene_params.get("scene_number")
                scene_data = scene_params.get("scene_data") if isinstance(scene_params, dict) else {}
                if scene_number is None and isinstance(scene_data, dict):
                    scene_number = scene_data.get("scene_number")
                try:
                    result = await self._generate_scene_script(scene_params)
                    key = str(scene_number) if scene_number is not None else str(scene_index + 1)
                    scripts[key] = result
                except Exception as exc:
                    failures.append(
                        {
                            "scene_number": scene_number,
                            "error": str(exc),
                        }
                    )

        tasks = [
            asyncio.create_task(_run_scene(scene, idx))
            for idx, scene in enumerate(scenes)
        ]
        await asyncio.gather(*tasks)

        return {
            "batch_success": len(failures) == 0,
            "scripts": scripts,
            "failures": failures,
            "total": len(scenes),
            "success_count": len(scripts),
            "failure_count": len(failures),
        }
    
    async def _generate_narrative_structure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成叙事结构"""
        
        scenes_data = params.get("scenes_data", [])
        video_style = params.get("video_style", "professional")
        
        prompt = f"""请分析以下场景并生成整体叙事结构：

场景列表：
{json.dumps(scenes_data, ensure_ascii=False, indent=2)}

视频风格：{video_style}

请生成：
1. 整体叙事主线
2. 场景间的逻辑关系
3. 情绪起伏曲线
4. 关键转折点

返回JSON格式：
{{
    "narrative_theme": "叙事主题",
    "story_arc": "故事弧线描述",
    "scene_connections": ["场景连接描述"],
    "emotional_curve": "情绪曲线",
    "key_moments": ["关键时刻"],
    "success": true
}}"""
        
        try:
            # 使用统一 LLM 服务
            from .service_interfaces import get_llm_service
            llm = get_llm_service()
            res = await llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=800,
                response_format={"type": "json_object"}
            )
            llm_content = (res.get("content") or "").strip()
            
            try:
                narrative_data = json.loads(llm_content)
                if "success" not in narrative_data:
                    narrative_data["success"] = True
                return narrative_data
            except json.JSONDecodeError:
                return {
                    "narrative_theme": "基于提供场景的连贯叙事",
                    "story_arc": llm_content,
                    "scene_connections": ["场景间自然过渡"],
                    "emotional_curve": "渐进式情感发展",
                    "key_moments": ["各场景重点时刻"],
                }

        except Exception as e:
            raise ToolError(f"叙事结构生成失败: {str(e)}", error_code="narrative_structure_failed")
    
    async def _optimize_dialogue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """优化对话内容"""
        
        script_text = params.get("script_text", "")
        target_tone = params.get("target_tone", "自然")
        
        prompt = f"""请优化以下脚本的对话部分：

原始脚本：
{script_text}

优化目标：
- 语调：{target_tone}
- 适合语音合成
- 自然流畅
- 符合视频内容

返回优化后的脚本文本。"""
        
        try:
            from .service_interfaces import get_llm_service
            llm = get_llm_service()
            res = await llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=600
            )
            optimized_text = (res.get("content") or script_text)
            if optimized_text:
                return {
                    "optimized_script": optimized_text,
                    "optimization_notes": "对话语调和流畅度优化",
                }
            raise ToolError("未生成优化结果", error_code="dialogue_optimize_empty")

        except Exception as e:
            raise ToolError(f"对话优化失败: {str(e)}", error_code="dialogue_optimize_failed")
    
    async def _analyze_script_continuity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """分析脚本连续性"""
        
        scripts = params.get("scripts", [])
        
        if len(scripts) < 2:
            return {
                "continuity_score": 1.0,
                "analysis": "单场景或场景过少，无需连续性分析",
                "suggestions": [],
                "success": True
            }
        
        prompt = f"""请分析以下脚本的连续性：

脚本列表：
{json.dumps(scripts, ensure_ascii=False, indent=2)}

分析维度：
1. 内容逻辑连贯性
2. 情绪过渡自然性
3. 主题一致性
4. 语言风格统一性

返回JSON格式：
{{
    "continuity_score": 0.8,
    "analysis": "连续性分析",
    "weak_points": ["薄弱环节"],
    "suggestions": ["改进建议"],
    "success": true
}}"""
        
        try:
            from .service_interfaces import get_llm_service
            llm = get_llm_service()
            res = await llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            llm_content = (res.get("content") or "").strip()
            if llm_content:
                try:
                    analysis_data = json.loads(llm_content)
                    return analysis_data
                except json.JSONDecodeError:
                    return {
                        "continuity_score": 0.7,
                        "analysis": llm_content,
                        "weak_points": [],
                        "suggestions": ["基于LLM分析进行优化"],
                    }
            raise ToolError(
                "连续性分析失败",
                error_code="continuity_analysis_failed",
                details={"suggestions": ["手动检查脚本连贯性"]},
            )

        except Exception as e:
            raise ToolError(f"连续性分析失败: {str(e)}", error_code="continuity_analysis_failed")

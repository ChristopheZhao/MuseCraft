"""
Script Generation Tool - 封装脚本生成业务逻辑
"""

import asyncio
import json
from typing import Dict, Any, List, Optional

from ..base_tool import AsyncTool, ToolMetadata, ToolType


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
                        "script_text": {"type": "string"},
                        "visual_description": {"type": "string"},
                        "narrative_description": {"type": "string"},
                        "duration": {"type": "number"}
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
        elif action == "generate_narrative_structure":
            return await self._generate_narrative_structure(parameters)
        elif action == "optimize_dialogue":
            return await self._optimize_dialogue(parameters)
        elif action == "analyze_script_continuity":
            return await self._analyze_script_continuity(parameters)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _generate_scene_script(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成场景脚本 - 使用专业提示词模板和LLM智能决策"""
        
        scene_data = params.get("scene_data", {})
        intelligent_style_design = params.get("intelligent_style_design", {})
        video_style = params.get("video_style", "professional")  # 向后兼容
        context = params.get("context", {})

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

        prompt = f"""你是专业视频脚本作家。为以下单个场景生成生产就绪脚本（JSON）。

场景信息：
- 场景编号：{scene_data.get('scene_number', 1)}
- 视觉描述：{scene_data.get('visual_description', '')}
- 叙事描述：{scene_data.get('narrative_description', '')}
- 风格上下文：{style_context}

要求：
1. 根据场景复杂度选择合适的时长（仅可从{_vcaps}中选择）；
2. 输出脚本文本与可选的叙事/音乐/音效字段；
3. 直接返回 JSON，不要解释性文本。

JSON 模板示例：
{{
  "duration": 5,
  "script_text": "……",
  "narrative_description": "……",
  "background_music_style": "……",
  "sound_effects": ["……"]
}}
"""

        try:
            # 使用统一 LLM 服务
            from .service_interfaces import get_llm_service
            llm = get_llm_service()
            res = await llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=int(req_max_tokens or 1000),
                model=req_model,
                response_format={"type": "json_object"}
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
                
                return script_data
                
            except json.JSONDecodeError:
                # 如果JSON解析失败，构建基本响应，默认使用provider默认时长
                return {
                    "duration": _default_dur,  # ✅ 遵循离散时长约束
                    "duration_reasoning": "JSON解析失败，使用默认时长",
                    "script_text": llm_content,
                    "visual_guidance": f"适合{video_style}风格的视觉表现",
                    "emotional_tone": "根据内容自然表达",
                    "keywords": [],
                    "success": True,
                    "_meta": {
                        "finish_reason": finish_reason,
                        "model": req_model,
                        "requested_max_tokens": int(req_max_tokens or 0)
                    }
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"场景脚本生成失败: {str(e)}",
                "duration": _default_dur,  # ✅ 即使错误也遵循离散时长约束
                "duration_reasoning": "发生错误，使用默认时长"
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
                    "success": True
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"叙事结构生成失败: {str(e)}"
            }
    
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
                    "success": True
                }
            return {
                "optimized_script": script_text,
                "optimization_notes": "优化失败，返回原始脚本",
                "success": False
            }
                
        except Exception as e:
            return {
                "optimized_script": script_text,
                "success": False,
                "error": f"对话优化失败: {str(e)}"
            }
    
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
                    if "success" not in analysis_data:
                        analysis_data["success"] = True
                    return analysis_data
                except json.JSONDecodeError:
                    return {
                        "continuity_score": 0.7,
                        "analysis": llm_content,
                        "weak_points": [],
                        "suggestions": ["基于LLM分析进行优化"],
                        "success": True
                    }
            return {
                "continuity_score": 0.5,
                "analysis": "连续性分析失败",
                "suggestions": ["手动检查脚本连贯性"],
                "success": False
            }
                
        except Exception as e:
            return {
                "continuity_score": 0.5,
                "success": False,
                "error": f"连续性分析失败: {str(e)}"
            }

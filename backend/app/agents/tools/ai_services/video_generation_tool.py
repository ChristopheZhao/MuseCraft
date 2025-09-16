"""
专门的视频生成工具 - 封装业务逻辑和Function Call决策
"""

import json
from typing import Dict, Any, List, Optional, Union
import logging

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .service_interfaces import get_llm_service, get_video_service, ServiceProvider
from ...core.video_config_manager import get_video_config


class VideoGenerationTool(AsyncTool):
    """
    专门的视频生成工具
    
    功能：
    - 智能分析场景内容选择最优参数
    - 封装视频生成业务逻辑
    - 支持场景连续性处理
    - Function Call决策duration、model等参数
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="video_generation",
            version="1.0.0",
            description="智能视频生成工具，根据场景内容自动选择最优参数",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["video", "generation", "intelligence", "function-call"],
            capabilities=[
                "intelligent_parameter_selection",
                "scene_continuity_support",
                "duration_optimization",
                "prompt_enhancement"
            ],
            limitations=[
                "requires_zhipu_api_key",
                "depends_on_video_config",
                "rate_limited"
            ]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
        
        # 初始化依赖的服务
        self.llm_service = None
        self.video_service = None
        self.video_config = get_video_config()
        
    def _initialize(self):
        """初始化视频生成工具"""
        # 初始化分层服务
        try:
            self.llm_service = get_llm_service()  # 用于智能分析和决策
            self.video_service = get_video_service()  # 用于视频生成
            
            self._functional = (
                self.llm_service.is_available() and 
                self.video_service.is_available()
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize services: {e}")
            self._functional = False
        
        if not self._functional:
            self.logger.warning("VideoGenerationTool not functional - required services unavailable")
    
    def get_available_actions(self) -> List[str]:
        return [
            "generate",
            "analyze_scene_requirements", 
            "optimize_parameters"
        ]

    def get_action_stage(self, action: str) -> str:
        """声明动作阶段：分析/优化为 plan，生成为 act。"""
        if action == "generate":
            return "act"
        return "plan"
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
            "generate": {
                "type": "object",
                "properties": {
                    "scene_data": {
                        "type": "object",
                        "description": "场景数据，包含script_text, visual_description等"
                    },
                    "image_url": {
                        "type": "string", 
                        "description": "参考图片URL或base64数据"
                    },
                    "continuity_frame": {
                        "type": "string",
                        "description": "连续性帧数据（可选）"
                    },
                    "user_preferences": {
                        "type": "object",
                        "description": "用户偏好设置（可选）",
                        "properties": {
                            "duration": {"type": "integer", "enum": [5, 10]},
                            "style": {"type": "string"},
                            "quality": {"type": "string"}
                        }
                    }
                },
                "required": ["scene_data", "image_url"]
            },
            "analyze_scene_requirements": {
                "type": "object",
                "properties": {
                    "scene_data": {"type": "object"},
                    "available_options": {"type": "object"}
                },
                "required": ["scene_data"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行视频生成工具"""
        if not self._functional:
            raise ToolError("VideoGenerationTool not functional - zhipu_client unavailable", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "generate":
            return await self._generate_video_with_intelligence(params)
        elif action == "analyze_scene_requirements":
            return await self._analyze_scene_requirements(params)
        elif action == "optimize_parameters":
            return await self._optimize_parameters(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _generate_video_with_intelligence(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """智能视频生成 - 包含Function Call参数决策"""
        
        scene_data = params["scene_data"]
        image_url = params["image_url"]
        continuity_frame = params.get("continuity_frame")
        user_preferences = params.get("user_preferences", {})
        
        # Step 1: 使用LLM分析场景并智能选择参数
        optimal_params = await self._llm_analyze_and_select_parameters(
            scene_data, user_preferences
        )
        
        # Step 2: 构建视频生成提示词
        enhanced_prompt = await self._build_enhanced_prompt(scene_data, optimal_params)
        
        # Step 3: 准备最终图像输入（优先使用连续性帧）
        final_image_input = continuity_frame if continuity_frame else image_url
        
        # Step 4: 调用zhipu_client服务生成视频
        generation_params = {
            "prompt": enhanced_prompt,
            "image_url": final_image_input,
            "model": optimal_params["model"],
            "duration": optimal_params["duration"]
        }
        
        # 支持首尾帧模式
        if optimal_params.get("first_frame_image") and optimal_params.get("last_frame_image"):
            generation_params.update({
                "first_frame_image": optimal_params["first_frame_image"],
                "last_frame_image": optimal_params["last_frame_image"]
            })
        
        self.logger.info(f"🎬 Generating video with intelligent parameters: duration={optimal_params['duration']}s, model={optimal_params['model']}")
        
        result = await self.video_service.generate_video(
            prompt=enhanced_prompt,
            image_url=final_image_input,
            model=optimal_params["model"],
            duration=optimal_params["duration"],
            first_frame_image=optimal_params.get("first_frame_image"),
            last_frame_image=optimal_params.get("last_frame_image")
        )
        
        # Step 5: 增强返回结果，包含决策信息
        result.update({
            "intelligent_parameters": optimal_params,
            "llm_reasoning": optimal_params.get("reasoning", ""),
            "prompt_used": enhanced_prompt,
            "continuity_mode": bool(continuity_frame)
        })
        
        return result
    
    async def _llm_analyze_and_select_parameters(
        self, 
        scene_data: Dict[str, Any], 
        user_preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用LLM分析场景内容并智能选择最优参数"""
        
        # 获取当前提供商配置
        provider_config = self.video_config.get_current_provider_config()
        
        # 构建Function Call schema
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "select_video_parameters",
                    "description": "根据场景内容智能选择视频生成参数",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "duration": {
                                "type": "integer",
                                "enum": provider_config.duration_capabilities,
                                "description": f"视频时长选择：{provider_config.duration_capabilities}秒。简单静态场景选较短时长，复杂动作场景选较长时长"
                            },
                            "model": {
                                "type": "string", 
                                "enum": [provider_config.model_name],
                                "description": "视频生成模型"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "选择这些参数的理由"
                            }
                        },
                        "required": ["duration", "model", "reasoning"]
                    }
                }
            }
        ]
        
        # 构建分析提示
        analysis_prompt = f"""
作为视频生成专家，请分析以下场景内容并选择最优的视频参数：

场景信息：
- 脚本文本：{scene_data.get('script_text', '')}
- 视觉描述：{scene_data.get('visual_description', '')}
- 叙事描述：{scene_data.get('narrative_description', '')}
- 氛围描述：{scene_data.get('mood_and_atmosphere', '')}

可选参数：
- 时长选项：{provider_config.duration_capabilities}秒
- 模型：{provider_config.model_name}

用户偏好：{user_preferences}

请根据场景的复杂度、动作密度、叙事节奏选择最合适的参数。
"""
        
        messages = [
            {
                "role": "system",
                "content": "你是视频生成参数优化专家，根据场景内容智能选择最优参数"
            },
            {
                "role": "user", 
                "content": analysis_prompt
            }
        ]
        
        # 使用Function Call进行智能决策
        try:
            # 从 ai_config 读取工具模型映射
            try:
                from ....core.ai_config import get_ai_config
                ai_cfg = get_ai_config()
                cfg_model = ai_cfg.get_model_for_tool("video_generation_tool")
                mcfg = ai_cfg.get_model_config(cfg_model) if cfg_model else None
            except Exception:
                cfg_model = None
                mcfg = None
            req_model = cfg_model or None
            req_temp = 0.3 if not (mcfg and getattr(mcfg, 'temperature', None) is not None) else float(mcfg.temperature)

            llm_result = await self.llm_service.function_call(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                model=req_model,
                temperature=req_temp
            )
            
            # 解析Function Call响应
            if llm_result.get("tool_calls"):
                tool_call = llm_result["tool_calls"][0]
                if tool_call["function"]["name"] == "select_video_parameters":
                    function_args = json.loads(tool_call["function"]["arguments"])
                    self.logger.info(f"🧠 LLM智能选择: {function_args['reasoning']}")
                    return function_args
            
            # 回退到默认参数
            self.logger.warning("LLM未返回Function Call，使用默认参数")
            
        except Exception as e:
            self.logger.error(f"LLM参数分析失败: {e}")
        
        # 回退方案：使用配置默认值 + 用户偏好
        return {
            "duration": user_preferences.get("duration", provider_config.default_duration),
            "model": provider_config.model_name,
            "reasoning": "使用默认配置（LLM分析失败时的回退方案）"
        }
    
    async def _build_enhanced_prompt(self, scene_data: Dict[str, Any], optimal_params: Dict[str, Any]) -> str:
        """构建增强的视频生成提示词"""
        
        # 合成基础描述
        base_lines = [
            scene_data.get('visual_description', ''),
            scene_data.get('script_text', ''),
            scene_data.get('narrative_description', '')
        ]
        # 追加角色一致性语义（若有）
        chars = scene_data.get('character_descriptions') or []
        if not chars:
            names = scene_data.get('characters_present') or []
            if names:
                chars = ["、".join(names)]
        if chars:
            base_lines.append("角色设定：" + "；".join(chars))

        base_prompt = "\n".join([l for l in base_lines if l])
        
        # 根据选择的时长调整提示词风格
        duration = optimal_params["duration"]
        if duration >= 10:
            style_enhancement = "丰富的动作变化，流畅的镜头运动，详细的画面展现"
        else:
            style_enhancement = "精准的关键动作，简洁的画面表达"
        
        enhanced_prompt = f"{base_prompt.strip()}，{style_enhancement}"
        
        # 限制长度
        provider_config = self.video_config.get_current_provider_config()
        if len(enhanced_prompt) > provider_config.prompt_max_length:
            enhanced_prompt = enhanced_prompt[:provider_config.prompt_max_length-3] + "..."
        
        return enhanced_prompt
    
    async def _analyze_scene_requirements(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """分析场景需求"""
        scene_data = params["scene_data"]
        
        # 使用LLM分析场景特点
        analysis = {
            "complexity": "medium",  # 这里可以用LLM分析
            "motion_density": "moderate",
            "recommended_duration": 5,
            "scene_type": "general"
        }
        
        return {
            "analysis": analysis,
            "recommendations": {
                "duration": analysis["recommended_duration"],
                "style_hints": []
            }
        }
    
    async def _optimize_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """优化参数"""
        # 参数优化逻辑
        return {"optimized_params": params}
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "generate":
            if not parameters.get("scene_data"):
                raise ToolValidationError("scene_data is required for generate")
            if not parameters.get("image_url"):
                raise ToolValidationError("image_url is required for generate")

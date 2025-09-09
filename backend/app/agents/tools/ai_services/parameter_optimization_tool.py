"""
参数优化工具 - 基于场景特征智能优化视频生成参数
"""

from typing import Dict, Any, List
import logging

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .service_interfaces import get_llm_service


class ParameterOptimizationTool(AsyncTool):
    """
    参数优化工具
    
    职责：
    - 分析场景特征并推荐最佳的视频生成参数
    - 提供时长、质量、运动强度等参数建议
    - 不做实际生成，只提供参数优化建议
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="parameter_optimization",
            version="1.0.0",
            description="基于场景特征智能优化视频生成参数，提供最佳的时长、质量和运动参数建议",
            tool_type=ToolType.ANALYSIS,
            author="system",
            tags=["parameter", "optimization", "video"],
            capabilities=[
                "duration_optimization",
                "quality_parameter_tuning", 
                "motion_parameter_adjustment",
                "provider_specific_optimization"
            ],
            limitations=[]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
        
        self.llm_service = None
        
    def _initialize(self):
        """初始化参数优化工具"""
        try:
            self.llm_service = get_llm_service()
            self._functional = True if self.llm_service else False
        except Exception as e:
            self.logger.error(f"Failed to initialize LLM service: {e}")
            self._functional = False
        
        if not self._functional:
            self.logger.warning("ParameterOptimizationTool not functional - LLM service unavailable")
    
    def get_available_actions(self) -> List[str]:
        return [
            "optimize_duration",
            "optimize_quality_settings",
            "optimize_motion_parameters", 
            "optimize_all_parameters"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        base_scene_properties = {
            "script_text": {"type": "string", "description": "场景脚本文本"},
            "visual_description": {"type": "string", "description": "视觉描述"},
            "narrative_description": {"type": "string", "description": "叙事描述"},
            "mood_and_atmosphere": {"type": "string", "description": "氛围描述"},
            "duration": {"type": "integer", "description": "原始时长（秒）"}
        }
        
        schemas = {
            "optimize_duration": {
                "type": "object",
                "properties": {
                    "scene_data": {
                        "type": "object",
                        "properties": base_scene_properties,
                        "description": "场景数据"
                    },
                    "available_durations": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "可用的时长选项",
                        "default": [5, 10]
                    }
                },
                "required": ["scene_data"],
                "description": "基于场景内容推荐最佳视频时长"
            },
            "optimize_quality_settings": {
                "type": "object",
                "properties": {
                    "scene_data": {
                        "type": "object", 
                        "properties": base_scene_properties,
                        "description": "场景数据"
                    },
                    "target_quality": {
                        "type": "string",
                        "enum": ["draft", "standard", "high", "cinematic"],
                        "description": "目标质量级别"
                    }
                },
                "required": ["scene_data"],
                "description": "优化质量相关参数设置"
            },
            "optimize_motion_parameters": {
                "type": "object",
                "properties": {
                    "scene_data": {
                        "type": "object",
                        "properties": base_scene_properties,
                        "description": "场景数据"
                    },
                    "motion_complexity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "auto"],
                        "description": "运动复杂度级别"
                    }
                },
                "required": ["scene_data"],
                "description": "优化运动相关参数"
            },
            "optimize_all_parameters": {
                "type": "object",
                "properties": {
                    "scene_data": {
                        "type": "object",
                        "properties": base_scene_properties,
                        "description": "场景数据"
                    },
                    "provider": {
                        "type": "string",
                        "description": "视频生成服务提供商",
                        "default": "zhipu"
                    },
                    "target_usage": {
                        "type": "string", 
                        "enum": ["preview", "draft", "production", "cinematic"],
                        "description": "目标用途",
                        "default": "production"
                    }
                },
                "required": ["scene_data"],
                "description": "综合优化所有视频生成参数"
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行参数优化"""
        if not self._functional:
            raise ToolError("ParameterOptimizationTool not functional - LLM service unavailable", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "optimize_duration":
            return await self._optimize_duration(params)
        elif action == "optimize_quality_settings":
            return await self._optimize_quality_settings(params)
        elif action == "optimize_motion_parameters":
            return await self._optimize_motion_parameters(params)
        elif action == "optimize_all_parameters":
            return await self._optimize_all_parameters(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _optimize_duration(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """优化视频时长"""
        scene_data = params["scene_data"]
        available_durations = params.get("available_durations", [5, 10])
        
        # 构建分析提示词
        analysis_prompt = f"""
作为视频制作专家，分析以下场景内容并推荐最佳的视频时长：

场景信息：
- 脚本：{scene_data.get('script_text', '')}
- 视觉描述：{scene_data.get('visual_description', '')}
- 叙事描述：{scene_data.get('narrative_description', '')}
- 氛围：{scene_data.get('mood_and_atmosphere', '')}

可选时长：{available_durations}秒

请分析：
1. 场景内容的复杂程度
2. 动作展现需要的时间
3. 叙事节奏要求
4. 推荐的最佳时长及理由

返回JSON格式：
{{
    "recommended_duration": 推荐时长（秒），
    "reasoning": "详细理由",
    "content_complexity": "low/medium/high",
    "action_density": "low/medium/high",
    "narrative_pacing": "slow/medium/fast"
}}
"""

        try:
            # 使用LLM分析（如果可用的话）
            if self.llm_service:
                # 直接使用 chat_completion 并强制 JSON 输出，避免依赖 FC 计划文本
                result = await self.llm_service.chat_completion(
                    messages=[{"role": "user", "content": analysis_prompt}],
                    temperature=0.3,
                    model="glm-4-plus",
                    response_format={"type": "json_object"}
                )
                
                if result.get("content"):
                    import json
                    analysis = json.loads(result["content"])
                else:
                    # Fallback逻辑
                    return self._fallback_duration_optimization(scene_data, available_durations)
            else:
                # LLM服务不可用，直接使用fallback
                return self._fallback_duration_optimization(scene_data, available_durations)
            
            if False:  # 跳过JSON解析部分，直接使用fallback
                analysis = {}
                
                # 验证推荐时长是否在可用选项中
                recommended = analysis.get("recommended_duration", 5)
                if recommended not in available_durations:
                    # 选择最接近的可用时长
                    recommended = min(available_durations, key=lambda x: abs(x - recommended))
                    analysis["recommended_duration"] = recommended
                    analysis["adjusted"] = True
                    analysis["adjustment_reason"] = f"Adjusted to nearest available duration: {recommended}s"
                
                return {
                    "optimization_type": "duration",
                    "recommended_parameters": {"duration": recommended},
                    "analysis": analysis,
                    "confidence": 0.85
                }
            else:
                # Fallback逻辑
                return self._fallback_duration_optimization(scene_data, available_durations)
                
        except Exception as e:
            self.logger.error(f"Duration optimization failed: {e}")
            return self._fallback_duration_optimization(scene_data, available_durations)
    
    async def _optimize_quality_settings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """优化质量设置"""
        scene_data = params["scene_data"]
        target_quality = params.get("target_quality", "standard")
        
        # 基于目标质量级别的参数映射
        quality_presets = {
            "draft": {
                "quality": "draft",
                "enhance": False,
                "upscale": False,
                "fps": 24
            },
            "standard": {
                "quality": "standard", 
                "enhance": True,
                "upscale": False,
                "fps": 30
            },
            "high": {
                "quality": "high",
                "enhance": True,
                "upscale": True,
                "fps": 30
            },
            "cinematic": {
                "quality": "cinematic",
                "enhance": True,
                "upscale": True,
                "fps": 24,
                "motion_blur": True
            }
        }
        
        recommended_settings = quality_presets.get(target_quality, quality_presets["standard"])
        
        return {
            "optimization_type": "quality",
            "recommended_parameters": recommended_settings,
            "target_quality": target_quality,
            "confidence": 0.90
        }
    
    async def _optimize_motion_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """优化运动参数"""
        scene_data = params["scene_data"]
        motion_complexity = params.get("motion_complexity", "auto")
        
        if motion_complexity == "auto":
            # 分析场景内容确定运动复杂度
            text_content = f"{scene_data.get('script_text', '')} {scene_data.get('visual_description', '')}"
            
            high_motion_keywords = ["跑", "跳", "飞", "冲", "追", "逃", "打", "踢", "旋转", "翻滚", "爆炸", "碰撞"]
            medium_motion_keywords = ["走", "移动", "转身", "挥手", "点头", "坐下", "站起", "开门", "关门"]
            
            high_motion_count = sum(1 for keyword in high_motion_keywords if keyword in text_content)
            medium_motion_count = sum(1 for keyword in medium_motion_keywords if keyword in text_content)
            
            if high_motion_count >= 2:
                motion_complexity = "high"
            elif high_motion_count >= 1 or medium_motion_count >= 2:
                motion_complexity = "medium"
            else:
                motion_complexity = "low"
        
        # 运动参数映射
        motion_settings = {
            "low": {
                "motion": "low",
                "camera_movement": "static",
                "amplification_ratio": 1.0
            },
            "medium": {
                "motion": "medium",
                "camera_movement": "gentle",
                "amplification_ratio": 1.2
            },
            "high": {
                "motion": "high", 
                "camera_movement": "dynamic",
                "amplification_ratio": 1.5
            }
        }
        
        recommended_settings = motion_settings.get(motion_complexity, motion_settings["medium"])
        
        return {
            "optimization_type": "motion",
            "recommended_parameters": recommended_settings,
            "detected_motion_complexity": motion_complexity,
            "confidence": 0.80
        }
    
    async def _optimize_all_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """综合优化所有参数"""
        scene_data = params["scene_data"]
        provider = params.get("provider", "zhipu")
        target_usage = params.get("target_usage", "production")
        
        # 综合所有优化结果
        duration_result = await self._optimize_duration({"scene_data": scene_data})
        quality_result = await self._optimize_quality_settings({
            "scene_data": scene_data,
            "target_quality": "high" if target_usage == "cinematic" else "standard"
        })
        motion_result = await self._optimize_motion_parameters({
            "scene_data": scene_data,
            "motion_complexity": "auto"
        })
        
        # 合并所有参数
        all_parameters = {}
        all_parameters.update(duration_result.get("recommended_parameters", {}))
        all_parameters.update(quality_result.get("recommended_parameters", {})) 
        all_parameters.update(motion_result.get("recommended_parameters", {}))
        
        # 添加提供商特定的优化
        if provider == "zhipu":
            all_parameters.update({
                "model": "cogvideox-3",
                "size": "1024x576",
                "with_audio": True
            })
        
        return {
            "optimization_type": "comprehensive",
            "recommended_parameters": all_parameters,
            "provider": provider,
            "target_usage": target_usage,
            "sub_optimizations": {
                "duration": duration_result,
                "quality": quality_result,
                "motion": motion_result
            },
            "confidence": 0.88
        }
    
    def _fallback_duration_optimization(self, scene_data: Dict, available_durations: List[int]) -> Dict[str, Any]:
        """时长优化的fallback逻辑"""
        # 简单的启发式规则
        text_length = len(f"{scene_data.get('script_text', '')} {scene_data.get('visual_description', '')}")
        
        if text_length > 200:
            recommended = max(available_durations)  # 复杂场景用长时长
        else:
            recommended = min(available_durations)  # 简单场景用短时长
        
        return {
            "optimization_type": "duration",
            "recommended_parameters": {"duration": recommended},
            "analysis": {
                "recommended_duration": recommended,
                "reasoning": f"Based on content length: {text_length} chars",
                "content_complexity": "high" if text_length > 200 else "low",
                "fallback_method": True
            },
            "confidence": 0.60
        }
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if not parameters.get("scene_data"):
            raise ToolValidationError(f"scene_data is required for {action}")

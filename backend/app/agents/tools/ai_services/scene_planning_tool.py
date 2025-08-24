"""
智能场景规划工具 - 让LLM根据内容智能决定场景数量和时长分配
"""

import json
from typing import Dict, Any, List, Optional
import logging

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .zhipu_client import ZhipuClientTool


class ScenePlanningTool(AsyncTool):
    """
    智能场景规划工具
    
    功能：
    - LLM分析用户输入决定最优场景数量
    - 智能分配每个场景的时长
    - 根据内容复杂度和叙事节奏规划场景
    - 不限制固定的场景数量
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="scene_planning",
            version="1.0.0",
            description="智能场景规划工具，根据内容自动决定最优场景数量和时长分配",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["scene", "planning", "intelligence", "adaptive"],
            capabilities=[
                "intelligent_scene_count_decision",
                "adaptive_duration_allocation",
                "narrative_structure_analysis",
                "content_complexity_assessment"
            ],
            limitations=[
                "requires_zhipu_api_key",
                "depends_on_content_analysis"
            ]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
        
        # 初始化依赖的服务
        self.zhipu_client = None
        
    def _initialize(self):
        """初始化场景规划工具"""
        try:
            self.zhipu_client = ZhipuClientTool()
            self.zhipu_client._initialize()
            self._functional = self.zhipu_client._functional
        except Exception as e:
            self.logger.error(f"Failed to initialize zhipu_client: {e}")
            self._functional = False
        
        if not self._functional:
            self.logger.warning("ScenePlanningTool not functional - zhipu_client unavailable")
    
    def get_available_actions(self) -> List[str]:
        return [
            "plan_scenes",
            "analyze_content_complexity",
            "optimize_scene_distribution"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
            "plan_scenes": {
                "type": "object",
                "properties": {
                    "user_input": {
                        "type": "string",
                        "description": "用户原始输入内容"
                    },
                    "target_total_duration": {
                        "type": "number",
                        "description": "目标总时长（秒），可选"
                    },
                    "content_type": {
                        "type": "string",
                        "description": "内容类型：story, tutorial, promotional等",
                        "enum": ["story", "tutorial", "promotional", "documentary", "entertainment", "educational"]
                    },
                    "user_preferences": {
                        "type": "object",
                        "description": "用户偏好设置",
                        "properties": {
                            "pacing": {"type": "string", "enum": ["fast", "medium", "slow"]},
                            "style": {"type": "string"},
                            "scene_complexity": {"type": "string", "enum": ["simple", "moderate", "complex"]}
                        }
                    }
                },
                "required": ["user_input"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行场景规划工具"""
        if not self._functional:
            raise ToolError("ScenePlanningTool not functional - zhipu_client unavailable", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "plan_scenes":
            return await self._plan_scenes_intelligently(params)
        elif action == "analyze_content_complexity":
            return await self._analyze_content_complexity(params)
        elif action == "optimize_scene_distribution":
            return await self._optimize_scene_distribution(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _plan_scenes_intelligently(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """使用LLM智能规划场景数量和时长分配"""
        
        user_input = params["user_input"]
        target_total_duration = params.get("target_total_duration", 30.0)  # 默认30秒
        content_type = params.get("content_type", "story")
        user_preferences = params.get("user_preferences", {})
        
        # 构建Function Call schema
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "plan_video_scenes",
                    "description": "根据内容智能规划视频场景数量和时长分配",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "total_scenes": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 20,  # 灵活的上限，不是硬限制
                                "description": "根据内容复杂度和叙事需要决定的场景总数"
                            },
                            "scene_durations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "scene_number": {"type": "integer"},
                                        "planned_duration": {"type": "number"},
                                        "content_focus": {"type": "string"},
                                        "complexity_level": {"type": "string", "enum": ["simple", "moderate", "complex"]}
                                    }
                                },
                                "description": "每个场景的详细规划"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "为什么选择这个场景数量和时长分配的详细理由"
                            },
                            "narrative_structure": {
                                "type": "object",
                                "properties": {
                                    "opening_style": {"type": "string"},
                                    "development_approach": {"type": "string"},
                                    "climax_placement": {"type": "string"},
                                    "conclusion_style": {"type": "string"}
                                },
                                "description": "叙事结构分析"
                            }
                        },
                        "required": ["total_scenes", "scene_durations", "reasoning", "narrative_structure"]
                    }
                }
            }
        ]
        
        # 构建智能分析提示
        analysis_prompt = f"""
作为视频叙事专家，请根据以下用户输入智能规划视频场景：

用户输入内容：
{user_input}

目标总时长：{target_total_duration}秒
内容类型：{content_type}
用户偏好：{user_preferences}

请分析内容的叙事需求，决定：
1. 最优的场景数量（不限制在4-6个，根据内容需要灵活决定）
2. 每个场景的时长分配（考虑内容密度和节奏）
3. 场景的复杂度级别（影响后续视频生成参数选择）

分析要点：
- 简单概念：可能只需1-2个场景
- 复杂故事：可能需要8-15个场景
- 教程内容：根据步骤数量决定场景数
- 推广内容：根据卖点数量决定场景数

每个场景的时长分配要考虑：
- 内容复杂度（复杂场景需要更长时间展现）
- 叙事节奏（开头结尾可能较短，高潮较长）
- 技术限制（单个场景视频生成能力5-10秒）
"""
        
        messages = [
            {
                "role": "system",
                "content": "你是视频叙事规划专家，擅长根据内容特点智能决定最优的场景数量和时长分配，不受固定场景数量限制"
            },
            {
                "role": "user", 
                "content": analysis_prompt
            }
        ]
        
        # 使用Function Call进行智能规划
        try:
            llm_result = await self.zhipu_client._chat_completion({
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "model": "glm-4-plus",
                "temperature": 0.3
            })
            
            # 解析Function Call响应
            if llm_result.get("tool_calls"):
                tool_call = llm_result["tool_calls"][0]
                if tool_call["function"]["name"] == "plan_video_scenes":
                    function_args = json.loads(tool_call["function"]["arguments"])
                    
                    # 验证和优化规划结果
                    validated_plan = self._validate_and_optimize_plan(
                        function_args, target_total_duration
                    )
                    
                    self.logger.info(f"🎯 LLM智能规划: {validated_plan['total_scenes']}个场景 - {validated_plan['reasoning']}")
                    
                    return {
                        "scene_plan": validated_plan,
                        "llm_reasoning": validated_plan["reasoning"],
                        "planning_approach": "llm_intelligent",
                        "total_planned_duration": sum(
                            scene["planned_duration"] for scene in validated_plan["scene_durations"]
                        )
                    }
            
            self.logger.warning("LLM未返回Function Call，使用回退规划")
            
        except Exception as e:
            self.logger.error(f"LLM场景规划失败: {e}")
        
        # 回退方案：基于内容长度的简单规划
        return self._fallback_scene_planning(user_input, target_total_duration)
    
    def _validate_and_optimize_plan(
        self, 
        plan: Dict[str, Any], 
        target_total_duration: float
    ) -> Dict[str, Any]:
        """验证和优化LLM生成的规划"""
        
        scene_durations = plan["scene_durations"]
        total_planned = sum(scene["planned_duration"] for scene in scene_durations)
        
        # 如果总时长差异过大，按比例调整
        if abs(total_planned - target_total_duration) > target_total_duration * 0.3:
            scale_factor = target_total_duration / total_planned
            for scene in scene_durations:
                scene["planned_duration"] = round(scene["planned_duration"] * scale_factor, 1)
                # 确保每个场景时长在合理范围内
                scene["planned_duration"] = max(2.0, min(15.0, scene["planned_duration"]))
        
        # 确保场景数量合理
        if plan["total_scenes"] != len(scene_durations):
            plan["total_scenes"] = len(scene_durations)
        
        return plan
    
    def _fallback_scene_planning(
        self, 
        user_input: str, 
        target_total_duration: float
    ) -> Dict[str, Any]:
        """回退的场景规划方案"""
        
        # 基于内容长度的简单启发式规划
        content_length = len(user_input)
        
        if content_length < 100:
            # 简短内容：2-3个场景
            scene_count = 2
        elif content_length < 300:
            # 中等内容：3-5个场景
            scene_count = 4
        else:
            # 长内容：5-8个场景
            scene_count = 6
        
        # 平均分配时长
        avg_duration = target_total_duration / scene_count
        scene_durations = []
        
        for i in range(scene_count):
            scene_durations.append({
                "scene_number": i + 1,
                "planned_duration": round(avg_duration, 1),
                "content_focus": f"Scene {i + 1}",
                "complexity_level": "moderate"
            })
        
        return {
            "scene_plan": {
                "total_scenes": scene_count,
                "scene_durations": scene_durations,
                "reasoning": f"基于内容长度({content_length}字符)的启发式规划(LLM分析失败时的回退方案)",
                "narrative_structure": {
                    "opening_style": "direct",
                    "development_approach": "linear",
                    "climax_placement": "middle",
                    "conclusion_style": "summary"
                }
            },
            "llm_reasoning": "使用回退启发式规划",
            "planning_approach": "fallback_heuristic",
            "total_planned_duration": target_total_duration
        }
    
    async def _analyze_content_complexity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """分析内容复杂度"""
        # 这里可以用LLM分析内容复杂度
        return {"complexity_analysis": "moderate"}
    
    async def _optimize_scene_distribution(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """优化场景分布"""
        # 优化场景分布逻辑
        return {"optimized_distribution": params}
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "plan_scenes":
            if not parameters.get("user_input"):
                raise ToolValidationError("user_input is required for plan_scenes")
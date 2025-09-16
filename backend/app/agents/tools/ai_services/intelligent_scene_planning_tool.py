"""
智能场景规划工具 - 使用LLM动态决定场景数量和分布
"""

from typing import Dict, Any, List
import logging

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .service_interfaces import get_llm_service


class IntelligentScenePlanningTool(AsyncTool):
    """
    智能场景规划工具 - 替代硬编码的场景规划逻辑
    
    职责：
    - 使用LLM分析内容复杂度和叙事需求
    - 智能决定最佳场景数量（不受4-8的硬编码限制）
    - 为每个场景分配合理的时长
    - 提供场景间的逻辑关系
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="intelligent_scene_planning",
            version="1.0.0",
            description="使用LLM智能分析内容并动态决定最佳的场景数量、时长分配和叙事结构",
            tool_type=ToolType.ANALYSIS,
            author="system",
            tags=["scene", "planning", "llm", "intelligent"],
            capabilities=[
                "dynamic_scene_count_planning",
                "intelligent_duration_allocation",
                "narrative_structure_analysis",
                "complexity_based_planning"
            ],
            limitations=[]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
        
        self.llm_service = None
        
    def _initialize(self):
        """初始化智能场景规划工具"""
        try:
            self.llm_service = get_llm_service()
            self._functional = True if self.llm_service else False
        except Exception as e:
            self.logger.error(f"Failed to initialize LLM service: {e}")
            self._functional = False
        
        if not self._functional:
            self.logger.warning("IntelligentScenePlanningTool not functional - LLM service unavailable")
    
    def get_available_actions(self) -> List[str]:
        return [
            "analyze_and_plan_scenes",
            "optimize_scene_distribution",
            "validate_scene_plan"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
            "analyze_and_plan_scenes": {
                "type": "object",
                "properties": {
                    "user_prompt": {
                        "type": "string",
                        "description": "用户的原始需求描述"
                    },
                    "target_total_duration": {
                        "type": "number",
                        "description": "目标总时长（秒）"
                    },
                    "video_style": {
                        "type": "string",
                        "description": "视频风格",
                        "default": "professional"
                    },
                    "complexity_hint": {
                        "type": "string",
                        "enum": ["simple", "moderate", "complex", "auto"],
                        "description": "复杂度提示，auto表示LLM自主判断",
                        "default": "auto"
                    }
                },
                "required": ["user_prompt", "target_total_duration"],
                "description": "分析用户需求并智能规划最佳场景数量和分布"
            },
            "optimize_scene_distribution": {
                "type": "object",
                "properties": {
                    "scene_plan": {
                        "type": "object",
                        "description": "已有的场景规划"
                    },
                    "optimization_focus": {
                        "type": "string",
                        "enum": ["balance", "dramatic_arc", "pacing", "simplicity"],
                        "description": "优化重点",
                        "default": "balance"
                    }
                },
                "required": ["scene_plan"],
                "description": "优化已有的场景分布方案"
            },
            "validate_scene_plan": {
                "type": "object",
                "properties": {
                    "scene_plan": {
                        "type": "object",
                        "description": "需要验证的场景规划"
                    },
                    "user_requirements": {
                        "type": "object",
                        "description": "用户需求"
                    }
                },
                "required": ["scene_plan", "user_requirements"],
                "description": "验证场景规划是否满足用户需求"
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行智能场景规划"""
        if not self._functional:
            raise ToolError("IntelligentScenePlanningTool not functional - LLM service unavailable", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "analyze_and_plan_scenes":
            return await self._analyze_and_plan_scenes(params)
        elif action == "optimize_scene_distribution":
            return await self._optimize_scene_distribution(params)
        elif action == "validate_scene_plan":
            return await self._validate_scene_plan(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _analyze_and_plan_scenes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """使用LLM智能分析并规划场景"""
        
        user_prompt = params["user_prompt"]
        target_total_duration = params["target_total_duration"]
        video_style = params.get("video_style", "professional")
        complexity_hint = params.get("complexity_hint", "auto")
        
        # 动态获取配置约束
        from ....core.config import settings
        
        min_scenes = settings.SCENE_COUNT_RANGE_MIN
        max_scenes = settings.SCENE_COUNT_RANGE_MAX  
        available_durations = settings.AVAILABLE_SCENE_DURATIONS
        
        # 构建智能场景规划提示词
        planning_prompt = f"""
作为专业的视频制作导演，请分析以下用户需求并制定最佳的场景规划方案：

**用户需求分析**：
内容描述："{user_prompt}"
目标总时长：{target_total_duration}秒
视频风格：{video_style}
复杂度提示：{complexity_hint}

**系统约束**：
⚠️  场景数量范围：{min_scenes}-{max_scenes}个场景（MAS价值体现 + 成本控制）
⚠️  场景时长选项：{available_durations}秒（当前API支持的离散时长）
⚠️  绝对不能使用其他时长值，这是API硬约束

**规划任务**：
请根据内容的叙事需求、复杂程度和系统约束，智能决定：

1. **最佳场景数量**：
   - 在{min_scenes}-{max_scenes}个场景范围内选择
   - 完全基于内容逻辑：分析内容包含多少个独立概念、事件或视觉转换
   - 每个场景都应该有明确的叙事价值

2. **场景时长分配**：
   - 每个场景必须选择{available_durations}秒中的一个
   - 根据场景复杂度和重要性选择：
     * {available_durations[0]}秒：简单场景、过渡场景、概念介绍
     * {available_durations[1]}秒：复杂场景、关键展示、详细说明

3. **叙事结构**：
   - 每个场景的核心内容
   - 场景间的逻辑关系
   - 整体的叙事节奏

**分析维度**：
- 内容复杂度：{user_prompt}包含多少个关键要素？
- 叙事层次：是否需要多个层面的展现？
- 视觉变化：需要多少个不同的视觉场景？
- 时间跨度：故事发生的时间跨度如何？

请返回JSON格式：
{{
    "analysis": {{
        "content_complexity": "simple/moderate/complex",
        "narrative_layers": "描述叙事层次",
        "key_elements": ["关键要素1", "关键要素2", ...],
        "visual_variety_needed": "描述视觉变化需求"
    }},
    "scene_plan": {{
        "total_scenes": 场景总数（智能决定，不受限制）,
        "total_duration": {target_total_duration},
        "scenes": [
            {{
                "scene_number": 1,
                "duration": 5或10,
                "duration_reasoning": "选择该时长的原因",
                "content_focus": "场景核心内容",
                "narrative_purpose": "叙事作用",
                "complexity_level": "simple/moderate/complex"
            }},
            // ... 更多场景
        ]
    }},
    "reasoning": "详细说明为什么选择这个场景数量和分配方案"
}}
"""

        try:
            # 使用LLM进行智能规划
            if self.llm_service:
                # 从 ai_config 中读取工具模型映射
                try:
                    from ....core.ai_config import get_ai_config
                    ai_cfg = get_ai_config()
                    cfg_model = ai_cfg.get_model_for_tool("intelligent_scene_planning")
                    mcfg = ai_cfg.get_model_config(cfg_model) if cfg_model else None
                except Exception:
                    cfg_model = None
                    mcfg = None
                req_model = cfg_model or None
                req_temp = 0.3 if not (mcfg and getattr(mcfg, 'temperature', None) is not None) else float(mcfg.temperature)

                result = await self.llm_service.function_call(
                    messages=[{"role": "user", "content": planning_prompt}],
                    temperature=req_temp,
                    model=req_model,
                    response_format={"type": "json_object"}  # ✅ 确保JSON格式输出
                )
                
                if result.get("content"):
                    import json
                    content = result["content"]
                    self.logger.info(f"🔍 LLM response content preview: {content[:200]}...")
                    
                    try:
                        # 尝试解析JSON响应
                        scene_plan = json.loads(content)
                        self.logger.info(f"✅ Successfully parsed JSON with {len(scene_plan.get('scene_plan', {}).get('scenes', []))} scenes")
                        
                        # 验证和清理数据
                        validated_plan = self._validate_and_clean_plan(scene_plan, target_total_duration)
                        
                        return {
                            "success": True,
                            "approach": "llm_intelligent_planning",
                            "scene_plan": validated_plan,
                            "confidence": 0.9
                        }
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"❌ Failed to parse LLM JSON response: {e}")
                        self.logger.warning(f"🔍 Raw content causing error: {content}")
                        # 如果JSON解析失败，使用智能fallback
                        return await self._intelligent_fallback_planning(user_prompt, target_total_duration, video_style)
                else:
                    self.logger.warning("❌ LLM returned empty content")
                    return await self._intelligent_fallback_planning(user_prompt, target_total_duration, video_style)
            else:
                return await self._intelligent_fallback_planning(user_prompt, target_total_duration, video_style)
                
        except Exception as e:
            self.logger.error(f"Intelligent scene planning failed: {e}")
            return await self._intelligent_fallback_planning(user_prompt, target_total_duration, video_style)
    
    async def _intelligent_fallback_planning(
        self, 
        user_prompt: str, 
        target_total_duration: float, 
        video_style: str
    ) -> Dict[str, Any]:
        """智能fallback规划 - 比硬编码更智能的备用方案"""
        
        # 分析内容特征
        content_analysis = self._analyze_content_features(user_prompt)
        
        # 根据分析结果智能决定场景数量
        if content_analysis["element_count"] <= 2 and content_analysis["complexity_score"] < 3:
            # 简单内容：1-2个场景
            scene_count = min(2, max(1, content_analysis["element_count"]))
        elif content_analysis["element_count"] <= 5 and content_analysis["complexity_score"] < 6:
            # 中等内容：2-4个场景
            scene_count = min(4, max(2, content_analysis["element_count"]))
        else:
            # 复杂内容：动态决定，不受上限限制
            base_scenes = min(8, content_analysis["element_count"])
            if content_analysis["has_temporal_sequence"]:
                scene_count = base_scenes + 2  # 时间序列需要更多场景
            else:
                scene_count = base_scenes
        
        # 智能分配时长
        scenes = []
        
        for i in range(scene_count):
            # 🔧 修复：移除越权的时长计算，只提供分析和建议
            # 🔧 修复：避免division by zero错误
            content_focus = ""
            if content_analysis["elements"] and len(content_analysis["elements"]) > 0:
                content_focus = content_analysis["elements"][i % len(content_analysis["elements"])]
            else:
                content_focus = f"场景内容分析 {i + 1}"
            
            scenes.append({
                "scene_number": i + 1,
                # 🔧 修复：不再计算具体时长，由ConceptPlanner的LLM决策
                "suggested_complexity": "高" if (i == 0 or i == scene_count - 1) else "中",
                "content_focus": content_focus,
                "narrative_purpose": "opening" if i == 0 else ("closing" if i == scene_count - 1 else "development"),
                "complexity_level": content_analysis["complexity_level"],
                # 🔧 移除时长建议，时长决策完全由ConceptPlanner负责
                "importance_level": "关键场景" if (i == 0 or i == scene_count - 1) else "发展场景"
            })
        
        return {
            "success": True,
            "approach": "intelligent_fallback",
            "scene_plan": {
                "analysis": {
                    "content_complexity": content_analysis["complexity_level"],
                    "narrative_layers": f"Identified {content_analysis['element_count']} key elements",
                    "key_elements": content_analysis["elements"],
                    "visual_variety_needed": "Moderate variety based on content analysis"
                },
                "scene_plan": {
                    "total_scenes": scene_count,
                    # 🔧 修复：移除时长相关计算，时长由ConceptPlanner根据API能力决策
                    "scenes": scenes
                },
                "reasoning": f"Intelligent fallback: Based on {content_analysis['element_count']} key elements and complexity score {content_analysis['complexity_score']}, determined {scene_count} scenes provide optimal narrative flow."
            },
            "confidence": 0.75
        }
    
    def _analyze_content_features(self, user_prompt: str) -> Dict[str, Any]:
        """分析内容特征（不依赖LLM的智能分析）"""
        
        # 关键元素检测
        elements = []
        complexity_indicators = []
        
        # 检测关键词和元素
        action_words = ["跑", "跳", "飞", "战斗", "追逐", "逃跑", "爆炸", "碰撞"]
        emotion_words = ["悲伤", "喜悦", "愤怒", "恐惧", "惊讶", "爱"]
        location_words = ["室内", "室外", "森林", "城市", "海边", "山上", "太空", "地下"]
        character_words = ["主角", "英雄", "反派", "朋友", "敌人", "家人"]
        
        for word_list, category in [
            (action_words, "action"), (emotion_words, "emotion"), 
            (location_words, "location"), (character_words, "character")
        ]:
            found_words = [word for word in word_list if word in user_prompt]
            if found_words:
                elements.extend(found_words)
                complexity_indicators.append(category)
        
        # 检测时间序列指示器
        temporal_words = ["然后", "接着", "随后", "最后", "开始", "结束", "过程中"]
        has_temporal = any(word in user_prompt for word in temporal_words)
        
        # 计算复杂度分数
        complexity_score = len(elements) + (2 if has_temporal else 0) + len(user_prompt) // 50
        
        # 确定复杂度级别
        if complexity_score < 3:
            complexity_level = "simple"
        elif complexity_score < 6:
            complexity_level = "moderate"
        else:
            complexity_level = "complex"
        
        return {
            "elements": elements[:10],  # 最多取10个关键元素
            "element_count": len(elements),
            "complexity_score": complexity_score,
            "complexity_level": complexity_level,
            "has_temporal_sequence": has_temporal,
            "content_length": len(user_prompt)
        }
    
    def _validate_and_clean_plan(self, raw_plan: Dict, target_duration: float) -> Dict[str, Any]:
        """验证和清理LLM生成的场景规划"""
        
        try:
            scene_plan = raw_plan.get("scene_plan", {})
            scenes = scene_plan.get("scenes", [])
            
            # 确保场景数量合理（允许1-20个场景，不再硬编码限制）
            if len(scenes) < 1:
                raise ValueError("At least 1 scene required")
            if len(scenes) > 20:
                self.logger.warning(f"Too many scenes ({len(scenes)}), limiting to 20")
                scenes = scenes[:20]
            
            # 重新分配时长以确保总时长匹配
            total_planned_duration = sum(scene.get("duration", 0) for scene in scenes)
            if abs(total_planned_duration - target_duration) > 2:
                # 按比例调整
                scale_factor = target_duration / total_planned_duration
                for scene in scenes:
                    scene["duration"] = round(scene.get("duration", 5) * scale_factor, 1)
                    # 确保每个场景时长在合理范围内
                    scene["duration"] = max(3, min(15, scene["duration"]))
            
            # 更新总场景数
            scene_plan["total_scenes"] = len(scenes)
            scene_plan["total_duration"] = target_duration
            
            return raw_plan
            
        except Exception as e:
            self.logger.error(f"Failed to validate scene plan: {e}")
            # 返回最简单的规划
            return {
                "analysis": {
                    "content_complexity": "moderate",
                    "narrative_layers": "Basic structure",
                    "key_elements": ["main content"],
                    "visual_variety_needed": "Standard variety"
                },
                "scene_plan": {
                    "total_scenes": 1,
                    "total_duration": target_duration,
                    "scenes": [{
                        "scene_number": 1,
                        "duration": target_duration,
                        "content_focus": "Complete content in single scene",
                        "narrative_purpose": "comprehensive",
                        "complexity_level": "moderate"
                    }]
                },
                "reasoning": "Fallback to single scene due to validation failure"
            }
    
    async def _optimize_scene_distribution(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """优化场景分布"""
        # TODO: 实现场景分布优化逻辑
        return {"status": "not_implemented"}
    
    async def _validate_scene_plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """验证场景规划"""
        # TODO: 实现场景规划验证逻辑
        return {"status": "not_implemented"}
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "analyze_and_plan_scenes":
            if not parameters.get("user_prompt"):
                raise ToolValidationError("user_prompt is required")
            if not parameters.get("target_total_duration"):
                raise ToolValidationError("target_total_duration is required")

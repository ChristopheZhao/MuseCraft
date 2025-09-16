"""
Narrative Structure Generation Tool - 专门用于叙事结构生成的原子性工具
"""

import time
from typing import Dict, Any, List, Union
from ..base_tool import BaseTool, ToolMetadata, ToolType, ToolInput, ToolOutput, ToolError


class NarrativeStructureGenerationTool(BaseTool):
    """
    叙事结构生成工具 - 专门负责整体叙事结构设计
    原子性功能：基于场景列表和概念计划生成整体叙事结构
    """
    
    def __init__(self, metadata=None, config=None):
        if metadata is None:
            metadata = ToolMetadata(
                name="narrative_structure_generation_tool",
                version="1.0.0",
                description="专门用于生成整体叙事结构的原子性工具",
                tool_type=ToolType.AI_SERVICE,
                author="MuseCraft MAS Team",
                capabilities=[
                    "narrative_flow_design",
                    "scene_connection_analysis",
                    "pacing_strategy_creation",
                    "json_structured_output"
                ],
                dependencies=[]  # 🚀 移除工具依赖，直接使用服务层
            )
        super().__init__(metadata)
        self._ai_client = None
        self._config = config or {}
    
    def _initialize(self):
        """初始化工具特定资源"""
        self.logger.info("📖 叙事结构生成工具初始化...")
    
    async def _ensure_ai_client(self):
        """确保AI客户端可用 - 直接使用服务层"""
        if not self._ai_client:
            try:
                from ....services.ai_client import AIClient
                self._ai_client = AIClient()
                self.logger.info("🤖 AI服务客户端初始化成功")
            except Exception as e:
                self.logger.error(f"AI服务客户端初始化失败: {e}")
                raise ToolError(f"AI服务不可用: {e}", self.metadata.name)
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行叙事结构生成 - 唯一功能"""
        await self._ensure_ai_client()
        
        parameters = tool_input.parameters
        scenes = parameters["scenes"]
        concept_plan = parameters["concept_plan"]
        
        prompt = self._build_narrative_structure_prompt(scenes, concept_plan)
        
        # 调用AI服务
        # 从 ai_config 读取工具模型映射（参数可覆盖）
        try:
            from ....core.ai_config import get_ai_config
            ai_cfg = get_ai_config()
            cfg_model = ai_cfg.get_model_for_tool("narrative_structure_generation_tool")
            mcfg = ai_cfg.get_model_config(cfg_model) if cfg_model else None
        except Exception:
            cfg_model = None
            mcfg = None
        req_model = parameters.get("model") or cfg_model
        req_temp = parameters.get("temperature", (mcfg.temperature if mcfg and getattr(mcfg, 'temperature', None) is not None else 0.6))
        req_max_tokens = parameters.get("max_tokens", (mcfg.max_tokens if mcfg and getattr(mcfg, 'max_tokens', None) is not None else 800))

        response = await self._ai_client.generate_text(
            prompt=prompt,
            model=req_model,
            temperature=req_temp,
            max_tokens=int(req_max_tokens)
        )
        
        return response
    
    def _build_narrative_structure_prompt(self, scenes: List[Any], concept_plan: Dict[str, Any]) -> str:
        """构建叙事结构生成提示词"""
        scenes_summary = []
        for i, scene in enumerate(scenes):
            # 处理SceneData对象或字典
            if hasattr(scene, 'title'):  # SceneData对象
                title = getattr(scene, 'title', '')
                duration = getattr(scene, 'duration', '')
                description = getattr(scene, 'description', '')
            else:  # 字典格式
                title = scene.get('title', '')
                duration = scene.get('duration', '')
                description = scene.get('description', '')
            
            scenes_summary.append(f"场景{i+1}: {title} ({duration}秒) - {description}")
        
        return f"""
        基于概念计划和场景列表，设计整体叙事结构：
        
        ## 概念计划
        - 整体概述: {concept_plan.get('overview', '')}
        - 视觉风格: {concept_plan.get('visual_style', '')}
        - 情绪基调: {concept_plan.get('mood_and_tone', '')}
        - 目标受众: {concept_plan.get('target_audience', '')}
        - 核心信息: {concept_plan.get('key_messages', [])}
        
        ## 场景列表
        {chr(10).join(scenes_summary)}
        
        ## 设计要求
        请生成包含以下结构的JSON格式叙事结构：
        {{
            "narrative_flow": {{
                "pacing_strategy": "整体节奏策略（如：渐进式、高潮式、平稳式）",
                "mood_and_tone": "情绪基调的发展轨迹",
                "transition_philosophy": "场景间过渡的设计理念"
            }},
            "scene_connections": [
                {{
                    "from_scene": 1,
                    "to_scene": 2,
                    "transition_type": "过渡类型（如：切换、淡入淡出、连贯）",
                    "connection_rationale": "连接的逻辑和理由",
                    "visual_continuity": "视觉连续性要求"
                }}
            ],
            "story_arc": {{
                "introduction": "开场部分的叙事功能",
                "development": "发展部分的叙事功能", 
                "climax": "高潮部分的叙事功能",
                "resolution": "结尾部分的叙事功能"
            }},
            "thematic_elements": {{
                "main_theme": "主要主题",
                "supporting_themes": ["支撑主题1", "支撑主题2"],
                "emotional_journey": "情感旅程描述"
            }}
        }}
        
        注意：
        1. 确保叙事结构支持核心信息的传达
        2. 考虑目标受众的观看体验
        3. 平衡各场景的重要性和时长
        4. 创造有吸引力的情感弧线
        """
    
    def get_available_actions(self) -> List[str]:
        """获取可用操作 - 只有一个原子性操作"""
        return ["generate_narrative_structure"]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """获取操作输入模式"""
        if action == "generate_narrative_structure":
            return {
                "type": "object",
                "properties": {
                    "scenes": {
                        "type": "array",
                        "description": "场景列表，包含各场景的基本信息"
                    },
                    "concept_plan": {
                        "type": "object",
                        "description": "概念计划对象，提供整体创意指导"
                    },
                    "model": {
                        "type": "string",
                        "description": "使用的AI模型"
                    },
                    "temperature": {
                        "type": "number",
                        "description": "生成温度",
                        "default": 0.6
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "最大token数",
                        "default": 800
                    }
                },
                "required": ["scenes", "concept_plan"]
            }
        else:
            raise ToolError(f"叙事结构生成工具只支持generate_narrative_structure操作: {action}", self.metadata.name)
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            await self._ensure_ai_client()
            return {
                "healthy": True,
                "service": "narrative_structure_generation_tool",
                "capabilities": self.metadata.capabilities
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}
    
    async def cleanup(self):
        """清理资源"""
        if self._ai_client and hasattr(self._ai_client, 'close'):
            await self._ai_client.close()
        self.logger.info("📖 叙事结构生成工具资源已清理")

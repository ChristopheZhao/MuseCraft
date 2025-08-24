"""
Scene Script Generation Tool - 专门用于场景脚本生成的原子性工具
"""

import time
from typing import Dict, Any, List
from ..base_tool import BaseTool, ToolMetadata, ToolType, ToolInput, ToolOutput, ToolError


class SceneScriptGenerationTool(BaseTool):
    """
    场景脚本生成工具 - 专门负责单个场景脚本生成
    原子性功能：基于场景信息和概念计划生成详细的场景脚本
    """
    
    def __init__(self, metadata=None, config=None):
        if metadata is None:
            metadata = ToolMetadata(
                name="scene_script_generation_tool",
                version="1.0.0",
                description="专门用于生成单个场景脚本的原子性工具",
                tool_type=ToolType.AI_SERVICE,
                author="MuseCraft MAS Team",
                capabilities=[
                    "scene_script_generation",
                    "narrative_structure_design",
                    "scene_design_creation",
                    "json_structured_output"
                ],
                dependencies=[]  # 🚀 移除工具依赖，直接使用服务层
            )
        super().__init__(metadata)
        self._ai_client = None
        self._config = config or {}
    
    def _initialize(self):
        """初始化工具特定资源"""
        self.logger.info("✍️ 场景脚本生成工具初始化...")
    
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
        """执行场景脚本生成 - 唯一功能"""
        await self._ensure_ai_client()
        
        parameters = tool_input.parameters
        scene_data = parameters["scene_data"]
        concept_plan = parameters["concept_plan"]
        
        prompt = self._build_scene_script_prompt(scene_data, concept_plan)
        
        # 调用AI服务
        response = await self._ai_client.generate_text(
            prompt=prompt,
            model=parameters.get("model"),
            temperature=parameters.get("temperature", 0.7),
            max_tokens=parameters.get("max_tokens", 1500)
        )
        
        return response
    
    def _build_scene_script_prompt(self, scene_data: Dict[str, Any], concept_plan: Dict[str, Any]) -> str:
        """构建场景脚本生成提示词"""
        return f"""
        基于概念计划和场景信息，生成详细的场景脚本：
        
        ## 概念计划
        - 整体概述: {concept_plan.get('overview', '')}
        - 视觉风格: {concept_plan.get('visual_style', '')}
        - 情绪基调: {concept_plan.get('mood_and_tone', '')}
        - 目标受众: {concept_plan.get('target_audience', '')}
        - 核心信息: {concept_plan.get('key_messages', [])}
        
        ## 场景信息
        - 场景编号: {scene_data.get('scene_number', '')}
        - 场景标题: {scene_data.get('title', '')}
        - 场景描述: {scene_data.get('description', '')}
        - 时长: {scene_data.get('duration', '')}秒
        - 视觉描述: {scene_data.get('visual_description', '')}
        - 氛围描述: {scene_data.get('mood_and_atmosphere', '')}
        
        ## 生成要求
        请生成包含以下结构的JSON格式脚本：
        {{
            "scene_number": {scene_data.get('scene_number', '')},
            "script": {{
                "script_text": "详细的脚本文本，描述场景中发生的事情",
                "voice_over": "配音文本，如果需要的话",
                "scene_direction": "场景指导说明"
            }},
            "narrative_structure": {{
                "opening_state": "场景开始时的状态",
                "main_action": "场景中的主要动作或事件",
                "closing_state": "场景结束时的状态",
                "story_function": "此场景在整体故事中的功能"
            }},
            "scene_design": {{
                "key_subjects": ["场景中的主要元素和对象"],
                "scene_setting": "场景的环境设置描述",
                "visual_style_notes": "视觉风格的具体说明",
                "composition_requirements": "构图和镜头要求",
                "continuity_elements": ["与其他场景保持连续性的元素"]
            }}
        }}
        
        注意：
        1. 脚本要具体生动，适合视频制作
        2. 考虑场景在整体视频中的位置和作用
        3. 确保与概念计划的一致性
        4. 提供足够的视觉和技术指导
        """
    
    def get_available_actions(self) -> List[str]:
        """获取可用操作 - 只有一个原子性操作"""
        return ["generate_scene_script"]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """获取操作输入模式"""
        if action == "generate_scene_script":
            return {
                "type": "object",
                "properties": {
                    "scene_data": {
                        "type": "object",
                        "description": "场景数据对象，包含场景的基本信息"
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
                        "default": 0.7
                    },
                    "max_tokens": {
                        "type": "integer", 
                        "description": "最大token数",
                        "default": 1500
                    }
                },
                "required": ["scene_data", "concept_plan"]
            }
        else:
            raise ToolError(f"场景脚本生成工具只支持generate_scene_script操作: {action}", self.metadata.name)
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            await self._ensure_ai_client()
            return {
                "healthy": True,
                "service": "scene_script_generation_tool",
                "capabilities": self.metadata.capabilities
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}
    
    async def cleanup(self):
        """清理资源"""
        if self._ai_client and hasattr(self._ai_client, 'close'):
            await self._ai_client.close()
        self.logger.info("✍️ 场景脚本生成工具资源已清理")
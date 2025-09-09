"""
Concept Generation Tool - 专门用于概念规划生成的原子性工具
"""

import time
from typing import Dict, Any, List
from ..base_tool import BaseTool, ToolMetadata, ToolType, ToolInput, ToolOutput, ToolError


class ConceptGenerationTool(BaseTool):
    """
    概念生成工具 - 专门负责视频概念规划生成
    原子性功能：将用户需求转换为结构化的视频概念计划
    """
    
    def __init__(self, metadata=None, config=None):
        if metadata is None:
            metadata = ToolMetadata(
                name="concept_generation_tool",
                version="1.0.0",
                description="专门用于生成视频概念规划的原子性工具",
                tool_type=ToolType.AI_SERVICE,
                author="MuseCraft MAS Team",
                capabilities=[
                    "concept_planning",
                    "scene_breakdown", 
                    "creative_direction",
                    "json_structured_output"
                ],
                dependencies=[]  # 🚀 移除工具依赖，直接使用服务层
            )
        super().__init__(metadata)
        self._llm_service = None
        self._config = config or {}
    
    def _initialize(self):
        """初始化工具特定资源"""
        self.logger.info("🎭 概念生成工具初始化...")
    
    async def _ensure_llm_service(self):
        """确保LLM服务可用 - 直接使用ZhipuClientTool（避免ServiceManager依赖）"""
        if not self._llm_service:
            try:
                from .zhipu_client import ZhipuClientTool
                self._llm_service = ZhipuClientTool()
                self._llm_service._initialize()
                if not self._llm_service._functional:
                    raise RuntimeError("ZhipuClientTool not functional (check GLM_API_KEY)")
                self.logger.info("🤖 AI服务客户端初始化成功")
            except Exception as e:
                self.logger.error(f"LLM服务初始化失败: {e}")
                raise ToolError(f"AI服务不可用: {e}", self.metadata.name)
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行概念生成 - 唯一功能"""
        await self._ensure_llm_service()
        
        parameters = tool_input.parameters
        
        # 构建概念生成提示词 - MAS智能风格决策
        prompt = self._build_concept_prompt(
            user_prompt=parameters["user_prompt"],
            style_preference=parameters.get("style_preference"),  # 可选的用户风格偏好提示
            duration=parameters.get("duration", 60),
            aspect_ratio=parameters.get("aspect_ratio", "16:9")
        )
        
        # 调用ZhipuClientTool进行概念生成，要求返回JSON对象
        try:
            from ..base_tool import ToolInput
            result = await self._llm_service.execute(ToolInput(
                action="chat_completion",
                parameters={
                    "messages": [{"role": "user", "content": prompt}],
                    "model": parameters.get("model", "glm-4-plus"),
                    "temperature": parameters.get("temperature", 0.7),
                    "max_tokens": parameters.get("max_tokens", 4000),
                    "response_format": {"type": "json_object"}
                }
            ))
            # ZhipuClientTool返回的是ToolOutput对象，需要检查success并获取result
            if hasattr(result, 'success') and not result.success:
                raise ToolError(f"ZhipuClient failed: {result.error}")
            # result.result包含实际的字典响应
            actual_result = result.result if hasattr(result, 'result') else result
            content = (actual_result or {}).get("content", "").strip()
        except Exception as e:
            raise ToolError(f"LLM service failed: {str(e)}", self.metadata.name)

        # 🚨 严格处理LLM响应 - 不使用fallback以便问题排查
        
        # 检查是否为空响应
        if not content:
            raise ToolError("LLM returned empty content - cannot proceed with concept generation", self.metadata.name)
        
        # 解析JSON内容
        try:
            import json
            parsed_data = json.loads(content)
            
            # 验证关键字段
            if not parsed_data.get('scenes') or len(parsed_data.get('scenes', [])) == 0:
                raise ToolError("LLM returned invalid concept data - no scenes generated", self.metadata.name)
            
            self.logger.info(f"🎭 解析概念数据成功，包含 {len(parsed_data.get('scenes', []))} 个场景")
            return parsed_data
            
        except json.JSONDecodeError as e:
            self.logger.error(f"LLM返回无效JSON: {e}")
            self.logger.error(f"原始内容: {content[:500]}")
            raise ToolError(f"LLM returned invalid JSON format: {str(e)}", self.metadata.name)
    
    def _build_concept_prompt(self, user_prompt: str, style_preference: str, duration: int, aspect_ratio: str) -> str:
        """使用模板管理器构建智能风格决策提示词"""
        from ...prompts.template_manager import get_template_manager
        
        template_manager = get_template_manager()
        
        # 使用增强的概念生成模板
        return template_manager.render_template(
            "enhanced_concept_generation",
            {
                "user_prompt": user_prompt,
                "style_preference": style_preference or "",
                "duration": duration,
                "aspect_ratio": aspect_ratio
            }
        )
    
    def get_available_actions(self) -> List[str]:
        """获取可用操作 - 只有一个原子性操作"""
        return ["generate_concept"]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """获取操作输入模式"""
        if action == "generate_concept":
            return {
                "type": "object",
                "properties": {
                    "user_prompt": {
                        "type": "string", 
                        "description": "用户的视频需求描述"
                    },
                    "style_preference": {
                        "type": "string", 
                        "description": "可选的用户风格偏好提示（如：我希望温馨一点、要专业一些等）"
                    },
                    "duration": {
                        "type": "integer", 
                        "description": "目标时长（秒）",
                        "default": 60
                    },
                    "aspect_ratio": {
                        "type": "string", 
                        "description": "画面比例",
                        "default": "16:9"
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
                        "default": 4000
                    }
                },
                "required": ["user_prompt"]
            }
        else:
            raise ToolError(f"概念生成工具只支持generate_concept操作: {action}", self.metadata.name)
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            await self._ensure_llm_service()
            return {
                "healthy": True,
                "service": "concept_generation_tool",
                "capabilities": self.metadata.capabilities
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}
    
    async def cleanup(self):
        """清理资源"""
        # 当前通过HTTP客户端按请求构造，无长连资源；保留日志
        self.logger.info("🎭 概念生成工具资源已清理")

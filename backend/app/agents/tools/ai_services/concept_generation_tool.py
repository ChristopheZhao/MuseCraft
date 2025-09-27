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
        self._config = config or {}
    
    def _initialize(self):
        """初始化工具特定资源"""
        self.logger.info("🎭 概念生成工具初始化...")
    
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行概念生成 - 唯一功能"""
        parameters = tool_input.parameters
        
        # 构建概念生成提示词 - MAS智能风格决策
        prompt = self._build_concept_prompt(
            user_prompt=parameters["user_prompt"],
            style_preference=parameters.get("style_preference"),  # 可选的用户风格偏好提示
            duration=parameters.get("duration", 60),
            aspect_ratio=parameters.get("aspect_ratio", "16:9")
        )
        
        # 调用LLM进行概念生成，要求返回JSON对象（供应商无关）
        try:
            from ..base_tool import ToolInput as TI
            from ..tool_registry import get_tool_registry
            # 从 ai_config 读取工具模型映射（可被参数覆盖）
            try:
                from ....core.ai_config import get_ai_config
                ai_cfg = get_ai_config()
                cfg_model = ai_cfg.get_model_for_tool("concept_generation_tool")
                mcfg = ai_cfg.get_model_config(cfg_model) if cfg_model else None
                provider_name = ai_cfg.get_model_provider(cfg_model) if cfg_model else None
            except Exception:
                cfg_model = None
                mcfg = None
                provider_name = None
            req_model = parameters.get("model") or cfg_model or None
            req_temp = parameters.get("temperature", (mcfg.temperature if mcfg and getattr(mcfg, 'temperature', None) is not None else 0.7))
            req_max_tokens = parameters.get("max_tokens", (mcfg.max_tokens if mcfg and getattr(mcfg, 'max_tokens', None) is not None else 4000))
            # 选择provider工具
            prov_alias = {"zhipu": "zhipu_client", "openai": "openai_client", "kimi": "kimi_client"}
            provider_tool = prov_alias.get(provider_name or "zhipu", "zhipu_client")
            provider = get_tool_registry().get_tool(provider_tool)

            # 优先使用 json_completion 获取严格JSON
            exec_res = await provider.execute(TI(action="json_completion", parameters={
                "prompt": prompt,
                "model": req_model,
                "temperature": req_temp,
                "max_tokens": int(req_max_tokens)
            }))
            payload = getattr(exec_res, 'result', exec_res)
            content = None
            parsed = None
            if isinstance(payload, dict):
                parsed = payload.get("json_result")
                content = payload.get("content") or payload.get("raw_content")
        except Exception as e:
            raise ToolError(f"LLM service failed: {str(e)}", self.metadata.name)

        # 🚨 严格处理LLM响应 - 不使用fallback以便问题排查
        
        # 检查是否为空响应
        if parsed is None and not content:
            raise ToolError("LLM returned empty content - cannot proceed with concept generation", self.metadata.name)
        
        # 解析JSON内容
        try:
            import json
            parsed_data = parsed if isinstance(parsed, dict) else json.loads(content)
            
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
        from ....core.video_config_manager import get_video_config
        from ....core.config import settings
        
        template_manager = get_template_manager()
        video_config = get_video_config()
        provider_config = video_config.get_current_provider_config()
        raw_capabilities = provider_config.duration_capabilities or getattr(
            settings, "AVAILABLE_SCENE_DURATIONS", [5, 10]
        )
        duration_capabilities = sorted({int(cap) for cap in raw_capabilities if cap}) or [5, 10]
        scene_count_min = getattr(settings, "SCENE_COUNT_RANGE_MIN", 3)
        scene_count_max = getattr(settings, "SCENE_COUNT_RANGE_MAX", 10)
        optimal_scene_count = video_config.calculate_optimal_scene_count(duration)
        optimal_scene_count = max(scene_count_min, min(optimal_scene_count, scene_count_max))
        
        # 使用增强的概念生成模板
        return template_manager.render_template(
            "enhanced_concept_generation",
            {
                "user_prompt": user_prompt,
                "style_preference": style_preference or "",
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "duration_capabilities": duration_capabilities,
                "scene_count_min": scene_count_min,
                "scene_count_max": scene_count_max,
                "optimal_scene_count": optimal_scene_count,
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

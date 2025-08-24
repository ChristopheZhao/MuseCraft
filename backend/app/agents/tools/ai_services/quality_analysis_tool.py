"""
Quality Analysis Tool - 专门用于视频质量分析的原子性工具
"""

import time
from typing import Dict, Any, List
from ..base_tool import BaseTool, ToolMetadata, ToolType, ToolInput, ToolOutput, ToolError


class QualityAnalysisTool(BaseTool):
    """
    质量分析工具 - 专门负责视频质量分析
    原子性功能：分析视频是否符合原始需求和质量标准
    """
    
    def __init__(self, metadata=None, config=None):
        if metadata is None:
            metadata = ToolMetadata(
                name="quality_analysis_tool",
                version="1.0.0",
                description="专门用于视频质量分析的原子性工具",
                tool_type=ToolType.AI_SERVICE,
                author="MuseCraft MAS Team",
                capabilities=[
                    "video_quality_analysis",
                    "requirement_compliance_check",
                    "improvement_suggestions",
                    "json_structured_output"
                ],
                dependencies=[]  # 🚀 移除工具依赖，直接使用服务层
            )
        super().__init__(metadata)
        self._ai_client = None
        self._config = config or {}
    
    def _initialize(self):
        """初始化工具特定资源"""
        self.logger.info("🔍 质量分析工具初始化...")
    
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
        """执行质量分析 - 唯一功能"""
        await self._ensure_ai_client()
        
        parameters = tool_input.parameters
        
        # 构建质量分析提示词
        prompt = self._build_quality_analysis_prompt(
            video_data=parameters["video_data"],
            original_requirements=parameters["original_requirements"],
            quality_criteria=parameters.get("quality_criteria", {})
        )
        
        # 调用AI服务
        response = await self._ai_client.generate_text(
            prompt=prompt,
            model=parameters.get("model"),
            temperature=parameters.get("temperature", 0.3),  # 分析类任务用较低温度
            max_tokens=parameters.get("max_tokens", 500)
        )
        
        return response
    
    def _build_quality_analysis_prompt(self, video_data: Dict[str, Any], original_requirements: Dict[str, Any], quality_criteria: Dict[str, Any]) -> str:
        """构建质量分析提示词"""
        return f"""
        作为专业的视频质量检查专家，请对生成的视频进行全面的质量分析：
        
        ## 原始需求
        用户需求: {original_requirements.get('user_prompt', '')}
        目标风格: {original_requirements.get('visual_style', '')}
        目标时长: {original_requirements.get('duration', '')}秒
        目标受众: {original_requirements.get('target_audience', '')}
        核心信息: {original_requirements.get('key_messages', [])}
        
        ## 生成的视频信息
        场景数量: {video_data.get('total_scenes', '')}
        实际时长: {video_data.get('actual_duration', '')}秒
        文件大小: {video_data.get('file_size', '')}
        分辨率: {video_data.get('resolution', '')}
        视频质量: {video_data.get('video_quality', '')}
        
        ## 质量标准
        技术质量: {quality_criteria.get('technical_quality', '高清、流畅')}
        内容质量: {quality_criteria.get('content_quality', '符合需求、连贯性')}
        创意质量: {quality_criteria.get('creative_quality', '创新性、吸引力')}
        
        ## 分析要求
        请从以下维度进行分析并生成JSON格式报告：
        {{
            "overall_score": 总体分数(0-100),
            "quality_assessment": {{
                "technical_quality": {{
                    "score": 技术质量分数(0-100),
                    "video_resolution": "分辨率评估",
                    "audio_quality": "音频质量评估", 
                    "rendering_quality": "渲染质量评估",
                    "issues": ["技术问题1", "技术问题2"],
                    "strengths": ["技术优势1", "技术优势2"]
                }},
                "content_quality": {{
                    "score": 内容质量分数(0-100),
                    "requirement_compliance": 需求符合度(0-100),
                    "narrative_coherence": 叙事连贯性(0-100),
                    "message_clarity": 信息传达清晰度(0-100),
                    "target_audience_fit": 目标受众适配度(0-100)
                }},
                "creative_quality": {{
                    "score": 创意质量分数(0-100),
                    "innovation_level": 创新水平(0-100),
                    "visual_appeal": 视觉吸引力(0-100),
                    "engagement_potential": 观众参与潜力(0-100)
                }}
            }},
            "compliance_check": {{
                "duration_match": 时长是否符合要求(true/false),
                "style_consistency": 风格是否一致(true/false),
                "message_delivery": 核心信息是否传达(true/false),
                "audience_appropriate": 是否适合目标受众(true/false)
            }},
            "recommendations": [
                {{
                    "category": "改进类别（技术/内容/创意）",
                    "suggestion": "具体建议",
                    "priority": "high/medium/low",
                    "estimated_effort": "预估工作量"
                }}
            ],
            "pass_criteria": 是否达到发布标准(true/false),
            "summary": "质量分析总结"
        }}
        
        注意：
        1. 分析要客观公正，基于实际情况
        2. 建议要具体可行，有操作性
        3. 考虑成本效益，优先级合理
        4. 总结要简洁明了，突出关键点
        """
    
    def get_available_actions(self) -> List[str]:
        """获取可用操作 - 只有一个原子性操作"""
        return ["analyze_quality"]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """获取操作输入模式"""
        if action == "analyze_quality":
            return {
                "type": "object",
                "properties": {
                    "video_data": {
                        "type": "object",
                        "description": "视频数据信息，包含技术参数和生成结果"
                    },
                    "original_requirements": {
                        "type": "object",
                        "description": "原始需求信息，用于对比分析"
                    },
                    "quality_criteria": {
                        "type": "object",
                        "description": "质量标准定义",
                        "default": {}
                    },
                    "model": {
                        "type": "string",
                        "description": "使用的AI模型"
                    },
                    "temperature": {
                        "type": "number",
                        "description": "生成温度",
                        "default": 0.3
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "最大token数",
                        "default": 500
                    }
                },
                "required": ["video_data", "original_requirements"]
            }
        else:
            raise ToolError(f"质量分析工具只支持analyze_quality操作: {action}", self.metadata.name)
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            await self._ensure_ai_client()
            return {
                "healthy": True,
                "service": "quality_analysis_tool",
                "capabilities": self.metadata.capabilities
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}
    
    async def cleanup(self):
        """清理资源"""
        if self._ai_client and hasattr(self._ai_client, 'close'):
            await self._ai_client.close()
        self.logger.info("🔍 质量分析工具资源已清理")
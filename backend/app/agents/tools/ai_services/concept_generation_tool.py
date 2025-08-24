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
        self._ai_client = None
        self._config = config or {}
    
    def _initialize(self):
        """初始化工具特定资源"""
        self.logger.info("🎭 概念生成工具初始化...")
    
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
        """执行概念生成 - 唯一功能"""
        await self._ensure_ai_client()
        
        parameters = tool_input.parameters
        
        # 构建概念生成提示词 - MAS智能风格决策
        prompt = self._build_concept_prompt(
            user_prompt=parameters["user_prompt"],
            style_preference=parameters.get("style_preference"),  # 可选的用户风格偏好提示
            duration=parameters.get("duration", 60),
            aspect_ratio=parameters.get("aspect_ratio", "16:9")
        )
        
        # 调用AI服务
        response = await self._ai_client.generate_text(
            prompt=prompt,
            model=parameters.get("model", "glm-4-plus"),  # 🔧 提供默认模型
            temperature=parameters.get("temperature", 0.7),
            max_tokens=parameters.get("max_tokens", 4000),
            response_format={"type": "json_object"}
        )
        
        # 🔧 修复：解析JSON内容
        try:
            import json
            content = response.get('content', '{}')
            parsed_data = json.loads(content)
            
            self.logger.info(f"🎭 解析概念数据成功，包含 {len(parsed_data.get('scenes', []))} 个场景")
            return parsed_data
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {e}")
            self.logger.error(f"原始内容: {response.get('content', '')[:200]}")
            
            # 返回基础结构，包含空场景列表
            return {
                "overview": "JSON解析失败，使用默认概念",
                "scenes": [],
                "intelligent_style_design": {},
                "success": False,
                "error": str(e)
            }
    
    def _build_concept_prompt(self, user_prompt: str, style_preference: str, duration: int, aspect_ratio: str) -> str:
        """构建智能风格决策提示词 - MAS核心设计"""
        
        # 用户风格偏好处理
        style_hint = ""
        if style_preference:
            style_hint = f"""
## 用户风格偏好提示
{style_preference}
（以上仅作参考，请基于内容需求进行专业的风格决策优化）"""

        return f"""
作为专业的视频创意总监，请基于用户需求智能设计最适合的视频风格并制定详细概念计划。

## 创作需求
{user_prompt}
{style_hint}

## 专业视频风格决策体系

### 表现形式维度
- **真人实拍**: 纪录片式拍摄、访谈对话、现场记录、生活场景
- **动画制作**: 2D手绘动画、3D渲染动画、定格动画、白板解说动画
- **混合媒体**: 真人+动画结合、屏幕录制+解说、图文+动效

### 叙事风格维度  
- **纪录片式**: 观察式记录、参与式互动、解说式教育、诗意式表达
- **商业推广式**: 企业形象展示、产品功能演示、客户见证分享
- **电影叙事式**: 戏剧化情节、角色发展弧线、情绪渲染引导

### 制作品味维度
- **极简主义**: 去装饰化设计、功能导向、留白美学、简洁有力
- **精致奢华**: 高制作价值、细节丰富、质感突出、专业水准
- **真实质朴**: 手持摄影质感、自然光线、未经雕琢、亲切自然

### 情感基调维度
- **专业权威**: 可信度高、逻辑清晰、数据支撑、理性说服
- **温馨亲和**: 情感共鸣、人文关怀、温暖色调、贴近生活  
- **活力动感**: 节奏明快、视觉冲击、年轻时尚、充满活力
- **神秘艺术**: 意境深远、视觉美学、创意独特、引人深思

请基于以上专业体系，智能分析内容特质，创造性组合最适合的风格方案。

## 技术制作约束
- 目标时长：{duration}秒  
- 画面比例：{aspect_ratio}
        
## 输出要求
请生成包含以下结构的JSON格式概念计划（重点包含智能风格决策）：
{{
    "overview": "整体概念概述",
    "intelligent_style_design": {{
        "style_name": "为这个视频创造的独特风格名称",
        "style_description": "风格的详细描述和特点",
        "visual_approach": "选择的表现形式（真人实拍/动画制作/混合媒体）",
        "narrative_style": "选择的叙事风格（纪录片式/商业推广式/电影叙事式）",
        "production_taste": "选择的制作品味（极简主义/精致奢华/真实质朴）",
        "emotional_tone": "选择的情感基调（专业权威/温馨亲和/活力动感/神秘艺术）",
        "style_reasoning": "选择此风格组合的专业理由和预期效果"
    }},
    "target_audience": "目标受众分析",
    "key_messages": ["核心信息1", "核心信息2"],
    "scenes": [
        {{
            "scene_number": 1,
            "title": "场景标题", 
            "description": "场景描述",
            "duration": 场景时长,
            "visual_description": "符合智能风格设计的视觉描述",
            "mood_and_atmosphere": "氛围描述"
        }}
    ],
    "success": true
}}

注意：
1. intelligent_style_design是核心输出，体现MAS智能决策能力
2. 确保场景总时长等于目标时长，场景数量适中（3-7个场景）  
3. 所有场景描述要与intelligent_style_design保持一致
        """
    
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
                        "description": "可选的用户风格偏好提示（如：我希望温馨一点、要专业一些等）",
                        "required": false
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
            await self._ensure_ai_client()
            return {
                "healthy": True,
                "service": "concept_generation_tool",
                "capabilities": self.metadata.capabilities
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}
    
    async def cleanup(self):
        """清理资源"""
        if self._ai_client and hasattr(self._ai_client, 'close'):
            await self._ai_client.close()
        self.logger.info("🎭 概念生成工具资源已清理")
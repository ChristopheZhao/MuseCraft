"""
Agent工具分配系统 - 为不同Agent提供专门的工具列表
"""

from typing import Dict, List, Set
from enum import Enum

from ...models import AgentType


class ToolCategory(Enum):
    """工具类别枚举"""
    AI_SERVICE = "ai_service"
    MEDIA_PROCESSING = "media_processing"
    STORAGE = "storage"
    ANALYSIS = "analysis"
    COMPOSITION = "composition"
    QUALITY = "quality"
    WORKFLOW = "workflow"


class AgentToolAllocator:
    """
    Agent工具分配器
    
    职责：
    - 为每个Agent类型定义专门的工具列表
    - 避免工具过载和不相关工具的干扰
    - 支持工具继承和覆盖
    """
    
    def __init__(self):
        # 定义每个Agent类型的专门工具列表
        self._agent_tool_mapping = {
            
            # 概念规划Agent - 纯LLM原生能力，无需外部工具
            AgentType.CONCEPT_PLANNER: [],

            # 项目级Series Planner - 纯策划，不调用工具
            AgentType.SERIES_PLANNER: [],
            
            # 脚本编写Agent - 文本生成和叙事分析
            AgentType.SCRIPT_WRITER: [
                "script_generation",                 # 脚本生成 - 匹配注册名称
                "scene_script_generation_tool",      # 场景脚本生成 - 匹配注册名称
                "scene_continuity_analysis_tool",    # 场景连续性分析 - 匹配注册名称
                "narrative_structure_generation_tool" # 叙事结构生成 - 匹配注册名称
            ],
            
            # 图像生成Agent - 视觉创作和图像处理
            AgentType.IMAGE_GENERATOR: [
                "image_generation",             # 图像生成工具（业务逻辑封装）
                "consistency_tool",             # 一致性提示资产查询
                # Image 阶段不做连续性判定，移除 continuity 分析相关工具
            ],
            
            # 视频生成Agent - 简化工具集合
            AgentType.VIDEO_GENERATOR: [
                "video_generation",                    # 视频生成（核心工具）
                "image_generation",                    # 补充图像生成（用于敏感图替换）
                "scene_continuity_preparation",       # 连续性准备（组合工具）
                "consistency_tool",                   # 一致性资产查询与注册
                "file_storage_tool"                   # 文件存储
            ],
            
            # 音频生成Agent - 音频创作和处理
            AgentType.AUDIO_GENERATOR: [
                "suno_client",                 # 背景音乐生成（已注册工具名）
                "audio_analysis_tool",        # 音频分析（静音/截断点/能量）
                "audio_processor",             # 音频后处理（时长/淡入淡出/循环）
                "ffmpeg_tool",                 # 媒体组合（视频加音频）
                "file_storage_tool"            # 文件持久化/下载
            ],

            # 配音合成Agent
            AgentType.VOICE_SYNTHESIZER: [
                "voice_synth_tool",
                "audio_processor",
                "audio_analysis_tool",
                "file_storage_tool",
            ],
            
            # 视频合成Agent - 媒体组合和渲染
            AgentType.VIDEO_COMPOSER: [
                # 使用已注册、可用的工具：ffmpeg 进行合成、file_storage 做本地URL
                "ffmpeg_tool",
                "audio_processor",
                "file_storage_tool"
            ],
            
            # 质量检查Agent - 质量评估和优化
            AgentType.QUALITY_CHECKER: [
                "quality_analysis_tool",        # 质量分析 - 匹配注册名称
                "content_safety_check",         # 内容安全检查
                "visual_quality_assessment",    # 视觉质量评估
                "audio_quality_assessment",     # 音频质量评估
                "compliance_check"              # 合规性检查
            ],
            
            # 协调器Agent - 使用轻量控制工具进行FC调度
            AgentType.ORCHESTRATOR: [
                "orchestrator_control"
            ],

            # Episode Orchestrator 复用已有工作流，不额外暴露工具
            AgentType.EPISODE_ORCHESTRATOR: [],

            # Episode Script Planner - 纯文本草稿生成
            AgentType.EPISODE_SCRIPT_PLANNER: [],
        }
        
        # 定义通用工具（所有Agent都可以使用）
        # 仅保留已在工具注册表中的通用工具，避免无效名称
        self._common_tools = [
            "file_storage_tool"
        ]
        
        # 定义工具依赖关系
        # 精简依赖：仅保留已注册、稳定的依赖
        self._tool_dependencies = {
            # 允许 video_generation 伴随 scene_analysis（均为已注册工具）
            "video_generation": ["scene_analysis"],
            # 其余移除不稳定依赖，避免装载未注册工具
        }
    
    def get_tools_for_agent(self, agent_type: AgentType) -> List[str]:
        """
        获取指定Agent类型的工具列表
        
        返回：该Agent应该使用的专门工具列表（不包含不相关工具）
        """
        # 获取专门工具
        specialized_tools = self._agent_tool_mapping.get(agent_type, [])
        
        # 添加通用工具（概念规划等纯LLM代理不注入通用工具）
        if agent_type == AgentType.CONCEPT_PLANNER:
            all_tools = list(specialized_tools)
        else:
            all_tools = specialized_tools + self._common_tools
        
        # 添加依赖工具
        dependencies = self._resolve_tool_dependencies(specialized_tools)
        all_tools.extend(dependencies)
        
        # 去重并保持顺序
        return list(dict.fromkeys(all_tools))
    
    def _resolve_tool_dependencies(self, tools: List[str]) -> List[str]:
        """解析工具依赖关系"""
        dependencies = []
        
        for tool in tools:
            if tool in self._tool_dependencies:
                deps = self._tool_dependencies[tool]
                dependencies.extend(deps)
        
        return dependencies
    
    def get_available_tools_by_category(self, category: ToolCategory) -> List[str]:
        """按类别获取可用工具"""
        category_mapping = {
            ToolCategory.AI_SERVICE: [
                "concept_generation", "script_generation", "image_generation", 
                "video_generation", "audio_generation", "scene_analysis"
            ],
            ToolCategory.MEDIA_PROCESSING: [
                "ffmpeg_processing", "audio_processing", "image_enhancement",
                "video_enhancement"
            ],
            ToolCategory.STORAGE: [
                "file_storage", "oss_storage", "s3_storage"
            ],
            ToolCategory.ANALYSIS: [
                "scene_analysis", "quality_analysis", "content_analysis",
                "visual_quality_assessment"
            ],
            ToolCategory.COMPOSITION: [
                "video_composition", "audio_composition", "media_synchronization"
            ],
            ToolCategory.QUALITY: [
                "quality_analysis", "content_safety_check", "compliance_check"
            ],
            ToolCategory.WORKFLOW: [
                "workflow_management", "task_scheduling", "progress_tracking"
            ]
        }
        
        return category_mapping.get(category, [])
    
    def validate_tool_allocation(self, agent_type: AgentType, requested_tools: List[str]) -> Dict[str, any]:
        """
        验证Agent请求的工具是否合理
        
        返回验证结果和建议
        """
        allowed_tools = set(self.get_tools_for_agent(agent_type))
        requested_tools_set = set(requested_tools)
        
        # 检查不被允许的工具
        unauthorized_tools = requested_tools_set - allowed_tools
        
        # 检查缺失的核心工具
        core_tools = set(self._agent_tool_mapping.get(agent_type, []))
        missing_core_tools = core_tools - requested_tools_set
        
        return {
            "is_valid": len(unauthorized_tools) == 0,
            "unauthorized_tools": list(unauthorized_tools),
            "missing_core_tools": list(missing_core_tools),
            "allowed_tools": list(allowed_tools),
            "recommendations": self._generate_recommendations(
                agent_type, unauthorized_tools, missing_core_tools
            )
        }
    
    def _generate_recommendations(
        self, 
        agent_type: AgentType, 
        unauthorized: Set[str], 
        missing: Set[str]
    ) -> List[str]:
        """生成工具配置建议"""
        recommendations = []
        
        if unauthorized:
            recommendations.append(
                f"{agent_type.value} Agent不应使用这些工具: {', '.join(unauthorized)}"
            )
        
        if missing:
            recommendations.append(
                f"{agent_type.value} Agent应该包含这些核心工具: {', '.join(missing)}"
            )
        
        if not unauthorized and not missing:
            recommendations.append(f"{agent_type.value} Agent的工具配置合理")
        
        return recommendations
    
    def get_tool_usage_statistics(self) -> Dict[str, any]:
        """获取工具使用统计"""
        all_tools = set()
        agent_tool_count = {}
        
        for agent_type, tools in self._agent_tool_mapping.items():
            all_tools.update(tools)
            agent_tool_count[agent_type.value] = len(tools)
        
        # 计算工具被使用次数
        tool_usage_count = {}
        for tools in self._agent_tool_mapping.values():
            for tool in tools:
                tool_usage_count[tool] = tool_usage_count.get(tool, 0) + 1
        
        return {
            "total_unique_tools": len(all_tools),
            "agent_tool_counts": agent_tool_count,
            "tool_usage_frequency": tool_usage_count,
            "most_used_tools": sorted(
                tool_usage_count.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5]
        }
    
    def suggest_new_agent_tools(self, agent_description: str) -> List[str]:
        """基于Agent描述建议工具列表"""
        # 这里可以用LLM分析Agent描述并推荐工具
        # 简化实现：基于关键词匹配
        keyword_tool_mapping = {
            "视频": ["video_generation", "video_composition"],
            "图像": ["image_generation", "image_analysis"],
            "音频": ["audio_generation", "audio_processing"],
            "质量": ["quality_analysis", "content_safety_check"],
            "脚本": ["script_generation", "narrative_analysis"],
            "分析": ["scene_analysis", "content_analysis"]
        }
        
        suggested_tools = []
        for keyword, tools in keyword_tool_mapping.items():
            if keyword in agent_description:
                suggested_tools.extend(tools)
        
        # 添加通用工具
        suggested_tools.extend(self._common_tools)
        
        return list(dict.fromkeys(suggested_tools))  # 去重


# 全局工具分配器实例
_tool_allocator = None


def get_tool_allocator() -> AgentToolAllocator:
    """获取全局工具分配器"""
    global _tool_allocator
    if _tool_allocator is None:
        _tool_allocator = AgentToolAllocator()
    return _tool_allocator


def get_agent_tools(agent_type: AgentType) -> List[str]:
    """便捷函数：获取Agent的工具列表"""
    return get_tool_allocator().get_tools_for_agent(agent_type)


def validate_agent_tools(agent_type: AgentType, tools: List[str]) -> Dict[str, any]:
    """便捷函数：验证Agent工具配置"""
    return get_tool_allocator().validate_tool_allocation(agent_type, tools)

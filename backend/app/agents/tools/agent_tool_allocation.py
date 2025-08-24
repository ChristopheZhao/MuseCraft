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
            
            # 概念规划Agent - 创意分析和内容规划
            AgentType.CONCEPT_PLANNER: [
                "concept_generation_tool",           # 概念生成 - 匹配注册名称
                "narrative_structure_generation_tool", # 叙事结构生成 - 匹配注册名称  
                "intelligent_scene_planning",        # 智能场景规划（LLM动态决策）
                "content_analysis",                  # 内容分析
                "creative_optimization"              # 创意优化
            ],
            
            # 脚本编写Agent - 文本生成和叙事分析
            AgentType.SCRIPT_WRITER: [
                "script_generation",                 # 脚本生成 - 匹配注册名称
                "scene_script_generation_tool",      # 场景脚本生成 - 匹配注册名称
                "scene_continuity_analysis_tool",    # 场景连续性分析 - 匹配注册名称
                "narrative_structure_generation_tool" # 叙事结构生成 - 匹配注册名称
            ],
            
            # 图像生成Agent - 视觉创作和图像处理
            AgentType.IMAGE_GENERATOR: [
                "image_generation",             # 图像生成
                "image_analysis",               # 图像分析
                "style_extraction",             # 风格提取
                "visual_consistency_check",     # 视觉一致性检查
                "image_enhancement",            # 图像增强
                "scene_continuity_analysis_tool" # 🔧 修复：场景连续性分析，决定是否使用前一场景最后一帧
            ],
            
            # 视频生成Agent - 视频创作和场景分析
            AgentType.VIDEO_GENERATOR: [
                "video_generation",             # 视频生成（核心工具）
                "scene_analysis",               # 场景分析
                "parameter_optimization",       # 参数优化
                "motion_analysis",              # 动作分析
                "video_enhancement",            # 视频增强
                "zhipu_client"                  # 🔧 修复：用于图像分析的GLM-4V调用
            ],
            
            # 音频生成Agent - 音频创作和处理
            AgentType.AUDIO_GENERATOR: [
                "audio_generation",             # 音频生成
                "music_composition",            # 音乐创作
                "voice_synthesis",              # 语音合成
                "audio_analysis",               # 音频分析
                "audio_processing"              # 音频处理
            ],
            
            # 视频合成Agent - 媒体组合和渲染
            AgentType.VIDEO_COMPOSER: [
                "video_composition",            # 视频合成
                "ffmpeg_processing",            # FFmpeg处理
                "media_synchronization",        # 媒体同步
                "transition_effects",           # 过渡效果
                "rendering_optimization"        # 渲染优化
            ],
            
            # 质量检查Agent - 质量评估和优化
            AgentType.QUALITY_CHECKER: [
                "quality_analysis_tool",        # 质量分析 - 匹配注册名称
                "content_safety_check",         # 内容安全检查
                "visual_quality_assessment",    # 视觉质量评估
                "audio_quality_assessment",     # 音频质量评估
                "compliance_check"              # 合规性检查
            ],
            
            # 协调器Agent - 工作流管理和调度
            AgentType.ORCHESTRATOR: [
                "workflow_management",          # 工作流管理
                "task_scheduling",              # 任务调度
                "resource_allocation",          # 资源分配
                "progress_tracking",            # 进度跟踪
                "error_recovery"                # 错误恢复
            ]
        }
        
        # 定义通用工具（所有Agent都可以使用）
        self._common_tools = [
            "file_storage",                     # 文件存储
            "progress_reporting",               # 进度报告
            "error_logging"                     # 错误日志
        ]
        
        # 定义工具依赖关系
        self._tool_dependencies = {
            "video_generation": ["scene_analysis"],      # 视频生成依赖场景分析
            "image_generation": ["style_extraction"],    # 图像生成依赖风格提取
            "video_composition": ["ffmpeg_processing"],  # 视频合成依赖FFmpeg
        }
    
    def get_tools_for_agent(self, agent_type: AgentType) -> List[str]:
        """
        获取指定Agent类型的工具列表
        
        返回：该Agent应该使用的专门工具列表（不包含不相关工具）
        """
        # 获取专门工具
        specialized_tools = self._agent_tool_mapping.get(agent_type, [])
        
        # 添加通用工具
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
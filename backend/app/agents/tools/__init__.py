"""
Agent Tools Module - All tool classes and utilities
"""

from .base_tool import BaseTool, AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .tool_registry import ToolRegistry, get_tool_registry

# AI Service Tools
from .ai_services.openai_client import OpenAIClientTool
from .ai_services.kimi_client import KimiClientTool
from .ai_services.zhipu_client import ZhipuClientTool
from .ai_services.suno_client import SunoClientTool
from .ai_services.image_generation_client import ImageGenerationClientTool
from .ai_services.jimeng_image_tool import JimengImageTool
from .ai_services.video_generation_tool_v2 import VideoGenerationTool
from .ai_services.voice_synth_tool import VoiceSynthesisTool
from .ai_services.scene_analysis_tool import SceneAnalysisTool
from .ai_services.parameter_optimization_tool import ParameterOptimizationTool
from .ai_services.intelligent_scene_planning_tool import IntelligentScenePlanningTool
from .ai_services.script_generation_tool import ScriptGenerationTool
from .ai_services.image_generation_tool import ImageGenerationTool
from .ai_services.quality_analysis_tool import QualityAnalysisTool
from .ai_services.role_analysis_tool import RoleAnalysisTool

# Video Processing Tools
from .video_processing.ffmpeg_tool import FFmpegTool
from .video_processing.minimax_video_tool import MiniMaxVideoTool
from .media_processing.audio_processor import AudioProcessorTool
from .media_processing.audio_analysis_tool import AudioAnalysisTool

# Storage Tools
from .storage.file_storage_tool import FileStorageTool
from .storage.oss_storage_tool import OSSStorageTool

# Video Composition Tools
from .video_composition.video_composer_tool import VideoComposerTool
from .video_processing.final_frame_tool import FinalFrameTool
from .video_processing.scene_continuity_preparation_tool import SceneContinuityPreparationTool
from .memory_tool import MemoryTool
from .orchestrator_control_tool import OrchestratorControlTool
from .consistency_tool import ConsistencyTool

# Tool registry instance
tool_registry = get_tool_registry()

def register_default_tools():
    """Register all default tools"""
    # Register AI service tools
    tool_registry.register_tool(OpenAIClientTool)
    tool_registry.register_tool(KimiClientTool)
    tool_registry.register_tool(ZhipuClientTool)
    tool_registry.register_tool(SunoClientTool)
    tool_registry.register_tool(VoiceSynthesisTool)
    tool_registry.register_tool(ImageGenerationClientTool)
    tool_registry.register_tool(JimengImageTool)
    
    # Register video processing tools
    tool_registry.register_tool(FFmpegTool)
    tool_registry.register_tool(MiniMaxVideoTool)
    tool_registry.register_tool(AudioProcessorTool)
    tool_registry.register_tool(AudioAnalysisTool)
    
    # Register storage tools
    tool_registry.register_tool(FileStorageTool)
    tool_registry.register_tool(OSSStorageTool)
    
    # Register video composition tools
    tool_registry.register_tool(VideoComposerTool)
    tool_registry.register_tool(FinalFrameTool)
    tool_registry.register_tool(SceneContinuityPreparationTool)
    
    # Register new MAS tools
    tool_registry.register_tool(VideoGenerationTool)
    tool_registry.register_tool(SceneAnalysisTool)
    tool_registry.register_tool(ParameterOptimizationTool)
    tool_registry.register_tool(IntelligentScenePlanningTool)
    tool_registry.register_tool(ScriptGenerationTool)
    tool_registry.register_tool(ImageGenerationTool)
    tool_registry.register_tool(QualityAnalysisTool)
    tool_registry.register_tool(RoleAnalysisTool)
    tool_registry.register_tool(ConsistencyTool)
    # Register shared memory capability
    tool_registry.register_tool(MemoryTool)
    # Register orchestrator control
    tool_registry.register_tool(OrchestratorControlTool)

__all__ = [
    # Base classes
    "BaseTool",
    "AsyncTool", 
    "ToolMetadata",
    "ToolType",
    "ToolInput",
    "ToolError",
    "ToolValidationError",
    
    # Registry
    "ToolRegistry",
    "get_tool_registry",
    "tool_registry",
    
    # AI Service Tools
    "OpenAIClientTool",
    "KimiClientTool", 
    "ZhipuClientTool", 
    "SunoClientTool",
    "VoiceSynthesisTool",
    "ImageGenerationClientTool",
    "JimengImageTool",
    "VideoGenerationTool",
    "SceneAnalysisTool", 
    "ParameterOptimizationTool",
    "IntelligentScenePlanningTool",
    "ScriptGenerationTool", 
    "ImageGenerationTool",
    "QualityAnalysisTool",
    "RoleAnalysisTool",
    
    # Video Processing Tools
    "FFmpegTool",
    "MiniMaxVideoTool",
    
    # Storage Tools
    "FileStorageTool",
    "OSSStorageTool",
    
    # Video Composition Tools
    "VideoComposerTool",
    "FinalFrameTool", 
    "SceneContinuityPreparationTool",
    "MemoryTool",
    "OrchestratorControlTool",
    "ConsistencyTool",
    
    # Functions
    "register_default_tools"
]

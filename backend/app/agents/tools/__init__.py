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

# Video Processing Tools
from .video_processing.ffmpeg_tool import FFmpegTool
from .video_processing.minimax_video_tool import MiniMaxVideoTool

# Storage Tools
from .storage.file_storage_tool import FileStorageTool
from .storage.oss_storage_tool import OSSStorageTool

# Video Composition Tools
from .video_composition.video_composer_tool import VideoComposerTool

# Tool registry instance
tool_registry = get_tool_registry()

def register_default_tools():
    """Register all default tools"""
    # Register AI service tools
    tool_registry.register_tool(OpenAIClientTool)
    tool_registry.register_tool(KimiClientTool)
    tool_registry.register_tool(ZhipuClientTool)
    tool_registry.register_tool(SunoClientTool)
    tool_registry.register_tool(ImageGenerationClientTool)
    tool_registry.register_tool(JimengImageTool)
    
    # Register video processing tools
    tool_registry.register_tool(FFmpegTool)
    tool_registry.register_tool(MiniMaxVideoTool)
    
    # Register storage tools
    tool_registry.register_tool(FileStorageTool)
    tool_registry.register_tool(OSSStorageTool)
    
    # Register video composition tools
    tool_registry.register_tool(VideoComposerTool)

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
    "ImageGenerationClientTool",
    "JimengImageTool",
    
    # Video Processing Tools
    "FFmpegTool",
    "MiniMaxVideoTool",
    
    # Storage Tools
    "FileStorageTool",
    "OSSStorageTool",
    
    # Video Composition Tools
    "VideoComposerTool",
    
    # Functions
    "register_default_tools"
]
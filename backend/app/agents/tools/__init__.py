"""
Agent Tools Module.

Keep this package import lightweight: importing any submodule under `app.agents.tools.*`
will execute this file first. Avoid importing provider SDKs or tool implementations here.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .base_tool import (
    AsyncTool,
    BaseTool,
    ToolError,
    ToolInput,
    ToolMetadata,
    ToolType,
    ToolValidationError,
)


_LAZY_IMPORTS = {
    # Registry
    "ToolRegistry": (".tool_registry", "ToolRegistry"),
    "get_tool_registry": (".tool_registry", "get_tool_registry"),
    # AI service tools
    "OpenAIClientTool": (".ai_services.openai_client", "OpenAIClientTool"),
    "KimiClientTool": (".ai_services.kimi_client", "KimiClientTool"),
    "ZhipuClientTool": (".ai_services.zhipu_client", "ZhipuClientTool"),
    "SunoClientTool": (".ai_services.suno_client", "SunoClientTool"),
    "ImageGenerationClientTool": (".ai_services.image_generation_client", "ImageGenerationClientTool"),
    "JimengImageTool": (".ai_services.jimeng_image_tool", "JimengImageTool"),
    "VideoGenerationTool": (".ai_services.video_generation_tool_v2", "VideoGenerationTool"),
    "VoiceSynthesisTool": (".ai_services.voice_synth_tool", "VoiceSynthesisTool"),
    "SceneAnalysisTool": (".ai_services.scene_analysis_tool", "SceneAnalysisTool"),
    "ParameterOptimizationTool": (".ai_services.parameter_optimization_tool", "ParameterOptimizationTool"),
    "IntelligentScenePlanningTool": (".ai_services.intelligent_scene_planning_tool", "IntelligentScenePlanningTool"),
    "ScriptGenerationTool": (".ai_services.script_generation_tool", "ScriptGenerationTool"),
    "ImageGenerationTool": (".ai_services.image_generation_tool", "ImageGenerationTool"),
    "QualityAnalysisTool": (".ai_services.quality_analysis_tool", "QualityAnalysisTool"),
    "RoleAnalysisTool": (".ai_services.role_analysis_tool", "RoleAnalysisTool"),
    # Video/media processing tools
    "FFmpegTool": (".video_processing.ffmpeg_tool", "FFmpegTool"),
    "MiniMaxVideoTool": (".video_processing.minimax_video_tool", "MiniMaxVideoTool"),
    "AudioProcessorTool": (".media_processing.audio_processor", "AudioProcessorTool"),
    "AudioAnalysisTool": (".media_processing.audio_analysis_tool", "AudioAnalysisTool"),
    # Storage tools
    "FileStorageTool": (".storage.file_storage_tool", "FileStorageTool"),
    "OSSStorageTool": (".storage.oss_storage_tool", "OSSStorageTool"),
    # Composition/tools
    "VideoComposerTool": (".video_composition.video_composer_tool", "VideoComposerTool"),
    "FinalFrameTool": (".video_processing.final_frame_tool", "FinalFrameTool"),
    "SceneContinuityPreparationTool": (".video_processing.scene_continuity_preparation_tool", "SceneContinuityPreparationTool"),
    "MemoryTool": (".memory_tool", "MemoryTool"),
    "OrchestratorControlTool": (".orchestrator_control_tool", "OrchestratorControlTool"),
    "ConsistencyTool": (".consistency_tool", "ConsistencyTool"),
    "VideoPromptBuilderTool": (".video_prompt_builder_tool", "VideoPromptBuilderTool"),
    "VideoPromptComposerTool": (".video_prompt_composer_tool", "VideoPromptComposerTool"),
    "ImagePromptComposerTool": (".image_prompt_composer_tool", "ImagePromptComposerTool"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_IMPORTS.get(name)
    if not target:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name, package=__name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def register_default_tools() -> None:
    """Register all default tools (explicit opt-in)."""
    from .tool_registry import get_tool_registry

    registry = get_tool_registry()

    from .ai_services.openai_client import OpenAIClientTool
    from .ai_services.kimi_client import KimiClientTool
    from .ai_services.zhipu_client import ZhipuClientTool
    from .ai_services.suno_client import SunoClientTool
    from .ai_services.voice_synth_tool import VoiceSynthesisTool
    from .ai_services.image_generation_client import ImageGenerationClientTool
    from .ai_services.jimeng_image_tool import JimengImageTool

    from .video_processing.ffmpeg_tool import FFmpegTool
    from .video_processing.minimax_video_tool import MiniMaxVideoTool
    from .media_processing.audio_processor import AudioProcessorTool
    from .media_processing.audio_analysis_tool import AudioAnalysisTool

    from .storage.file_storage_tool import FileStorageTool
    from .storage.oss_storage_tool import OSSStorageTool

    from .video_composition.video_composer_tool import VideoComposerTool
    from .video_processing.final_frame_tool import FinalFrameTool
    from .video_processing.scene_continuity_preparation_tool import SceneContinuityPreparationTool

    from .ai_services.video_generation_tool_v2 import VideoGenerationTool
    from .ai_services.scene_analysis_tool import SceneAnalysisTool
    from .ai_services.parameter_optimization_tool import ParameterOptimizationTool
    from .ai_services.intelligent_scene_planning_tool import IntelligentScenePlanningTool
    from .ai_services.script_generation_tool import ScriptGenerationTool
    from .ai_services.image_generation_tool import ImageGenerationTool
    from .ai_services.quality_analysis_tool import QualityAnalysisTool
    from .ai_services.role_analysis_tool import RoleAnalysisTool
    from .consistency_tool import ConsistencyTool
    from .video_prompt_builder_tool import VideoPromptBuilderTool
    from .video_prompt_composer_tool import VideoPromptComposerTool
    from .image_prompt_composer_tool import ImagePromptComposerTool
    from .memory_tool import MemoryTool
    from .orchestrator_control_tool import OrchestratorControlTool

    registry.register_tool(OpenAIClientTool)
    registry.register_tool(KimiClientTool)
    registry.register_tool(ZhipuClientTool)
    registry.register_tool(SunoClientTool)
    registry.register_tool(VoiceSynthesisTool)
    registry.register_tool(ImageGenerationClientTool)
    registry.register_tool(JimengImageTool)

    registry.register_tool(FFmpegTool)
    registry.register_tool(MiniMaxVideoTool)
    registry.register_tool(AudioProcessorTool)
    registry.register_tool(AudioAnalysisTool)

    registry.register_tool(FileStorageTool)
    registry.register_tool(OSSStorageTool)

    registry.register_tool(VideoComposerTool)
    registry.register_tool(FinalFrameTool)
    registry.register_tool(SceneContinuityPreparationTool)

    registry.register_tool(VideoGenerationTool)
    registry.register_tool(SceneAnalysisTool)
    registry.register_tool(ParameterOptimizationTool)
    registry.register_tool(IntelligentScenePlanningTool)
    registry.register_tool(ScriptGenerationTool)
    registry.register_tool(ImageGenerationTool)
    registry.register_tool(QualityAnalysisTool)
    registry.register_tool(RoleAnalysisTool)
    registry.register_tool(ConsistencyTool)
    registry.register_tool(VideoPromptBuilderTool)
    registry.register_tool(VideoPromptComposerTool)
    registry.register_tool(ImagePromptComposerTool)
    registry.register_tool(MemoryTool, auto_load=False)
    registry.register_tool(OrchestratorControlTool)


__all__ = [
    "BaseTool",
    "AsyncTool",
    "ToolMetadata",
    "ToolType",
    "ToolInput",
    "ToolError",
    "ToolValidationError",
    "register_default_tools",
]

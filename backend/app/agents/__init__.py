"""
Agents package for video generation workflow.

保持 __init__ 轻量，避免导入子模块时触发整个 Agent 栈的沉重依赖。
通过懒加载提供常用 Agent 导出，只有访问时才导入对应模块。
"""

__all__ = [
    "BaseAgent",
    "AgentError",
    "AgentTimeoutError",
    "ReActAgent",
    "OrchestratorAgent",
    "EpisodeOrchestratorAgent",
    "ConceptPlannerAgent",
    "SeriesPlannerAgent",
    "EpisodeScriptPlannerAgent",
    "ScriptWriterAgent",
    "ImageGeneratorAgent",
    "VideoGeneratorAgent",
    "VoiceSynthesizerAgent",
    "AudioGeneratorAgent",
    "VideoComposerAgent",
    "QualityCheckerAgent",
]


_LAZY_MODULES = {
    "BaseAgent": ("app.agents.base", "BaseAgent"),
    "AgentError": ("app.agents.base", "AgentError"),
    "AgentTimeoutError": ("app.agents.base", "AgentTimeoutError"),
    "ReActAgent": ("app.agents.react_agent", "ReActAgent"),
    "OrchestratorAgent": ("app.agents.orchestrator", "OrchestratorAgent"),
    "EpisodeOrchestratorAgent": ("app.agents.episode_orchestrator", "EpisodeOrchestratorAgent"),
    "ConceptPlannerAgent": ("app.agents.concept_planner", "ConceptPlannerAgent"),
    "SeriesPlannerAgent": ("app.agents.series_planner", "SeriesPlannerAgent"),
    "EpisodeScriptPlannerAgent": ("app.agents.episode_script_planner", "EpisodeScriptPlannerAgent"),
    "ScriptWriterAgent": ("app.agents.script_writer", "ScriptWriterAgent"),
    "ImageGeneratorAgent": ("app.agents.image_generator", "ImageGeneratorAgent"),
    "VideoGeneratorAgent": ("app.agents.video_generator", "VideoGeneratorAgent"),
    "VoiceSynthesizerAgent": ("app.agents.voice_synthesizer", "VoiceSynthesizerAgent"),
    "AudioGeneratorAgent": ("app.agents.audio_generator", "AudioGeneratorAgent"),
    "VideoComposerAgent": ("app.agents.video_composer", "VideoComposerAgent"),
    "QualityCheckerAgent": ("app.agents.quality_checker", "QualityCheckerAgent"),
}


def __getattr__(name):
    if name not in _LAZY_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_MODULES[name]
    module = __import__(module_name, fromlist=[attr_name])
    value = getattr(module, attr_name)
    globals()[name] = value
    return value

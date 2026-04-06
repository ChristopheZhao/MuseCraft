"""
Agent type/status enums
"""
import enum
import logging

logger = logging.getLogger(__name__)


class AgentType(str, enum.Enum):
    ORCHESTRATOR = "orchestrator"
    EPISODE_ORCHESTRATOR = "episode_orchestrator"
    EPISODE_SCRIPT_PLANNER = "episode_script_planner"
    CONCEPT_PLANNER = "concept_planner"
    SERIES_PLANNER = "series_planner"
    SCRIPT_WRITER = "script_writer"
    IMAGE_GENERATOR = "image_generator"
    VIDEO_GENERATOR = "video_generator"
    VOICE_SYNTHESIZER = "voice_synthesizer"
    AUDIO_GENERATOR = "audio_generator"
    VIDEO_COMPOSER = "video_composer"
    QUALITY_CHECKER = "quality_checker"


class AgentStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


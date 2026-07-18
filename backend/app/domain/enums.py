"""Domain enums shared by application, Agent, and persistence adapter layers."""

from enum import Enum


class AgentType(str, Enum):
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


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PERSISTING_DATA = "persisting_data"


class TaskType(str, Enum):
    VIDEO_GENERATION = "video_generation"
    IMAGE_GENERATION = "image_generation"
    SCRIPT_WRITING = "script_writing"
    VIDEO_EDITING = "video_editing"
    CONCEPT_PLANNING = "concept_planning"


class SceneType(str, Enum):
    INTRO = "intro"
    MAIN_CONTENT = "main_content"
    TRANSITION = "transition"
    OUTRO = "outro"
    BACKGROUND = "background"


class ResourceType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE_OVER = "voice_over"
    TEXT = "text"
    SCRIPT = "script"
    THUMBNAIL = "thumbnail"
    TEMP_FILE = "temp_file"


class WorkflowSessionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_GATE = "waiting_gate"
    RESUMING = "resuming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowNodeStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PENDING_GATE = "pending_gate"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STALE = "stale"


class WorkflowAttemptStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


class WorkflowGateStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    AWAITING_HUMAN = "awaiting_human"
    DECIDED = "decided"

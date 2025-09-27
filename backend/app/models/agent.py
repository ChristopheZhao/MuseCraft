"""
Agent execution model for tracking agent workflow steps
"""
import enum
import logging
from sqlalchemy import Column, String, Text, JSON, Enum, Integer, ForeignKey, Float, Boolean
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship

from .base import BaseModel


logger = logging.getLogger(__name__)


class AgentType(str, enum.Enum):
    ORCHESTRATOR = "orchestrator"
    CONCEPT_PLANNER = "concept_planner"
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


class AgentTypeString(TypeDecorator):
    """Persist AgentType enum as VARCHAR while exposing Enum instances."""

    impl = String(50)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, AgentType):
            return value.value
        if isinstance(value, str):
            return value
        raise ValueError(f"Unsupported agent_type value: {value!r}")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, AgentType):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            try:
                return AgentType(cleaned)
            except ValueError:
                try:
                    return AgentType(cleaned.lower())
                except ValueError:
                    logger.warning("Unknown agent_type value from DB: %s", cleaned)
                    return cleaned
        return value


class AgentExecution(BaseModel):
    __tablename__ = "agent_executions"
    
    # Task relationship
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    task = relationship("Task", back_populates="agent_executions")
    
    # Agent information
    agent_type = Column(AgentTypeString(), nullable=False)
    agent_name = Column(String(100), nullable=False)
    agent_version = Column(String(20), default="1.0")
    
    # Execution information
    execution_order = Column(Integer, nullable=False)  # Step number in workflow
    status = Column(Enum(AgentStatus), default=AgentStatus.PENDING)
    
    # Timing information
    started_at = Column(Integer)  # Unix timestamp
    completed_at = Column(Integer)  # Unix timestamp
    duration = Column(Float)  # in seconds
    timeout_seconds = Column(Integer, default=300)  # 5 minutes default
    
    # Input and output
    input_data = Column(JSON, default=dict)  # Input parameters and data
    output_data = Column(JSON, default=dict)  # Generated output data
    
    # AI model information
    model_name = Column(String(100))  # Which AI model was used
    model_parameters = Column(JSON, default=dict)  # Model-specific parameters
    
    # Performance metrics
    tokens_used = Column(Integer)  # For LLM calls
    api_calls_made = Column(Integer, default=0)
    cost_estimate = Column(Float)  # Estimated cost in USD
    
    # Error handling
    error_message = Column(Text)
    error_type = Column(String(100))
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Progress tracking
    progress_percentage = Column(Integer, default=0)
    current_substep = Column(String(100))
    
    # Quality metrics
    output_quality_score = Column(Integer)  # 1-10 scale
    confidence_score = Column(Float)  # 0.0-1.0 scale
    
    # Debugging and monitoring
    debug_info = Column(JSON, default=dict)  # Debug information
    performance_metrics = Column(JSON, default=dict)  # Performance data
    
    # Dependencies
    depends_on_agents = Column(JSON, default=list)  # List of agent types this depends on
    blocks_agents = Column(JSON, default=list)  # List of agent types this blocks
    
    def __repr__(self):
        return f"<AgentExecution(id={self.id}, agent_type={self.agent_type}, status={self.status})>"
    
    @property
    def is_completed(self) -> bool:
        return self.status == AgentStatus.COMPLETED
    
    @property
    def is_running(self) -> bool:
        return self.status == AgentStatus.RUNNING
    
    @property
    def is_failed(self) -> bool:
        return self.status == AgentStatus.FAILED
    
    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries
    
    def start_execution(self):
        """Mark agent execution as started"""
        import time
        self.started_at = int(time.time())
        self.status = AgentStatus.RUNNING
    
    def complete_execution(self, output_data: dict = None):
        """Mark agent execution as completed"""
        import time
        current_time = int(time.time())
        
        self.completed_at = current_time
        self.status = AgentStatus.COMPLETED
        self.progress_percentage = 100
        
        if self.started_at:
            self.duration = current_time - self.started_at
        
        if output_data:
            self.output_data.update(output_data)
    
    def fail_execution(self, error_message: str, error_type: str = None):
        """Mark agent execution as failed"""
        import time
        current_time = int(time.time())
        
        self.status = AgentStatus.FAILED
        self.error_message = error_message
        self.error_type = error_type or "unknown"
        self.retry_count += 1
        
        if self.started_at:
            self.duration = current_time - self.started_at
    
    def update_progress(self, percentage: int, substep: str = None):
        """Update execution progress"""
        self.progress_percentage = min(100, max(0, percentage))
        if substep:
            self.current_substep = substep
    
    def add_debug_info(self, key: str, value):
        """Add debug information"""
        if not self.debug_info:
            self.debug_info = {}
        self.debug_info[key] = value
    
    def estimate_cost(self, token_cost_per_1k: float = 0.002):
        """Estimate execution cost based on tokens used"""
        if self.tokens_used:
            self.cost_estimate = (self.tokens_used / 1000) * token_cost_per_1k

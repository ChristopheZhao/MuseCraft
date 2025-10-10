"""
Task model for video generation tasks
"""
import enum
from typing import Dict, Any, Optional
from sqlalchemy import Column, String, Text, JSON, Enum, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy import String as SQLString
import uuid

from .base import BaseModel


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PERSISTING_DATA = "persisting_data"


class TaskType(str, enum.Enum):
    VIDEO_GENERATION = "video_generation"
    IMAGE_GENERATION = "image_generation"
    SCRIPT_WRITING = "script_writing"
    VIDEO_EDITING = "video_editing"
    CONCEPT_PLANNING = "concept_planning"


class Task(BaseModel):
    __tablename__ = "tasks"
    
    # Basic task information  
    # Use String for UUID to maintain compatibility with both MySQL and PostgreSQL
    task_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()), index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    task_type = Column(Enum(TaskType), nullable=False)
    status = Column(String(20), default=TaskStatus.PENDING.value, nullable=False)
    
    # User and session information
    user_id = Column(String(100))  # For future user authentication
    session_id = Column(String(100))
    
    # Task configuration and parameters
    input_parameters = Column(JSON, default=dict)  # User input parameters
    output_metadata = Column(JSON, default=dict)   # Generated output metadata
    
    # Progress tracking
    progress_percentage = Column(Integer, default=0)
    current_step = Column(String(100))
    total_steps = Column(Integer, default=6)  # 6 agents in workflow
    
    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Resource management
    estimated_duration = Column(Integer)  # in seconds
    actual_duration = Column(Integer)     # in seconds
    resource_usage = Column(JSON, default=dict)  # CPU, memory, etc.
    
    # Quality control
    quality_score = Column(Integer)  # 1-10 scale
    quality_feedback = Column(Text)
    requires_human_review = Column(Boolean, default=False)
    
    # Relationships
    scenes = relationship("Scene", back_populates="task", cascade="all, delete-orphan")
    resources = relationship("Resource", back_populates="task", cascade="all, delete-orphan")
    agent_executions = relationship("AgentExecution", back_populates="task", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Task(id={self.id}, task_id={self.task_id}, status={self.status})>"
    
    @property
    def is_completed(self) -> bool:
        return self.status == TaskStatus.COMPLETED.value
    
    @property
    def is_failed(self) -> bool:
        return self.status == TaskStatus.FAILED.value
    
    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries
    
    def update_progress(self, step: str, percentage: int):
        """Update task progress"""
        self.current_step = step
        self.progress_percentage = min(100, max(0, percentage))
    
    def add_error(self, error_message: str):
        """Add error message and increment retry count"""
        self.error_message = error_message
        self.retry_count += 1
        self.status = TaskStatus.FAILED.value
    
    def reset_for_retry(self):
        """Reset task for retry"""
        if self.can_retry:
            self.status = TaskStatus.PENDING.value
            self.progress_percentage = 0
            self.current_step = None
            self.error_message = None

"""
Execution state model for tracking transient runtime metadata.
This is used for audit logging and event context, distinct from business memory.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time
from contextvars import ContextVar

@dataclass
class ExecutionState:
    """
    Encapsulates the transient state of a single agent execution run.
    This object is created at the start of execute() and discarded afterwards.
    It is NOT persisted to DB directly, but used to populate events.
    """
    id: str
    agent_type: str
    agent_name: str
    execution_order: int
    input_data: Dict[str, Any] = field(default_factory=dict)
    
    # Mutable state tracking
    status: str = "pending"
    progress: int = 0
    current_substep: Optional[str] = None
    
    # Metrics
    tokens_used: int = 0
    api_calls_made: int = 0
    model_parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Timing
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    
    # Error tracking
    error_message: Optional[str] = None
    
    @property
    def duration(self) -> float:
        end = self.completed_at or time.time()
        return end - self.started_at

    def update_progress(self, percentage: int, substep: Optional[str] = None):
        self.progress = min(100, max(0, int(percentage)))
        if substep:
            self.current_substep = substep

    def add_token_usage(self, tokens: int):
        self.tokens_used += tokens
        self.api_calls_made += 1

    def finish(self, status: str = "completed", error: Optional[str] = None):
        self.status = status
        self.completed_at = time.time()
        if error:
            self.error_message = error


# Global ContextVar for execution state
execution_context_var: ContextVar[Optional[ExecutionState]] = ContextVar("execution_context", default=None)


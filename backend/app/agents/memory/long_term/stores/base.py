"""
Base Memory Classes - Foundation for agent memory systems
"""

import time
import json
import hashlib
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import uuid


class MemoryType(Enum):
    """Types of memory storage"""
    SHORT_TERM = "short_term"      # Working memory, session-based
    LONG_TERM = "long_term"        # Persistent across sessions
    EPISODIC = "episodic"          # Specific experiences/events
    SEMANTIC = "semantic"          # General knowledge/facts
    PROCEDURAL = "procedural"      # How-to knowledge/skills
    WORKING = "working"            # Current task context
    CONCEPTUAL = "conceptual"      # High-level concepts and creative guidance


class MemoryImportance(Enum):
    """Memory importance levels"""
    CRITICAL = 5
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    MINIMAL = 1


@dataclass
class MemoryItem:
    """Individual memory item"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: Any = None
    memory_type: MemoryType = MemoryType.SHORT_TERM
    importance: MemoryImportance = MemoryImportance.MEDIUM
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Temporal information
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    access_count: int = 0
    
    # Contextual information
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Relationships
    related_items: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    
    # Content hash for deduplication
    content_hash: Optional[str] = None
    
    def __post_init__(self):
        """Post-initialization processing"""
        if self.content_hash is None:
            self.content_hash = self._compute_content_hash()
    
    def _compute_content_hash(self) -> str:
        """Compute hash of content for deduplication"""
        if self.content is None:
            return ""
        
        content_str = json.dumps(self.content, sort_keys=True, default=str)
        return hashlib.md5(content_str.encode()).hexdigest()
    
    def update_access(self):
        """Update access tracking"""
        self.last_accessed = datetime.now()
        self.access_count += 1
    
    def is_expired(self) -> bool:
        """Check if memory item is expired"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def get_age_seconds(self) -> float:
        """Get age of memory in seconds"""
        return (datetime.now() - self.created_at).total_seconds()
    
    def get_recency_score(self) -> float:
        """Get recency score (0.0 to 1.0, higher = more recent)"""
        age_hours = self.get_age_seconds() / 3600
        return 1.0 / (1.0 + age_hours)  # Exponential decay
    
    def get_importance_score(self) -> float:
        """Get normalized importance score (0.0 to 1.0)"""
        return self.importance.value / 5.0
    
    def get_relevance_score(self, query_tags: List[str] = None) -> float:
        """Get relevance score based on tag overlap"""
        if not query_tags or not self.tags:
            return 0.0
        
        common_tags = set(self.tags) & set(query_tags)
        return len(common_tags) / len(set(self.tags) | set(query_tags))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "importance": self.importance.value,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "access_count": self.access_count,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "related_items": self.related_items,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "content_hash": self.content_hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """Create from dictionary"""
        # Parse datetime fields
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["last_accessed"] = datetime.fromisoformat(data["last_accessed"])
        if data["expires_at"]:
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        
        # Convert enum fields
        data["memory_type"] = MemoryType(data["memory_type"])
        data["importance"] = MemoryImportance(data["importance"])
        
        return cls(**data)


@dataclass
class MemoryQuery:
    """Memory query parameters"""
    content: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    memory_types: List[MemoryType] = field(default_factory=list)
    importance_min: Optional[MemoryImportance] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    time_range: Optional[Tuple[datetime, datetime]] = None
    limit: int = 10
    include_expired: bool = False
    similarity_threshold: float = 0.5
    sort_by: str = "relevance"  # relevance, recency, importance, access_count


class BaseMemoryStore(ABC):
    """Base class for memory storage backends"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._initialize()
    
    @abstractmethod
    def _initialize(self):
        """Initialize storage backend"""
        pass
    
    @abstractmethod
    async def store(self, memory_item: MemoryItem) -> bool:
        """
        Store a memory item
        
        Args:
            memory_item: Memory item to store
            
        Returns:
            Success status
        """
        pass
    
    @abstractmethod
    async def retrieve(self, memory_id: str) -> Optional[MemoryItem]:
        """
        Retrieve a specific memory item
        
        Args:
            memory_id: Memory item ID
            
        Returns:
            Memory item or None if not found
        """
        pass
    
    @abstractmethod
    async def search(self, query: MemoryQuery) -> List[MemoryItem]:
        """
        Search for memory items
        
        Args:
            query: Search query parameters
            
        Returns:
            List of matching memory items
        """
        pass
    
    @abstractmethod
    async def update(self, memory_item: MemoryItem) -> bool:
        """
        Update a memory item
        
        Args:
            memory_item: Updated memory item
            
        Returns:
            Success status
        """
        pass
    
    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """
        Delete a memory item
        
        Args:
            memory_id: Memory item ID
            
        Returns:
            Success status
        """
        pass
    
    @abstractmethod
    async def cleanup_expired(self) -> int:
        """
        Clean up expired memory items
        
        Returns:
            Number of items cleaned up
        """
        pass
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics
        
        Returns:
            Statistics dictionary
        """
        pass


class BaseMemoryRetriever(ABC):
    """Base class for memory retrieval strategies"""
    
    def __init__(self, memory_store: BaseMemoryStore, config: Dict[str, Any] = None):
        self.memory_store = memory_store
        self.config = config or {}
        self._initialize()
    
    @abstractmethod
    def _initialize(self):
        """Initialize retriever"""
        pass
    
    @abstractmethod
    async def retrieve_relevant(
        self, 
        query: str,
        context: Dict[str, Any] = None,
        limit: int = 10
    ) -> List[MemoryItem]:
        """
        Retrieve relevant memories for a query
        
        Args:
            query: Search query
            context: Additional context information
            limit: Maximum number of items to return
            
        Returns:
            List of relevant memory items
        """
        pass
    
    async def retrieve_recent(
        self,
        memory_types: List[MemoryType] = None,
        limit: int = 10,
        agent_id: str = None
    ) -> List[MemoryItem]:
        """Retrieve recent memories"""
        query = MemoryQuery(
            memory_types=memory_types or [],
            agent_id=agent_id,
            limit=limit,
            sort_by="recency"
        )
        return await self.memory_store.search(query)
    
    async def retrieve_important(
        self,
        importance_min: MemoryImportance = MemoryImportance.HIGH,
        limit: int = 10,
        agent_id: str = None
    ) -> List[MemoryItem]:
        """Retrieve important memories"""
        query = MemoryQuery(
            importance_min=importance_min,
            agent_id=agent_id,
            limit=limit,
            sort_by="importance"
        )
        return await self.memory_store.search(query)
    
    async def retrieve_by_tags(
        self,
        tags: List[str],
        limit: int = 10,
        agent_id: str = None
    ) -> List[MemoryItem]:
        """Retrieve memories by tags"""
        query = MemoryQuery(
            tags=tags,
            agent_id=agent_id,
            limit=limit,
            sort_by="relevance"
        )
        return await self.memory_store.search(query)


class MemoryError(Exception):
    """Base memory system error"""
    pass


class MemoryStorageError(MemoryError):
    """Memory storage error"""
    pass


class MemoryRetrievalError(MemoryError):
    """Memory retrieval error"""
    pass


class MemoryValidationError(MemoryError):
    """Memory validation error"""
    pass
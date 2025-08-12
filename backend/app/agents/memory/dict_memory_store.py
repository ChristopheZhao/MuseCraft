"""
Simple Dictionary-based Memory Store - In-memory implementation
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from .base_memory import (
    BaseMemoryStore, MemoryItem, MemoryQuery,
    MemoryError, MemoryStorageError
)


class DictMemoryStore(BaseMemoryStore):
    """
    Simple in-memory dictionary-based memory store
    Suitable for development and testing
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.memories: Dict[str, MemoryItem] = {}
        self.logger = logging.getLogger("dict_memory_store")
        super().__init__(config)
    
    def _initialize(self):
        """Initialize the memory store"""
        # For dict store, nothing special to initialize
        self.logger.info("DictMemoryStore initialized")
    
    async def store(self, memory_item: MemoryItem) -> bool:
        """Store a memory item"""
        try:
            self.memories[memory_item.id] = memory_item
            self.logger.debug(f"Stored memory: {memory_item.id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store memory: {e}")
            raise MemoryStorageError(f"Storage failed: {str(e)}")
    
    async def retrieve(self, memory_id: str) -> Optional[MemoryItem]:
        """Retrieve a specific memory item"""
        return self.memories.get(memory_id)
    
    async def search(self, query: MemoryQuery) -> List[MemoryItem]:
        """Search for memories based on query criteria"""
        results = []
        
        for memory in self.memories.values():
            # Apply filters
            if query.memory_types and memory.memory_type not in query.memory_types:
                continue
                
            if query.importance_min and memory.importance.value < query.importance_min.value:
                continue
                
            if query.agent_id and memory.agent_id != query.agent_id:
                continue
                
            if query.task_id and memory.task_id != query.task_id:
                continue
                
            if query.session_id and memory.session_id != query.session_id:
                continue
                
            if query.tags:
                if not any(tag in memory.tags for tag in query.tags):
                    continue
                    
            if query.time_range:
                start_time, end_time = query.time_range
                if not (start_time <= memory.created_at <= end_time):
                    continue
                    
            # Simple content matching
            if query.content:
                memory_content_str = str(memory.content).lower()
                if query.content.lower() not in memory_content_str:
                    continue
                    
            results.append(memory)
        
        # Sort by relevance (simple: by access count and recency)
        results.sort(key=lambda m: (m.access_count, m.last_accessed), reverse=True)
        
        # Apply limit
        if query.limit:
            results = results[:query.limit]
            
        return results
    
    async def update(self, memory_item: MemoryItem) -> bool:
        """Update an existing memory item"""
        if memory_item.id in self.memories:
            self.memories[memory_item.id] = memory_item
            return True
        return False
    
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory item"""
        if memory_id in self.memories:
            del self.memories[memory_id]
            return True
        return False
    
    async def cleanup_expired(self) -> int:
        """Remove expired memories"""
        current_time = datetime.now()
        expired_ids = []
        
        for memory_id, memory in self.memories.items():
            if memory.expires_at and memory.expires_at < current_time:
                expired_ids.append(memory_id)
                
        for memory_id in expired_ids:
            del self.memories[memory_id]
            
        return len(expired_ids)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get store statistics"""
        total_memories = len(self.memories)
        
        type_counts = {}
        importance_counts = {}
        
        for memory in self.memories.values():
            # Count by type
            type_name = memory.memory_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
            
            # Count by importance
            importance_name = memory.importance.name
            importance_counts[importance_name] = importance_counts.get(importance_name, 0) + 1
            
        return {
            "total_memories": total_memories,
            "type_distribution": type_counts,
            "importance_distribution": importance_counts,
            "store_type": "dictionary",
            "is_persistent": False
        }
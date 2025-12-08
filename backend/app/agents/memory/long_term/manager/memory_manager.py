"""
Memory Manager - High-level interface for agent memory operations
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Union, Type
from datetime import datetime, timedelta
from collections import defaultdict

from ..stores import (
    MemoryItem, MemoryQuery, MemoryType, MemoryImportance,
    BaseMemoryStore, BaseMemoryRetriever,
    MemoryError, MemoryStorageError, MemoryRetrievalError
)


class LongTermMemoryManager:
    """
    High-level memory management interface for long-term memories.
    
    Provides unified access to different memory stores and retrieval strategies
    """
    
    def __init__(
        self,
        stores: Dict[str, BaseMemoryStore] = None,
        retrievers: Dict[str, BaseMemoryRetriever] = None,
        default_store: str = "default",
        default_retriever: str = "default",
        config: Dict[str, Any] = None
    ):
        self.stores = stores or {}
        self.retrievers = retrievers or {}
        self.default_store = default_store
        self.default_retriever = default_retriever
        self.config = config or {}
        
        self.logger = logging.getLogger("long_term_memory_manager")
        
        # Memory consolidation settings
        self.consolidation_interval = self.config.get("consolidation_interval", 3600)  # 1 hour
        self.max_short_term_items = self.config.get("max_short_term_items", 1000)
        self.importance_decay_rate = self.config.get("importance_decay_rate", 0.95)
        
        # Statistics
        self.stats = defaultdict(int)
        
        # Start background tasks
        self._consolidation_task = None
        self._cleanup_task = None
        self._start_background_tasks()
    
    def add_store(self, name: str, store: BaseMemoryStore):
        """Add a memory store"""
        self.stores[name] = store
        self.logger.info(f"Added memory store: {name}")
    
    def add_retriever(self, name: str, retriever: BaseMemoryRetriever):
        """Add a memory retriever"""
        self.retrievers[name] = retriever
        self.logger.info(f"Added memory retriever: {name}")
    
    def get_store(self, name: str = None) -> BaseMemoryStore:
        """Get memory store by name"""
        store_name = name or self.default_store
        if store_name not in self.stores:
            raise MemoryError(f"Memory store not found: {store_name}")
        return self.stores[store_name]
    
    def get_retriever(self, name: str = None) -> BaseMemoryRetriever:
        """Get memory retriever by name"""
        retriever_name = name or self.default_retriever
        if retriever_name not in self.retrievers:
            raise MemoryError(f"Memory retriever not found: {retriever_name}")
        return self.retrievers[retriever_name]
    
    async def store_memory(
        self,
        content: Any,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        importance: MemoryImportance = MemoryImportance.MEDIUM,
        tags: List[str] = None,
        agent_id: str = None,
        task_id: str = None,
        session_id: str = None,
        expires_in: Optional[timedelta] = None,
        store_name: str = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Store a memory item
        
        Args:
            content: Memory content
            memory_type: Type of memory
            importance: Importance level
            tags: Associated tags
            agent_id: Agent identifier
            task_id: Task identifier
            session_id: Session identifier
            expires_in: Expiration time delta
            store_name: Specific store to use
            metadata: Additional metadata
            
        Returns:
            Memory item ID
        """
        try:
            # Create memory item
            memory_item = MemoryItem(
                content=content,
                memory_type=memory_type,
                importance=importance,
                tags=tags or [],
                agent_id=agent_id,
                task_id=task_id,
                session_id=session_id,
                metadata=metadata or {}
            )
            
            # Set expiration
            if expires_in:
                memory_item.expires_at = datetime.now() + expires_in
            elif memory_type == MemoryType.SHORT_TERM:
                # Default short-term memory expiration
                default_ttl = self.config.get("short_term_ttl", 3600)  # 1 hour
                memory_item.expires_at = datetime.now() + timedelta(seconds=default_ttl)
            
            # Check for duplicates
            existing_item = await self._find_duplicate(memory_item, store_name)
            if existing_item:
                # Update existing item instead of creating duplicate
                existing_item.access_count += 1
                existing_item.last_accessed = datetime.now()
                existing_item.importance = max(existing_item.importance, importance)
                await self._update_memory(existing_item, store_name)
                self.stats["duplicates_merged"] += 1
                return existing_item.id
            
            # Store the memory
            store = self.get_store(store_name)
            success = await store.store(memory_item)
            
            if success:
                self.stats["items_stored"] += 1
                self.logger.debug(f"Stored memory: {memory_item.id}")
                return memory_item.id
            else:
                raise MemoryStorageError("Failed to store memory item")
                
        except Exception as e:
            self.stats["storage_errors"] += 1
            self.logger.error(f"Error storing memory: {e}")
            raise MemoryStorageError(f"Storage failed: {str(e)}")
    
    async def retrieve_memory(
        self, 
        memory_id: str, 
        store_name: str = None,
        update_access: bool = True
    ) -> Optional[MemoryItem]:
        """
        Retrieve a specific memory item
        
        Args:
            memory_id: Memory item ID
            store_name: Specific store to use
            update_access: Whether to update access tracking
            
        Returns:
            Memory item or None
        """
        try:
            store = self.get_store(store_name)
            memory_item = await store.retrieve(memory_id)
            
            if memory_item and update_access:
                memory_item.update_access()
                await store.update(memory_item)
            
            if memory_item:
                self.stats["items_retrieved"] += 1
            
            return memory_item
            
        except Exception as e:
            self.stats["retrieval_errors"] += 1
            self.logger.error(f"Error retrieving memory {memory_id}: {e}")
            raise MemoryRetrievalError(f"Retrieval failed: {str(e)}")
    
    async def search_memories(
        self,
        query: str = None,
        tags: List[str] = None,
        memory_types: List[MemoryType] = None,
        importance_min: MemoryImportance = None,
        agent_id: str = None,
        task_id: str = None,
        session_id: str = None,
        time_range: tuple = None,
        limit: int = 10,
        retriever_name: str = None,
        store_name: str = None
    ) -> List[MemoryItem]:
        """
        Search for relevant memories
        
        Args:
            query: Search query text
            tags: Tags to filter by
            memory_types: Memory types to include
            importance_min: Minimum importance level
            agent_id: Agent identifier filter
            task_id: Task identifier filter
            session_id: Session identifier filter
            time_range: Time range filter (start, end)
            limit: Maximum results
            retriever_name: Specific retriever to use
            store_name: Specific store to use
            
        Returns:
            List of matching memory items
        """
        try:
            if query and retriever_name:
                # Use specific retriever for semantic search
                retriever = self.get_retriever(retriever_name)
                context = {
                    "agent_id": agent_id,
                    "task_id": task_id,
                    "session_id": session_id
                }
                memories = await retriever.retrieve_relevant(query, context, limit)
            else:
                # Use store search
                memory_query = MemoryQuery(
                    content=query,
                    tags=tags or [],
                    memory_types=memory_types or [],
                    importance_min=importance_min,
                    agent_id=agent_id,
                    task_id=task_id,
                    session_id=session_id,
                    time_range=time_range,
                    limit=limit
                )
                
                store = self.get_store(store_name)
                memories = await store.search(memory_query)
            
            # Update access for retrieved memories
            for memory in memories:
                memory.update_access()
                try:
                    await self._update_memory(memory, store_name)
                except Exception as e:
                    self.logger.warning(f"Failed to update access for {memory.id}: {e}")
            
            self.stats["searches_performed"] += 1
            return memories
            
        except Exception as e:
            self.stats["search_errors"] += 1
            self.logger.error(f"Error searching memories: {e}")
            raise MemoryRetrievalError(f"Search failed: {str(e)}")
    
    async def retrieve_memories(
        self,
        query: str = None,
        memory_type: MemoryType = None,
        tags: List[str] = None,
        importance_min: MemoryImportance = None,
        agent_id: str = None,
        task_id: str = None,
        session_id: str = None,
        time_range: tuple = None,
        limit: int = 10,
        retriever_name: str = None,
        store_name: str = None
    ) -> List[MemoryItem]:
        """
        Retrieve memories - alias for search_memories with single memory_type support
        """
        memory_types = [memory_type] if memory_type else None
        
        return await self.search_memories(
            query=query,
            tags=tags,
            memory_types=memory_types,
            importance_min=importance_min,
            agent_id=agent_id,
            task_id=task_id,
            session_id=session_id,
            time_range=time_range,
            limit=limit,
            retriever_name=retriever_name,
            store_name=store_name
        )
    
    async def update_memory(
        self,
        memory_id: str,
        content: Any = None,
        tags: List[str] = None,
        importance: MemoryImportance = None,
        metadata: Dict[str, Any] = None,
        store_name: str = None
    ) -> bool:
        """
        Update a memory item
        
        Args:
            memory_id: Memory item ID
            content: New content (optional)
            tags: New tags (optional)
            importance: New importance (optional)
            metadata: New metadata (optional)
            store_name: Specific store to use
            
        Returns:
            Success status
        """
        try:
            # Retrieve current memory
            memory_item = await self.retrieve_memory(memory_id, store_name, update_access=False)
            if not memory_item:
                return False
            
            # Update fields
            if content is not None:
                memory_item.content = content
                memory_item.content_hash = memory_item._compute_content_hash()
            
            if tags is not None:
                memory_item.tags = tags
            
            if importance is not None:
                memory_item.importance = importance
            
            if metadata is not None:
                memory_item.metadata.update(metadata)
            
            # Update in store
            store = self.get_store(store_name)
            success = await store.update(memory_item)
            
            if success:
                self.stats["items_updated"] += 1
            
            return success
            
        except Exception as e:
            self.stats["update_errors"] += 1
            self.logger.error(f"Error updating memory {memory_id}: {e}")
            return False
    
    async def delete_memory(self, memory_id: str, store_name: str = None) -> bool:
        """
        Delete a memory item
        
        Args:
            memory_id: Memory item ID
            store_name: Specific store to use
            
        Returns:
            Success status
        """
        try:
            store = self.get_store(store_name)
            success = await store.delete(memory_id)
            
            if success:
                self.stats["items_deleted"] += 1
            
            return success
            
        except Exception as e:
            self.stats["deletion_errors"] += 1
            self.logger.error(f"Error deleting memory {memory_id}: {e}")
            return False
    
    async def consolidate_memories(self, agent_id: str = None):
        """
        Consolidate short-term memories into long-term storage
        
        Args:
            agent_id: Agent identifier to consolidate for
        """
        try:
            self.logger.info("Starting memory consolidation...")
            
            # Get short-term memories
            short_term_query = MemoryQuery(
                memory_types=[MemoryType.SHORT_TERM],
                agent_id=agent_id,
                limit=self.max_short_term_items,
                sort_by="importance"
            )
            
            store = self.get_store()
            short_term_memories = await store.search(short_term_query)
            
            consolidated_count = 0
            
            for memory in short_term_memories:
                # Determine if memory should be consolidated
                should_consolidate = self._should_consolidate(memory)
                
                if should_consolidate:
                    # Convert to long-term memory
                    memory.memory_type = MemoryType.LONG_TERM
                    
                    # Adjust importance based on access patterns
                    memory.importance = self._calculate_consolidated_importance(memory)
                    
                    # Update in store
                    await store.update(memory)
                    consolidated_count += 1
                
                elif memory.is_expired() or memory.importance == MemoryImportance.MINIMAL:
                    # Delete low-importance or expired memories
                    await store.delete(memory.id)
                    self.stats["items_cleaned"] += 1
            
            self.stats["consolidation_runs"] += 1
            self.stats["items_consolidated"] += consolidated_count
            
            self.logger.info(f"Consolidated {consolidated_count} memories")
            
        except Exception as e:
            self.logger.error(f"Error during memory consolidation: {e}")
    
    async def cleanup_expired(self, store_name: str = None) -> int:
        """
        Clean up expired memories
        
        Args:
            store_name: Specific store to clean
            
        Returns:
            Number of items cleaned
        """
        try:
            store = self.get_store(store_name)
            cleaned_count = await store.cleanup_expired()
            
            self.stats["cleanup_runs"] += 1
            self.stats["items_cleaned"] += cleaned_count
            
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            return 0
    
    async def get_memory_stats(self, store_name: str = None) -> Dict[str, Any]:
        """
        Get memory statistics
        
        Args:
            store_name: Specific store to get stats for
            
        Returns:
            Statistics dictionary
        """
        try:
            store_stats = {}
            
            if store_name:
                store = self.get_store(store_name)
                store_stats[store_name] = await store.get_stats()
            else:
                for name, store in self.stores.items():
                    store_stats[name] = await store.get_stats()
            
            return {
                "manager_stats": dict(self.stats),
                "store_stats": store_stats,
                "config": self.config
            }
            
        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}
    
    async def _find_duplicate(
        self, 
        memory_item: MemoryItem, 
        store_name: str = None
    ) -> Optional[MemoryItem]:
        """Find duplicate memory item"""
        if not memory_item.content_hash:
            return None
        
        try:
            # Search for items with same content hash
            query = MemoryQuery(
                agent_id=memory_item.agent_id,
                limit=5
            )
            
            store = self.get_store(store_name)
            existing_items = await store.search(query)
            
            for item in existing_items:
                if item.content_hash == memory_item.content_hash:
                    return item
            
            return None
            
        except Exception:
            return None
    
    async def _update_memory(self, memory_item: MemoryItem, store_name: str = None):
        """Update memory item in store"""
        store = self.get_store(store_name)
        await store.update(memory_item)
    
    def _should_consolidate(self, memory: MemoryItem) -> bool:
        """Determine if memory should be consolidated to long-term"""
        # High importance memories
        if memory.importance.value >= MemoryImportance.HIGH.value:
            return True
        
        # Frequently accessed memories
        age_hours = memory.get_age_seconds() / 3600
        if memory.access_count > 3 and age_hours > 24:
            return True
        
        # Tagged as important
        important_tags = {"important", "key", "critical", "remember"}
        if any(tag in important_tags for tag in memory.tags):
            return True
        
        return False
    
    def _calculate_consolidated_importance(self, memory: MemoryItem) -> MemoryImportance:
        """Calculate importance for consolidated memory"""
        # Base importance
        importance_score = memory.importance.value
        
        # Adjust based on access frequency
        access_boost = min(2, memory.access_count / 5)
        importance_score += access_boost
        
        # Adjust based on age (older memories may be less important)
        age_days = memory.get_age_seconds() / (24 * 3600)
        age_penalty = min(1, age_days / 30)  # Penalty after 30 days
        importance_score -= age_penalty
        
        # Clamp to valid range
        importance_score = max(1, min(5, importance_score))
        
        return MemoryImportance(int(importance_score))
    
    def _start_background_tasks(self):
        """Start background consolidation and cleanup tasks"""
        try:
            # 检查是否有运行的事件循环
            loop = asyncio.get_running_loop()
            
            if self.config.get("enable_consolidation", True):
                self._consolidation_task = asyncio.create_task(
                    self._consolidation_loop()
                )
            
            if self.config.get("enable_cleanup", True):
                self._cleanup_task = asyncio.create_task(
                    self._cleanup_loop()
                )
        except RuntimeError:
            # 没有运行的事件循环，在同步环境中跳过后台任务
            print("LongTermMemoryManager: No running event loop, skipping background tasks")
            self._consolidation_task = None
            self._cleanup_task = None
    
    async def _consolidation_loop(self):
        """Background consolidation loop"""
        while True:
            try:
                await asyncio.sleep(self.consolidation_interval)
                await self.consolidate_memories()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in consolidation loop: {e}")
    
    async def _cleanup_loop(self):
        """Background cleanup loop"""
        cleanup_interval = self.config.get("cleanup_interval", 1800)  # 30 minutes
        
        while True:
            try:
                await asyncio.sleep(cleanup_interval)
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {e}")
    
    async def close(self):
        """Close memory manager and cleanup resources"""
        if self._consolidation_task:
            self._consolidation_task.cancel()
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        self.logger.info("Memory manager closed")

"""
Redis Service for callback data storage and retrieval
"""
import json
import logging
import asyncio
from typing import Any, Optional, Dict
from redis import asyncio as aioredis
from ..core.config import settings

logger = logging.getLogger(__name__)


class RedisService:
    """Redis service for storing and retrieving callback data"""
    
    def __init__(self):
        self._redis = None
        self._lock = asyncio.Lock()
    
    async def _get_redis(self):
        """Get Redis connection (lazy initialization)"""
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    try:
                        self._redis = await aioredis.from_url(
                            settings.REDIS_URL,
                            decode_responses=True,
                            retry_on_timeout=True,
                            health_check_interval=30
                        )
                        # Test connection
                        await self._redis.ping()
                        logger.info("Redis connection established successfully")
                    except Exception as e:
                        logger.error(f"Failed to connect to Redis: {e}")
                        raise
        return self._redis
    
    async def store_callback_result(
        self, 
        task_id: str, 
        result: Dict[str, Any], 
        ttl: int = 3600
    ) -> bool:
        """Store callback result in Redis with TTL"""
        try:
            redis = await self._get_redis()
            key = f"suno_callback:{task_id}"
            
            # Store as JSON string
            await redis.setex(
                key, 
                ttl, 
                json.dumps(result, ensure_ascii=False)
            )
            
            logger.info(f"Stored callback result for task {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store callback result for task {task_id}: {e}")
            return False
    
    async def get_callback_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve callback result from Redis"""
        try:
            redis = await self._get_redis()
            key = f"suno_callback:{task_id}"
            
            result_json = await redis.get(key)
            if result_json:
                result = json.loads(result_json)
                logger.info(f"Retrieved callback result for task {task_id}")
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get callback result for task {task_id}: {e}")
            return None
    
    async def delete_callback_result(self, task_id: str) -> bool:
        """Delete callback result from Redis"""
        try:
            redis = await self._get_redis()
            key = f"suno_callback:{task_id}"
            
            deleted = await redis.delete(key)
            if deleted:
                logger.info(f"Deleted callback result for task {task_id}")
            
            return bool(deleted)
            
        except Exception as e:
            logger.error(f"Failed to delete callback result for task {task_id}: {e}")
            return False
    
    async def wait_for_callback(
        self, 
        task_id: str, 
        timeout: int = 300,  # 5 minutes default
        check_interval: float = 1.0  # Check every 1 second
    ) -> Optional[Dict[str, Any]]:
        """Wait for callback result with polling"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            # Check if result is available
            result = await self.get_callback_result(task_id)
            if result is not None:
                return result
            
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Callback wait timeout for task {task_id} after {elapsed:.1f}s")
                return None
            
            # Wait before next check
            await asyncio.sleep(check_interval)
    
    async def set_callback_event(self, task_id: str) -> bool:
        """Set an event flag for callback completion"""
        try:
            redis = await self._get_redis()
            key = f"suno_event:{task_id}"
            
            # Set event with 1 hour TTL
            await redis.setex(key, 3600, "completed")
            
            logger.info(f"Set callback event for task {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set callback event for task {task_id}: {e}")
            return False
    
    async def wait_for_callback_event(
        self, 
        task_id: str, 
        timeout: int = 300,
        check_interval: float = 0.5
    ) -> bool:
        """Wait for callback event (more efficient than polling results)"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            redis = await self._get_redis()
            event_key = f"suno_event:{task_id}"
            
            while True:
                # Check if event is set
                if await redis.exists(event_key):
                    logger.info(f"Callback event received for task {task_id}")
                    return True
                
                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    logger.warning(f"Callback event wait timeout for task {task_id} after {elapsed:.1f}s")
                    return False
                
                # Wait before next check
                await asyncio.sleep(check_interval)
                
        except Exception as e:
            logger.error(f"Error waiting for callback event {task_id}: {e}")
            return False
    
    async def cleanup_callback_data(self, task_id: str) -> bool:
        """Clean up all callback-related data for a task"""
        try:
            redis = await self._get_redis()
            
            keys_to_delete = [
                f"suno_callback:{task_id}",
                f"suno_event:{task_id}"
            ]
            
            deleted = await redis.delete(*keys_to_delete)
            logger.info(f"Cleaned up {deleted} callback entries for task {task_id}")
            
            return deleted > 0
            
        except Exception as e:
            logger.error(f"Failed to cleanup callback data for task {task_id}: {e}")
            return False
    
    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")


# Global Redis service instance
redis_service = RedisService()
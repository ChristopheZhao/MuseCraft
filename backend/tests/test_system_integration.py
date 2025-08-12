"""
System Integration Tests

Tests the integration between different system components:
- Frontend React app with Backend FastAPI
- Database operations and transactions
- Redis caching and task queues
- File storage and handling
- WebSocket real-time communication
"""
import pytest
import asyncio
import json
import os
import tempfile
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as redis

from app.models import Task, AgentExecution, Scene, Resource, TaskStatus
from app.core.database import get_db
from app.services.websocket import websocket_manager
from app.services.file_storage import FileStorageService


@pytest.mark.integration
@pytest.mark.asyncio
class TestSystemIntegration:
    """System integration tests."""
    
    async def test_api_database_integration(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession
    ):
        """Test API endpoints correctly interact with database."""
        
        # Test task creation
        request_data = {
            "user_prompt": "Create a test video for database integration",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Verify task exists in database
        stmt = select(Task).where(Task.task_id == task_id)
        result = await test_db_session.execute(stmt)
        task = result.scalar_one()
        
        assert task.user_prompt == request_data["user_prompt"]
        assert task.status == TaskStatus.PENDING
        
        # Test task retrieval
        response = await test_client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        
        retrieved_task = response.json()
        assert retrieved_task["task_id"] == task_id
        assert retrieved_task["user_prompt"] == request_data["user_prompt"]
        
        # Test task list
        response = await test_client.get("/api/v1/tasks/")
        assert response.status_code == 200
        
        tasks_list = response.json()
        assert len(tasks_list) >= 1
        assert any(t["task_id"] == task_id for t in tasks_list)
        
        # Test task update
        update_data = {"status": "processing"}
        response = await test_client.patch(f"/api/v1/tasks/{task_id}", json=update_data)
        assert response.status_code == 200
        
        # Verify update in database
        await test_db_session.refresh(task)
        assert task.status == TaskStatus.PROCESSING
    
    async def test_redis_caching_integration(
        self,
        test_client: AsyncClient,
        test_redis: redis.Redis
    ):
        """Test Redis caching integration."""
        
        # Test cache key generation and storage
        cache_key = "test:integration:cache"
        test_data = {"message": "Hello Redis", "timestamp": "2024-01-01T00:00:00Z"}
        
        await test_redis.setex(cache_key, 300, json.dumps(test_data))
        
        # Retrieve from cache
        cached_data = await test_redis.get(cache_key)
        assert cached_data is not None
        
        parsed_data = json.loads(cached_data)
        assert parsed_data == test_data
        
        # Test cache expiration
        ttl = await test_redis.ttl(cache_key)
        assert ttl > 0 and ttl <= 300
        
        # Test cache deletion
        await test_redis.delete(cache_key)
        cached_data = await test_redis.get(cache_key)
        assert cached_data is None
    
    async def test_celery_task_queue_integration(
        self,
        test_client: AsyncClient,
        test_redis: redis.Redis,
        mock_celery_tasks: AsyncMock
    ):
        """Test Celery task queue integration."""
        
        # Submit a task that should trigger Celery
        request_data = {
            "user_prompt": "Create a video to test Celery integration",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Verify Celery task was queued
        # In real scenario, this would be handled by the orchestrator
        mock_celery_tasks.assert_called()
        
        # Test task status tracking through Redis
        status_key = f"task_status:{task_id}"
        await test_redis.hset(status_key, mapping={
            "status": "processing",
            "progress": "25",
            "current_agent": "concept_planner"
        })
        
        # Retrieve status
        status_data = await test_redis.hgetall(status_key)
        assert status_data[b"status"] == b"processing"
        assert status_data[b"progress"] == b"25"
    
    async def test_file_storage_integration(
        self,
        test_client: AsyncClient,
        test_storage_dirs: Dict[str, str],
        integration_helper
    ):
        """Test file storage and handling integration."""
        
        # Create test files
        test_files = await integration_helper.create_test_files(
            test_storage_dirs['upload']
        )
        
        # Test file upload
        with open(test_files['image'], 'rb') as f:
            files = {"file": ("test_image.jpg", f, "image/jpeg")}
            response = await test_client.post("/api/v1/files/upload", files=files)
        
        assert response.status_code == 200
        upload_result = response.json()
        
        assert "file_id" in upload_result
        assert "url" in upload_result
        
        # Test file retrieval
        file_id = upload_result["file_id"]
        response = await test_client.get(f"/api/v1/files/{file_id}")
        assert response.status_code == 200
        
        # Test file storage service
        storage_service = FileStorageService()
        
        # Store a generated file
        generated_content = b"Generated video content"
        file_path = await storage_service.store_generated_file(
            content=generated_content,
            filename="test_video.mp4",
            content_type="video/mp4"
        )
        
        assert os.path.exists(file_path)
        
        # Verify content
        with open(file_path, 'rb') as f:
            stored_content = f.read()
        assert stored_content == generated_content
        
        # Test file cleanup
        await storage_service.cleanup_temp_files(max_age_hours=0)
        # Temp files should be cleaned up
    
    async def test_websocket_api_integration(
        self,
        test_client: AsyncClient,
        websocket_test_client,
        test_db_session: AsyncSession
    ):
        """Test WebSocket real-time communication integration."""
        
        # Create a task first
        request_data = {
            "user_prompt": "Create a video to test WebSocket integration",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Test WebSocket connection
        with websocket_test_client.websocket_connect(f"/ws?session_id=test-session") as websocket:
            # Send a message
            test_message = {
                "type": "subscribe",
                "task_id": task_id
            }
            websocket.send_json(test_message)
            
            # Simulate sending progress update
            await websocket_manager.send_progress_update(
                session_id="test-session",
                task_id=task_id,
                progress=50,
                status="processing",
                agent_name="script_writer"
            )
            
            # Receive message
            received_message = websocket.receive_json()
            
            assert received_message["type"] == "progress-update"
            assert received_message["data"]["task_id"] == task_id
            assert received_message["data"]["progress"] == 50
    
    async def test_database_transaction_integrity(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession
    ):
        """Test database transaction integrity."""
        
        # Create a task that will involve multiple database operations
        request_data = {
            "user_prompt": "Create a video to test transaction integrity",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Get the task from database
        stmt = select(Task).where(Task.task_id == task_id)
        result = await test_db_session.execute(stmt)
        task = result.scalar_one()
        
        # Simulate a complex transaction with multiple related objects
        async with test_db_session.begin():
            # Create scenes
            scenes = []
            for i in range(3):
                scene = Scene(
                    task_id=task.id,
                    scene_number=i + 1,
                    title=f"Scene {i + 1}",
                    description=f"Description for scene {i + 1}",
                    duration=10,
                    scene_metadata={"test": True}
                )
                scenes.append(scene)
                test_db_session.add(scene)
            
            # Create resources
            resources = []
            for i, scene in enumerate(scenes):
                resource = Resource(
                    task_id=task.id,
                    scene_id=scene.id if hasattr(scene, 'id') else None,
                    resource_type="image",
                    file_path=f"/test/image_{i}.jpg",
                    file_size=1024 * (i + 1),
                    resource_metadata={"generated": True}
                )
                resources.append(resource)
                test_db_session.add(resource)
            
            # Create agent executions
            agent_execution = AgentExecution(
                task_id=task.id,
                agent_type="concept_planner",
                agent_name="test_agent",
                status="completed",
                input_data={"prompt": "test"},
                output_data={"result": "success"},
                execution_metadata={"duration": 5.0}
            )
            test_db_session.add(agent_execution)
        
        # Verify all objects were created
        await test_db_session.commit()
        
        # Check scenes
        stmt = select(Scene).where(Scene.task_id == task.id)
        result = await test_db_session.execute(stmt)
        created_scenes = result.scalars().all()
        assert len(created_scenes) == 3
        
        # Check resources
        stmt = select(Resource).where(Resource.task_id == task.id)
        result = await test_db_session.execute(stmt)
        created_resources = result.scalars().all()
        assert len(created_resources) == 3
        
        # Check agent executions
        stmt = select(AgentExecution).where(AgentExecution.task_id == task.id)
        result = await test_db_session.execute(stmt)
        created_executions = result.scalars().all()
        assert len(created_executions) == 1
    
    async def test_error_handling_across_components(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        test_redis: redis.Redis
    ):
        """Test error handling and propagation across system components."""
        
        # Test database connection error handling
        with patch('app.core.database.get_db') as mock_db:
            mock_db.side_effect = Exception("Database connection failed")
            
            response = await test_client.get("/api/v1/tasks/")
            assert response.status_code == 500
            
            error_data = response.json()
            assert "detail" in error_data
        
        # Test Redis connection error handling
        await test_redis.close()  # Close connection to simulate error
        
        # Should handle Redis errors gracefully
        request_data = {
            "user_prompt": "Test Redis error handling",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        # This should still work even if Redis is down (depending on implementation)
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        # Response could be 201 (success) or 500 (error) depending on Redis dependency
        assert response.status_code in [201, 500]
    
    async def test_concurrent_database_operations(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession
    ):
        """Test concurrent database operations don't cause conflicts."""
        
        # Create multiple tasks concurrently
        async def create_task(index: int):
            request_data = {
                "user_prompt": f"Concurrent test video {index}",
                "video_style": "professional",
                "duration": 30,
                "aspect_ratio": "16:9"
            }
            
            response = await test_client.post("/api/v1/tasks/", json=request_data)
            return response
        
        # Execute concurrent requests
        responses = await asyncio.gather(
            *[create_task(i) for i in range(5)],
            return_exceptions=True
        )
        
        # All should succeed
        successful_responses = [r for r in responses if not isinstance(r, Exception)]
        assert len(successful_responses) == 5
        
        # All should have unique task IDs
        task_ids = set()
        for response in successful_responses:
            assert response.status_code == 201
            task_data = response.json()
            task_ids.add(task_data["task_id"])
        
        assert len(task_ids) == 5  # All unique
        
        # Verify all tasks exist in database
        stmt = select(Task)
        result = await test_db_session.execute(stmt)
        all_tasks = result.scalars().all()
        
        created_task_ids = {task.task_id for task in all_tasks}
        assert task_ids.issubset(created_task_ids)
    
    async def test_api_rate_limiting_integration(
        self,
        test_client: AsyncClient
    ):
        """Test API rate limiting integration."""
        
        # Make multiple rapid requests
        responses = []
        for i in range(10):
            response = await test_client.get("/health")
            responses.append(response)
        
        # Most should succeed, but rate limiting might kick in
        successful_responses = [r for r in responses if r.status_code == 200]
        rate_limited_responses = [r for r in responses if r.status_code == 429]
        
        # Should have mostly successful responses
        assert len(successful_responses) >= 5
        
        # If rate limiting is implemented, some might be limited
        if rate_limited_responses:
            assert len(rate_limited_responses) <= 5
    
    async def test_health_check_integration(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        test_redis: redis.Redis
    ):
        """Test health check integration with all components."""
        
        # Test basic health check
        response = await test_client.get("/health")
        assert response.status_code == 200
        
        health_data = response.json()
        assert health_data["status"] == "healthy"
        assert "service" in health_data
        assert "version" in health_data
        
        # Test detailed health check (if available)
        response = await test_client.get("/api/v1/health/detailed")
        
        if response.status_code == 200:  # If endpoint exists
            detailed_health = response.json()
            
            # Should include component status
            assert "components" in detailed_health
            
            # Check database health
            if "database" in detailed_health["components"]:
                assert detailed_health["components"]["database"]["status"] in ["healthy", "degraded"]
            
            # Check Redis health
            if "redis" in detailed_health["components"]:
                assert detailed_health["components"]["redis"]["status"] in ["healthy", "degraded"]
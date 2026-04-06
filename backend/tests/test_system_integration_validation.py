"""
System Integration Validation Test Suite

This module validates all system component integrations, ensuring proper
communication, data flow, and error handling between different parts of
the video generation platform.
"""
import asyncio
import json
import time
import psutil
import redis
from typing import Dict, List, Any, Optional
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import websockets

from app.core.config import settings
from app.core.database import get_db
from app.models import Task, Resource
from app.services.ai_client import enhanced_ai_client
from app.services.websocket import websocket_manager
from app.services.file_storage import file_storage_service
from app.services.task_queue import task_queue_service
from app.services.monitoring_service import monitoring_service


@pytest.mark.integration
@pytest.mark.asyncio
class TestSystemIntegrationValidation:
    """System integration validation tests."""
    
    async def test_database_redis_integration(
        self,
        test_db_session: AsyncSession,
        test_redis
    ):
        """Test database and Redis integration for session management."""
        
        # Test database connection
        result = await test_db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1
        
        # Test Redis connection
        await test_redis.set("test_key", "test_value")
        value = await test_redis.get("test_key")
        assert value.decode() == "test_value"
        
        # Test session synchronization
        session_id = "integration-test-session"
        session_data = {
            "user_id": "test-user-123",
            "active_tasks": ["task1", "task2"],
            "preferences": {"theme": "dark"}
        }
        
        # Store in Redis
        await test_redis.setex(
            f"session:{session_id}",
            3600,
            json.dumps(session_data)
        )
        
        # Verify cross-reference with database
        task = Task(
            task_id="task1",
            title="Integration Test Task",
            user_prompt="Test prompt",
            session_id=session_id,
            status="pending"
        )
        test_db_session.add(task)
        await test_db_session.commit()
        
        # Retrieve and validate
        stored_session = await test_redis.get(f"session:{session_id}")
        session_data_retrieved = json.loads(stored_session.decode())
        
        assert "task1" in session_data_retrieved["active_tasks"]
        
        # Verify database consistency
        stmt = select(Task).where(Task.session_id == session_id)
        db_tasks = await test_db_session.execute(stmt)
        task_results = db_tasks.scalars().all()
        
        assert len(task_results) == 1
        assert task_results[0].task_id == "task1"
    
    async def test_api_websocket_integration(
        self,
        test_client: AsyncClient,
        mock_websocket: MagicMock
    ):
        """Test API and WebSocket integration for real-time updates."""
        
        # Submit task via API
        request_data = {
            "user_prompt": "Test WebSocket integration",
            "video_style": "professional",
            "duration": 30,
            "session_id": "websocket-integration-test"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]

        websocket_manager.active_connections.add(mock_websocket)
        websocket_manager.task_connections[task_id] = {mock_websocket}

        try:
            await websocket_manager.broadcast_to_task(task_id, {
                "type": "task_notification",
                "task_id": task_id,
                "message": "Task created",
                "level": "info",
            })

            await websocket_manager.broadcast_to_task(task_id, {
                "type": "event.progress",
                "agent_type": "script_writer",
                "payload": {
                    "progress": 50,
                    "current_step": "processing",
                },
            })

            assert len(mock_websocket.messages) >= 2

            messages = [
                json.loads(msg) if isinstance(msg, str) else msg
                for msg in mock_websocket.messages
            ]

            task_created_msg = next(
                (msg for msg in messages if isinstance(msg, dict) and msg.get("type") == "task_notification"),
                None
            )
            assert task_created_msg is not None
            assert task_created_msg["task_id"] == task_id

            progress_msg = next(
                (msg for msg in messages if isinstance(msg, dict) and msg.get("type") == "event.progress"),
                None
            )
            assert progress_msg is not None
            assert progress_msg["payload"]["progress"] == 50
        finally:
            websocket_manager.task_connections.pop(task_id, None)
            websocket_manager.active_connections.discard(mock_websocket)
    
    async def test_ai_service_integration_chain(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test integration chain between different AI services."""
        
        # Configure service chain responses
        mock_ai_services['openai'].chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps({
                "concept": "Test video concept",
                "scenes": [{"title": "Scene 1", "description": "Test scene"}]
            })))
        ]
        
        mock_ai_services['stability'].generate.return_value = MagicMock(
            artifacts=[MagicMock(seed=123, binary=b"generated_image_data")]
        )
        
        mock_ai_services['elevenlabs'] = AsyncMock()
        mock_ai_services['elevenlabs'].generate.return_value = b"generated_audio_data"
        
        # Test service chain execution
        with patch('app.services.ai_client.openai_client', mock_ai_services['openai']):
            concept_result = await enhanced_ai_client.chat_completion(
                "Generate a video concept",
                model="gpt-4"
            )
        
        assert "concept" in concept_result
        
        with patch('app.services.ai_client.stability_client', mock_ai_services['stability']):
            image_result = await enhanced_ai_client.generate_image(
                "A professional scene",
                style="photographic"
            )
        
        assert image_result is not None
        
        # Verify service call sequencing
        assert mock_ai_services['openai'].chat.completions.create.called
        assert mock_ai_services['stability'].generate.called
    
    async def test_file_storage_integration(
        self,
        test_storage_dirs: Dict[str, str],
        test_client: AsyncClient
    ):
        """Test file storage integration across upload, processing, and output."""
        
        # Test file upload
        test_file_content = b"test file content for integration"
        files = {"files": ("test.txt", test_file_content, "text/plain")}
        
        upload_response = await test_client.post(
            "/api/v1/files/upload",
            files=files
        )
        assert upload_response.status_code == 200
        
        upload_data = upload_response.json()
        file_id = upload_data["files"][0]["file_id"]
        
        # Verify file was stored correctly
        stored_file_path = file_storage_service.get_file_path(file_id)
        assert stored_file_path is not None
        
        with open(stored_file_path, 'rb') as f:
            stored_content = f.read()
        assert stored_content == test_file_content
        
        # Test file processing simulation
        processed_file_id = await file_storage_service.process_file(
            file_id,
            processing_type="video_generation"
        )
        
        # Test file retrieval
        retrieval_response = await test_client.get(f"/api/v1/files/{file_id}")
        assert retrieval_response.status_code == 200
        
        # Test file cleanup
        cleanup_result = await file_storage_service.cleanup_temporary_files(
            older_than_hours=0
        )
        assert cleanup_result["files_cleaned"] >= 0
    
    async def test_task_queue_integration(
        self,
        test_db_session: AsyncSession,
        test_redis,
        mock_celery_tasks: AsyncMock
    ):
        """Test task queue integration with database and Redis."""
        
        # Create test task
        task = Task(
            task_id="queue-integration-test",
            title="Queue Integration Test",
            user_prompt="Test queue integration",
            status="pending"
        )
        test_db_session.add(task)
        await test_db_session.commit()
        
        # Queue task for processing
        queue_result = await task_queue_service.queue_task(
            task_id=task.task_id,
            agent_type="concept_planner",
            input_data={"prompt": "test"},
            priority="normal"
        )
        
        assert queue_result["queued"] is True
        assert queue_result["queue_position"] >= 0
        
        # Verify task status in Redis queue
        queue_info = await test_redis.llen("task_queue:normal")
        assert queue_info >= 1
        
        # Simulate task processing
        processing_result = await task_queue_service.process_next_task("normal")
        assert processing_result is not None
        
        # Verify database status update
        await test_db_session.refresh(task)
        assert task.status in ["processing", "completed"]
    
    async def test_monitoring_integration(
        self,
        test_db_session: AsyncSession,
        test_redis
    ):
        """Test monitoring service integration with system components."""
        
        # Start monitoring
        await monitoring_service.start_monitoring()
        
        # Create test metrics
        metrics_data = {
            "cpu_usage": 45.2,
            "memory_usage": 1024.5,
            "active_tasks": 3,
            "queue_size": 5,
            "api_response_time": 0.25
        }
        
        # Record metrics
        await monitoring_service.record_metrics(metrics_data)
        
        # Verify metrics storage in Redis
        stored_metrics = await test_redis.get("metrics:latest")
        assert stored_metrics is not None
        
        metrics_parsed = json.loads(stored_metrics.decode())
        assert metrics_parsed["cpu_usage"] == 45.2
        assert metrics_parsed["memory_usage"] == 1024.5
        
        # Test threshold alerts
        high_usage_metrics = {
            "cpu_usage": 95.0,  # High CPU usage
            "memory_usage": 8192.0,  # High memory usage
            "queue_size": 100  # Large queue
        }
        
        alert_result = await monitoring_service.check_thresholds(high_usage_metrics)
        assert alert_result["alerts_triggered"] > 0
        assert "cpu_usage" in alert_result["alert_types"]
    
    async def test_performance_under_load_integration(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test system integration under simulated load."""
        
        # Configure fast mock responses
        mock_ai_services['openai'].chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="Quick response"))
        ]
        
        # Create concurrent requests
        concurrent_requests = 10
        tasks = []
        
        for i in range(concurrent_requests):
            request_data = {
                "user_prompt": f"Load test video {i}",
                "video_style": "professional",
                "duration": 30
            }
            
            task = asyncio.create_task(
                test_client.post("/api/v1/tasks/", json=request_data)
            )
            tasks.append(task)
        
        # Execute all requests concurrently
        start_time = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        execution_time = time.time() - start_time
        
        # Verify responses
        successful_responses = [
            r for r in responses 
            if not isinstance(r, Exception) and r.status_code == 201
        ]
        
        assert len(successful_responses) >= concurrent_requests * 0.8  # 80% success rate
        assert execution_time < 10.0  # Should complete within 10 seconds
        
        # Check system resource usage
        system_metrics = await self._get_system_metrics()
        assert system_metrics["cpu_usage"] < 90.0  # Should not max out CPU
        assert system_metrics["memory_usage"] < 1000.0  # Memory usage in MB
    
    async def test_data_consistency_integration(
        self,
        test_db_session: AsyncSession,
        test_redis
    ):
        """Test data consistency across database and cache layers."""
        
        # Create task in database
        task = Task(
            task_id="consistency-test-123",
            title="Data Consistency Test",
            user_prompt="Test consistency",
            status="processing",
            progress=50
        )
        test_db_session.add(task)
        await test_db_session.commit()
        
        # Update cache
        cache_key = f"task:{task.task_id}"
        cache_data = {
            "status": "processing",
            "progress": 50,
            "last_updated": time.time()
        }
        await test_redis.setex(cache_key, 3600, json.dumps(cache_data))
        
        # Simulate status update
        task.status = "completed"
        task.progress = 100
        await test_db_session.commit()
        
        # Update cache
        cache_data["status"] = "completed"
        cache_data["progress"] = 100
        cache_data["last_updated"] = time.time()
        await test_redis.setex(cache_key, 3600, json.dumps(cache_data))
        
        # Verify consistency
        # Check database
        stmt = select(Task).where(Task.task_id == task.task_id)
        db_result = await test_db_session.execute(stmt)
        db_task = db_result.scalar_one()
        
        # Check cache
        cached_data = await test_redis.get(cache_key)
        cache_task = json.loads(cached_data.decode())
        
        # Verify consistency
        assert db_task.status == cache_task["status"]
        assert db_task.progress == cache_task["progress"]
    
    async def _get_system_metrics(self) -> Dict[str, float]:
        """Get current system metrics for testing."""
        
        return {
            "cpu_usage": psutil.cpu_percent(interval=1),
            "memory_usage": psutil.virtual_memory().used / (1024 * 1024),  # MB
            "disk_usage": psutil.disk_usage('/').percent
        }


@pytest.mark.integration
@pytest.mark.asyncio
class TestComponentBoundaryValidation:
    """Test validation of component boundaries and interfaces."""
    
    async def test_api_contract_validation(self, test_client: AsyncClient):
        """Validate API contracts and response schemas."""
        
        # Test task creation endpoint
        valid_request = {
            "user_prompt": "Create a test video",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=valid_request)
        assert response.status_code == 201
        
        response_data = response.json()
        required_fields = ["task_id", "title", "status", "created_at"]
        for field in required_fields:
            assert field in response_data
        
        # Test invalid request handling
        invalid_request = {
            "user_prompt": "",  # Empty prompt
            "duration": -1  # Invalid duration
        }
        
        response = await test_client.post("/api/v1/tasks/", json=invalid_request)
        assert response.status_code == 422  # Validation error
    
    async def test_database_model_validation(self, test_db_session: AsyncSession):
        """Validate database model constraints and relationships."""
        
        # Test valid task creation
        valid_task = Task(
            task_id="valid-task-123",
            title="Valid Task",
            user_prompt="Valid prompt",
            status="pending"
        )
        
        test_db_session.add(valid_task)
        await test_db_session.commit()
        
        # Test constraint violations
        with pytest.raises(Exception):  # Should raise integrity error
            duplicate_task = Task(
                task_id="valid-task-123",  # Duplicate ID
                title="Duplicate Task",
                user_prompt="Another prompt",
                status="pending"
            )
            test_db_session.add(duplicate_task)
            await test_db_session.commit()
    
    async def test_service_interface_validation(self):
        """Validate service interfaces and method contracts."""
        
        # Test file storage service interface
        with pytest.raises(ValueError):
            await file_storage_service.store_file(
                file_data=None,  # Invalid file data
                filename="test.txt"
            )
        
        # Test monitoring service interface
        with pytest.raises(TypeError):
            await monitoring_service.record_metrics(
                "invalid_metrics"  # Should be dict, not string
            )

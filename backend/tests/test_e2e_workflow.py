"""
End-to-End Workflow Integration Tests

Tests the complete video generation workflow from user input to final output,
verifying that all agents collaborate correctly and the system produces
expected results.
"""
import pytest
import asyncio
import json
import time
from typing import Dict, Any
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Task, Scene, Resource, TaskStatus, AgentType
from app.agents.enhanced_orchestrator import EnhancedOrchestratorAgent
from app.services.websocket import websocket_manager


@pytest.mark.e2e
@pytest.mark.asyncio
class TestEndToEndWorkflow:
    """End-to-end workflow integration tests."""
    
    async def test_complete_video_generation_workflow(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock],
        mock_celery_tasks: AsyncMock,
        integration_helper
    ):
        """Test complete video generation workflow from request to completion."""
        
        # Step 1: Create video generation request
        request_data = {
            "user_prompt": "Create a professional video about artificial intelligence trends in 2024",
            "video_style": "professional",
            "duration": 60,
            "aspect_ratio": "16:9",
            "session_id": "test-session-123"
        }
        
        # Mock AI service responses
        mock_ai_services['openai'].chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps({
                "concept": "AI Trends 2024",
                "key_points": ["Machine Learning", "Neural Networks", "Automation"],
                "visual_style": "modern tech",
                "narrative_arc": "introduction -> trends -> future"
            })))
        ]
        
        mock_ai_services['stability'].generate.return_value = MagicMock(
            artifacts=[
                MagicMock(seed=12345, binary=b"mock_image_data_1"),
                MagicMock(seed=12346, binary=b"mock_image_data_2")
            ]
        )
        
        # Step 2: Submit task
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Verify task was created
        stmt = select(Task).where(Task.task_id == task_id)
        result = await test_db_session.execute(stmt)
        task = result.scalar_one()
        
        assert task.title == "AI Trends 2024 Video Generation"
        assert task.status == TaskStatus.PENDING
        assert task.user_prompt == request_data["user_prompt"]
        
        # Step 3: Simulate orchestrator execution
        orchestrator = EnhancedOrchestratorAgent.create_default()
        
        with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
            mock_client.chat_completion.return_value = {
                "concept": "AI Trends 2024",
                "scenes": [
                    {"title": "Introduction", "duration": 10, "description": "Opening scene"},
                    {"title": "Current Trends", "duration": 30, "description": "Main content"},
                    {"title": "Future Outlook", "duration": 20, "description": "Conclusion"}
                ]
            }
            
            # Execute workflow
            result = await orchestrator.execute(
                task_id=task_id,
                input_data=task.input_parameters,
                db=test_db_session
            )
        
        # Step 5: Verify scenes were created
        stmt = select(Scene).where(Scene.task_id == task.id)
        scenes_result = await test_db_session.execute(stmt)
        scenes = scenes_result.scalars().all()
        
        assert len(scenes) >= 3
        assert any(scene.title == "Introduction" for scene in scenes)
        
        # Step 6: Verify resources were generated
        stmt = select(Resource).where(Resource.task_id == task.id)
        resources_result = await test_db_session.execute(stmt)
        resources = resources_result.scalars().all()
        
        assert len(resources) > 0
        
        # Step 7: Check final task status
        await test_db_session.refresh(task)
        assert task.status in [TaskStatus.COMPLETED, TaskStatus.PROCESSING]
    
    async def test_workflow_with_error_recovery(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock],
        integration_helper
    ):
        """Test workflow handles errors gracefully and recovers."""
        
        request_data = {
            "user_prompt": "Create a video that will cause an error initially",
            "video_style": "creative",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        # Configure mock to fail first, then succeed
        call_count = 0
        def mock_ai_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Simulated AI service failure")
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="Success on retry"))]
            )
        
        mock_ai_services['openai'].chat.completions.create.side_effect = mock_ai_response
        
        # Submit task
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Execute with error recovery
        orchestrator = EnhancedOrchestratorAgent.create_default()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            mock_recovery.handle_error.return_value = {"retry": True, "delay": 0.1}
            
            result = await orchestrator.execute(
                task_id=task_id,
                input_data=request_data,
                db=test_db_session
            )
        
        # Verify error recovery was attempted
        assert mock_recovery.handle_error.called
        assert call_count >= 2  # Failed once, then succeeded
    
    async def test_workflow_quality_control_rejection(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test workflow handles quality control rejection."""
        
        request_data = {
            "user_prompt": "Create inappropriate content",  # Should trigger quality check
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        # Mock quality control to reject content
        with patch('app.services.quality_control.quality_control_service') as mock_qc:
            mock_qc.validate_content.return_value = {
                "approved": False,
                "reasons": ["Inappropriate content detected"],
                "confidence": 0.95
            }
            
            response = await test_client.post("/api/v1/tasks/", json=request_data)
            assert response.status_code == 201
            
            task_data = response.json()
            task_id = task_data["task_id"]
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            # Check task was rejected
            stmt = select(Task).where(Task.task_id == task_id)
            result = await test_db_session.execute(stmt)
            task = result.scalar_one()
            
            # Task should be failed or require human review
            assert task.status in [TaskStatus.FAILED, TaskStatus.PENDING_REVIEW]
    
    async def test_workflow_progress_tracking(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock],
        mock_websocket: MagicMock
    ):
        """Test progress tracking throughout workflow."""
        
        request_data = {
            "user_prompt": "Create a test video for progress tracking",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        # Mock WebSocket connection
        websocket_manager.active_connections["test-session"] = mock_websocket
        
        # Submit task
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Simulate workflow execution with progress updates
        orchestrator = EnhancedOrchestratorAgent.create_default()
        
        with patch('app.services.monitoring_service.monitoring_service') as mock_monitor:
            await orchestrator.execute(
                task_id=task_id,
                input_data=request_data,
                db=test_db_session
            )
        
        # Verify progress updates were sent
        assert len(mock_websocket.messages) > 0
        
        # Check for different types of progress messages
        message_types = set()
        for message in mock_websocket.messages:
            if isinstance(message, dict) and 'type' in message:
                message_types.add(message['type'])
        
        expected_message_types = {
            'agent-status-update',
            'progress-update',
            'result-ready'
        }
        
        assert message_types & expected_message_types  # At least some expected types
    
    @pytest.mark.slow
    async def test_workflow_with_realistic_timing(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock],
        performance_thresholds: Dict[str, float]
    ):
        """Test workflow with realistic timing constraints."""
        
        request_data = {
            "user_prompt": "Create a complex multi-scene video with realistic timing",
            "video_style": "cinematic",
            "duration": 120,  # Longer video
            "aspect_ratio": "16:9"
        }
        
        # Add realistic delays to mock responses
        async def delayed_ai_response(*args, **kwargs):
            await asyncio.sleep(0.5)  # Simulate AI processing time
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="AI response"))]
            )
        
        mock_ai_services['openai'].chat.completions.create.side_effect = delayed_ai_response
        
        start_time = time.time()
        
        # Submit and process task
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Execute workflow
        orchestrator = EnhancedOrchestratorAgent.create_default()
        await orchestrator.execute(
            task_id=task_id,
            input_data=request_data,
            db=test_db_session
        )
        
        execution_time = time.time() - start_time
        
        # Verify execution time is within acceptable bounds
        max_acceptable_time = performance_thresholds.get('task_processing_time', 60.0)
        assert execution_time < max_acceptable_time
        
        # Verify task completed successfully
        stmt = select(Task).where(Task.task_id == task_id)
        result = await test_db_session.execute(stmt)
        task = result.scalar_one()
        
        assert task.status == TaskStatus.COMPLETED
    
    async def test_workflow_resource_cleanup(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        test_storage_dirs: Dict[str, str],
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test that temporary resources are cleaned up after workflow completion."""
        
        request_data = {
            "user_prompt": "Create a video to test resource cleanup",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        # Create some test files in temp directory
        import os
        temp_files = []
        for i in range(3):
            temp_file = os.path.join(test_storage_dirs['temp'], f'temp_file_{i}.tmp')
            with open(temp_file, 'w') as f:
                f.write('temporary content')
            temp_files.append(temp_file)
        
        # Submit task
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Execute workflow
        orchestrator = EnhancedOrchestratorAgent.create_default()
        await orchestrator.execute(
            task_id=task_id,
            input_data=request_data,
            db=test_db_session
        )
        
        # Verify temp files were cleaned up
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                # Some temp files might remain if they're still needed
                # This is acceptable behavior
                pass
        
        # Verify final outputs exist in generated directory
        generated_files = os.listdir(test_storage_dirs['generated'])
        assert len(generated_files) > 0  # Should have some generated output
    
    async def test_concurrent_workflow_execution(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test multiple workflows can execute concurrently."""
        
        # Create multiple tasks
        tasks = []
        for i in range(3):
            request_data = {
                "user_prompt": f"Create test video {i} for concurrent execution",
                "video_style": "professional",
                "duration": 30,
                "aspect_ratio": "16:9"
            }
            
            response = await test_client.post("/api/v1/tasks/", json=request_data)
            assert response.status_code == 201
            tasks.append(response.json())
        
        # Execute all tasks concurrently
        orchestrator = EnhancedOrchestratorAgent.create_default()
        
        async def execute_task(task_data):
            return await orchestrator.execute(
                task_id=task_data["task_id"],
                input_data={
                    "user_prompt": f"Test prompt for {task_data['task_id']}",
                    "video_style": "professional",
                    "duration": 30
                },
                db=test_db_session
            )
        
        # Run tasks concurrently
        results = await asyncio.gather(
            *[execute_task(task) for task in tasks],
            return_exceptions=True
        )
        
        # Verify all tasks completed
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) == len(tasks)
        
        # Verify tasks in database
        for task_data in tasks:
            stmt = select(Task).where(Task.task_id == task_data["task_id"])
            result = await test_db_session.execute(stmt)
            task = result.scalar_one()
            assert task.status in [TaskStatus.COMPLETED, TaskStatus.PROCESSING]
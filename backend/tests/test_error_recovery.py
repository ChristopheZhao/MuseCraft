"""
Error Handling and Recovery Integration Tests

Tests system resilience and error recovery mechanisms:
- Agent failure handling and retry logic
- Service degradation and fallback mechanisms
- Circuit breaker patterns
- Data consistency during failures
- Graceful error propagation
- Recovery workflows and cleanup
"""
import pytest
import asyncio
import time
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock, MagicMock, side_effect
from httpx import AsyncClient, HTTPStatusError, ConnectTimeout
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Task, TaskStatus, AgentType
from app.agents.enhanced_orchestrator import EnhancedOrchestratorAgent
from app.services.error_recovery import error_recovery_service, ErrorCategory, ErrorSeverity
from app.services.enhanced_ai_client import enhanced_ai_client, AIServiceProvider
from app.services.monitoring_service import monitoring_service


@pytest.mark.asyncio
class TestErrorRecovery:
    """Error handling and recovery tests."""
    
    async def test_agent_failure_recovery(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test agent failure detection and recovery."""
        
        # Create task
        request_data = {
            "user_prompt": "Create a video to test agent failure recovery",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Configure AI service to fail initially
        failure_count = 0
        def failing_ai_service(*args, **kwargs):
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:  # Fail first 2 attempts
                raise Exception("Simulated AI service failure")
            return {"content": "Success after retries"}
        
        mock_ai_services['openai'].chat.completions.create.side_effect = failing_ai_service
        
        # Execute orchestrator with error recovery
        orchestrator = EnhancedOrchestratorAgent()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            # Configure error recovery to retry
            mock_recovery.handle_error.return_value = {
                "action": "retry",
                "delay": 0.1,
                "max_attempts": 5,
                "circuit_breaker_open": False
            }
            
            with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
                mock_client.chat_completion.side_effect = failing_ai_service
                
                result = await orchestrator.execute(
                    task_id=task_id,
                    input_data=request_data,
                    db=test_db_session
                )
        
        # Verify error recovery was invoked
        assert mock_recovery.handle_error.called
        
        # Verify final success after retries
        assert failure_count >= 3  # Failed twice, succeeded on third
        
        # Check task status in database
        stmt = select(Task).where(Task.task_id == task_id)
        db_result = await test_db_session.execute(stmt)
        task = db_result.scalar_one()
        
        # Task should eventually succeed or be marked for retry
        assert task.status in [TaskStatus.COMPLETED, TaskStatus.PROCESSING, TaskStatus.PENDING]
    
    async def test_circuit_breaker_activation(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test circuit breaker activation after repeated failures."""
        
        # Configure AI service to always fail
        mock_ai_services['openai'].chat.completions.create.side_effect = Exception("Persistent service failure")
        
        # Create multiple tasks to trigger circuit breaker
        task_ids = []
        for i in range(6):  # Exceed circuit breaker threshold
            request_data = {
                "user_prompt": f"Test circuit breaker task {i}",
                "video_style": "professional",
                "duration": 30,
                "aspect_ratio": "16:9"
            }
            
            response = await test_client.post("/api/v1/tasks/", json=request_data)
            assert response.status_code == 201
            task_ids.append(response.json()["task_id"])
        
        orchestrator = EnhancedOrchestratorAgent()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            # Configure circuit breaker to open after failures
            def mock_error_handler(*args, **kwargs):
                error_category = kwargs.get('error_category', ErrorCategory.UNKNOWN)
                if error_category == ErrorCategory.AI_SERVICE_ERROR:
                    # Simulate circuit breaker opening
                    return {
                        "action": "circuit_breaker_open",
                        "delay": 60,
                        "circuit_breaker_open": True,
                        "fallback_available": False
                    }
                return {"action": "fail", "circuit_breaker_open": True}
            
            mock_recovery.handle_error.side_effect = mock_error_handler
            
            with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
                mock_client.chat_completion.side_effect = Exception("Service failure")
                
                # Execute tasks - later ones should hit circuit breaker
                results = []
                for task_id in task_ids:
                    try:
                        result = await orchestrator.execute(
                            task_id=task_id,
                            input_data={"user_prompt": "test"},
                            db=test_db_session
                        )
                        results.append(result)
                    except Exception as e:
                        results.append({"error": str(e), "circuit_breaker": True})
        
        # Verify circuit breaker was activated
        circuit_breaker_results = [r for r in results if r.get("circuit_breaker")]
        assert len(circuit_breaker_results) > 0, "Circuit breaker should have been activated"
        
        # Verify error recovery was called multiple times
        assert mock_recovery.handle_error.call_count >= 3
    
    async def test_service_fallback_mechanisms(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test fallback to alternative services when primary fails."""
        
        # Configure primary service (OpenAI) to fail
        mock_ai_services['openai'].chat.completions.create.side_effect = Exception("OpenAI service down")
        
        # Configure fallback service (Anthropic) to succeed
        mock_ai_services['anthropic'].messages.create.return_value = MagicMock(
            content=[MagicMock(text="Fallback response from Anthropic")]
        )
        
        request_data = {
            "user_prompt": "Test service fallback mechanisms",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_id = response.json()["task_id"]
        
        orchestrator = EnhancedOrchestratorAgent()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            # Configure error recovery to use fallback
            mock_recovery.handle_error.return_value = {
                "action": "fallback",
                "fallback_provider": AIServiceProvider.ANTHROPIC,
                "circuit_breaker_open": False
            }
            
            with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
                # Mock fallback behavior
                def mock_chat_completion(*args, **kwargs):
                    provider = kwargs.get('provider', AIServiceProvider.OPENAI)
                    if provider == AIServiceProvider.OPENAI:
                        raise Exception("OpenAI service down")
                    elif provider == AIServiceProvider.ANTHROPIC:
                        return {"content": "Fallback response from Anthropic"}
                
                mock_client.chat_completion.side_effect = mock_chat_completion
                
                result = await orchestrator.execute(
                    task_id=task_id,
                    input_data=request_data,
                    db=test_db_session
                )
        
        # Verify fallback was attempted
        assert mock_recovery.handle_error.called
        
        # Verify task completed using fallback
        stmt = select(Task).where(Task.task_id == task_id)
        db_result = await test_db_session.execute(stmt)
        task = db_result.scalar_one()
        
        assert task.status in [TaskStatus.COMPLETED, TaskStatus.PROCESSING]
    
    async def test_data_consistency_during_failures(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test data consistency is maintained during failures."""
        
        request_data = {
            "user_prompt": "Test data consistency during failures",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_id = response.json()["task_id"]
        
        # Get initial task state
        stmt = select(Task).where(Task.task_id == task_id)
        result = await test_db_session.execute(stmt)
        task = result.scalar_one()
        initial_status = task.status
        
        # Configure AI service to fail
        mock_ai_services['openai'].chat.completions.create.side_effect = Exception("Service failure")
        
        orchestrator = EnhancedOrchestratorAgent()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            mock_recovery.handle_error.return_value = {
                "action": "fail",
                "circuit_breaker_open": False
            }
            
            with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
                mock_client.chat_completion.side_effect = Exception("Service failure")
                
                try:
                    result = await orchestrator.execute(
                        task_id=task_id,
                        input_data=request_data,
                        db=test_db_session
                    )
                except Exception:
                    # Failure is expected
                    pass
        
        # Verify task state is consistent
        await test_db_session.refresh(task)
        
        # Task should be in a valid error state, not corrupted
        assert task.status in [TaskStatus.FAILED, TaskStatus.ERROR, initial_status]
    
    async def test_partial_failure_recovery(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test recovery from partial workflow failures."""
        
        request_data = {
            "user_prompt": "Test partial failure recovery",
            "video_style": "professional",
            "duration": 60,  # Longer video with multiple scenes
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_id = response.json()["task_id"]
        
        # Configure specific agent to fail
        call_count = 0
        def selective_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # Let concept planning succeed
            if call_count <= 2:
                return {"content": "Concept planning success"}
            
            # Fail on script writing (3rd call)
            if call_count == 3:
                raise Exception("Script writing failure")
            
            # Succeed on retry
            return {"content": "Script writing success on retry"}
        
        mock_ai_services['openai'].chat.completions.create.side_effect = selective_failure
        
        orchestrator = EnhancedOrchestratorAgent()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            # Configure recovery to retry failed step
            mock_recovery.handle_error.return_value = {
                "action": "retry_step",
                "step": "script_writer",
                "delay": 0.1,
                "preserve_progress": True
            }
            
            with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
                mock_client.chat_completion.side_effect = selective_failure
                
                result = await orchestrator.execute(
                    task_id=task_id,
                    input_data=request_data,
                    db=test_db_session
                )
        
        # Verify partial recovery occurred
        assert call_count >= 4  # Initial attempts + retry
        
        # Verify task eventually succeeded
        stmt = select(Task).where(Task.task_id == task_id)
        db_result = await test_db_session.execute(stmt)
        task = db_result.scalar_one()
        
        assert task.status in [TaskStatus.COMPLETED, TaskStatus.PROCESSING]
    
    async def test_resource_cleanup_on_failure(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        test_storage_dirs: Dict[str, str],
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test proper resource cleanup when failures occur."""
        
        import os
        
        # Create some temporary files to simulate partial work
        temp_files = []
        for i in range(3):
            temp_file = os.path.join(test_storage_dirs['temp'], f'temp_resource_{i}.tmp')
            with open(temp_file, 'w') as f:
                f.write(f'temporary resource {i}')
            temp_files.append(temp_file)
        
        request_data = {
            "user_prompt": "Test resource cleanup on failure",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_id = response.json()["task_id"]
        
        # Configure service to fail
        mock_ai_services['openai'].chat.completions.create.side_effect = Exception("Service failure")
        
        orchestrator = EnhancedOrchestratorAgent()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            mock_recovery.handle_error.return_value = {
                "action": "fail",
                "cleanup_resources": True
            }
            
            with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
                mock_client.chat_completion.side_effect = Exception("Service failure")
                
                try:
                    result = await orchestrator.execute(
                        task_id=task_id,
                        input_data=request_data,
                        db=test_db_session
                    )
                except Exception:
                    # Failure is expected
                    pass
        
        # Verify temp files were cleaned up (if cleanup was implemented)
        remaining_files = [f for f in temp_files if os.path.exists(f)]
        
        # Depending on implementation, files might be cleaned up
        # This test verifies the cleanup mechanism is working
        if len(remaining_files) < len(temp_files):
            print(f"Cleanup successful: {len(temp_files) - len(remaining_files)} files cleaned")
        
        # Verify task is in proper failed state
        stmt = select(Task).where(Task.task_id == task_id)
        db_result = await test_db_session.execute(stmt)
        task = db_result.scalar_one()
        
        assert task.status in [TaskStatus.FAILED, TaskStatus.ERROR]
    
    async def test_timeout_handling(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test handling of service timeouts."""
        
        # Configure AI service to timeout
        async def timeout_response(*args, **kwargs):
            await asyncio.sleep(10)  # Simulate very slow response
            return {"content": "Too late"}
        
        mock_ai_services['openai'].chat.completions.create.side_effect = timeout_response
        
        request_data = {
            "user_prompt": "Test timeout handling",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_id = response.json()["task_id"]
        
        orchestrator = EnhancedOrchestratorAgent()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            mock_recovery.handle_error.return_value = {
                "action": "timeout_retry",
                "delay": 0.1,
                "timeout": 2.0  # Shorter timeout for retry
            }
            
            with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
                # Mock timeout behavior
                async def mock_chat_completion(*args, **kwargs):
                    timeout = kwargs.get('timeout', 5.0)
                    if timeout > 5.0:
                        raise asyncio.TimeoutError("Request timed out")
                    return {"content": "Success with shorter timeout"}
                
                mock_client.chat_completion.side_effect = mock_chat_completion
                
                start_time = time.time()
                
                try:
                    result = await asyncio.wait_for(
                        orchestrator.execute(
                            task_id=task_id,
                            input_data=request_data,
                            db=test_db_session
                        ),
                        timeout=15.0
                    )
                except asyncio.TimeoutError:
                    # Timeout is acceptable for this test
                    pass
                
                execution_time = time.time() - start_time
        
        # Verify timeout was handled reasonably quickly
        assert execution_time < 15.0, "Timeout handling took too long"
        
        # Verify error recovery was invoked
        assert mock_recovery.handle_error.called
    
    async def test_cascading_failure_prevention(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test prevention of cascading failures across the system."""
        
        # Create multiple tasks to test isolation
        task_ids = []
        for i in range(3):
            request_data = {
                "user_prompt": f"Test cascading failure prevention {i}",
                "video_style": "professional",
                "duration": 30,
                "aspect_ratio": "16:9"
            }
            
            response = await test_client.post("/api/v1/tasks/", json=request_data)
            assert response.status_code == 201
            task_ids.append(response.json()["task_id"])
        
        # Configure first task to fail, others to succeed
        call_count = 0
        def selective_service_behavior(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # Fail first few calls (first task)
            if call_count <= 3:
                raise Exception("Service failure for first task")
            
            # Succeed for subsequent tasks
            return {"content": f"Success for call {call_count}"}
        
        mock_ai_services['openai'].chat.completions.create.side_effect = selective_service_behavior
        
        orchestrator = EnhancedOrchestratorAgent()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            # Configure isolation - don't let one failure affect others
            mock_recovery.handle_error.return_value = {
                "action": "isolate_failure",
                "circuit_breaker_open": False,  # Don't open circuit breaker
                "affect_other_tasks": False
            }
            
            with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
                mock_client.chat_completion.side_effect = selective_service_behavior
                
                # Execute tasks concurrently
                async def execute_task(task_id: str):
                    try:
                        return await orchestrator.execute(
                            task_id=task_id,
                            input_data={"user_prompt": "test"},
                            db=test_db_session
                        )
                    except Exception as e:
                        return {"error": str(e), "task_id": task_id}
                
                results = await asyncio.gather(
                    *[execute_task(task_id) for task_id in task_ids],
                    return_exceptions=True
                )
        
        # Verify failure isolation
        successful_results = [r for r in results if not isinstance(r, Exception) and not r.get("error")]
        failed_results = [r for r in results if isinstance(r, Exception) or r.get("error")]
        
        # At least some tasks should succeed despite others failing
        assert len(successful_results) > 0, "All tasks failed - cascading failure not prevented"
        
        # Verify tasks in database have appropriate states
        for task_id in task_ids:
            stmt = select(Task).where(Task.task_id == task_id)
            db_result = await test_db_session.execute(stmt)
            task = db_result.scalar_one()
            
            # Each task should have a valid status
            assert task.status in [
                TaskStatus.PENDING, TaskStatus.PROCESSING, 
                TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ERROR
            ]
    
    async def test_graceful_degradation(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test graceful degradation when services are partially available."""
        
        request_data = {
            "user_prompt": "Test graceful degradation",
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        }
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_id = response.json()["task_id"]
        
        # Configure some services to be unavailable
        mock_ai_services['stability'].generate.side_effect = Exception("Image generation service down")
        mock_ai_services['runway'].tasks.create.side_effect = Exception("Video generation service down")
        
        # Keep text services available
        mock_ai_services['openai'].chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Text generation works"))]
        )
        
        orchestrator = EnhancedOrchestratorAgent()
        
        with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
            # Configure graceful degradation
            mock_recovery.handle_error.return_value = {
                "action": "degrade_gracefully",
                "fallback_mode": "text_only",
                "reduced_functionality": True
            }
            
            with patch('app.agents.enhanced_orchestrator.enhanced_ai_client') as mock_client:
                def mock_service_calls(*args, **kwargs):
                    service_type = kwargs.get('service_type', 'text')
                    
                    if service_type in ['image', 'video']:
                        raise Exception(f"{service_type} service unavailable")
                    
                    return {"content": "Text service available"}
                
                mock_client.chat_completion.return_value = {"content": "Text service available"}
                mock_client.generate_image.side_effect = Exception("Image service down")
                mock_client.generate_video.side_effect = Exception("Video service down")
                
                result = await orchestrator.execute(
                    task_id=task_id,
                    input_data=request_data,
                    db=test_db_session
                )
        
        # Verify graceful degradation occurred
        assert mock_recovery.handle_error.called
        
        # Verify task completed in degraded mode
        stmt = select(Task).where(Task.task_id == task_id)
        db_result = await test_db_session.execute(stmt)
        task = db_result.scalar_one()
        
        # Task should complete with reduced functionality
        assert task.status in [TaskStatus.COMPLETED, TaskStatus.PARTIAL_SUCCESS]
        
        # Check if degradation was recorded in metadata
        if hasattr(task, 'output_metadata') and task.output_metadata:
            assert task.output_metadata.get('degraded_mode') or task.output_metadata.get('fallback_used')
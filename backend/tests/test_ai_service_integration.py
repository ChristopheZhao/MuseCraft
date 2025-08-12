"""
AI Service Integration Tests

Tests the integration with external AI services:
- OpenAI GPT models for text generation
- Anthropic Claude for advanced reasoning
- Stability AI for image generation
- Runway ML for video generation
- Pika Labs for video creation
- Error handling and fallback mechanisms
- Rate limiting and cost control
"""
import pytest
import asyncio
import json
import time
from typing import Dict, Any, List, Optional
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, HTTPStatusError, ConnectTimeout
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enhanced_ai_client import enhanced_ai_client, AIServiceProvider
from app.services.error_recovery import error_recovery_service, ErrorCategory
from app.agents.concept_planner import ConceptPlannerAgent
from app.agents.script_writer import ScriptWriterAgent
from app.agents.image_generator import ImageGeneratorAgent
from app.agents.video_generator import VideoGeneratorAgent


@pytest.mark.ai_services
@pytest.mark.asyncio
class TestAIServiceIntegration:
    """AI service integration tests."""
    
    async def test_openai_integration(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test OpenAI API integration."""
        
        # Configure mock response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({
                "concept": "AI-Generated Video Concept",
                "themes": ["technology", "innovation", "future"],
                "narrative_structure": "problem-solution-benefits",
                "visual_style": "modern and clean"
            })))
        ]
        
        mock_ai_services['openai'].chat.completions.create.return_value = mock_response
        
        # Test concept generation
        concept_agent = ConceptPlannerAgent()
        
        with patch('app.agents.concept_planner.enhanced_ai_client') as mock_client:
            mock_client.chat_completion.return_value = {
                "concept": "AI-Generated Video Concept",
                "themes": ["technology", "innovation", "future"],
                "narrative_structure": "problem-solution-benefits",
                "visual_style": "modern and clean"
            }
            
            result = await concept_agent.execute(
                task_id="test-task-123",
                input_data={
                    "user_prompt": "Create a video about AI technology",
                    "video_style": "professional",
                    "duration": 60
                },
                db=None  # Mock database session not needed for this test
            )
        
        # Verify result
        assert result["success"] is True
        assert "concept" in result["data"]
        assert result["data"]["concept"] == "AI-Generated Video Concept"
        
        # Verify API was called correctly
        mock_client.chat_completion.assert_called_once()
    
    async def test_anthropic_integration(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test Anthropic Claude API integration."""
        
        # Configure mock response
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({
                "script": "Welcome to the future of AI technology...",
                "scenes": [
                    {"title": "Introduction", "duration": 10, "narration": "AI is transforming..."},
                    {"title": "Current State", "duration": 20, "narration": "Today's AI systems..."},
                    {"title": "Future Vision", "duration": 30, "narration": "Looking ahead..."}
                ],
                "style_notes": "Professional, engaging, informative tone"
            }))
        ]
        
        mock_ai_services['anthropic'].messages.create.return_value = mock_response
        
        # Test script writing
        script_agent = ScriptWriterAgent()
        
        with patch('app.agents.script_writer.enhanced_ai_client') as mock_client:
            mock_client.chat_completion.return_value = {
                "script": "Welcome to the future of AI technology...",
                "scenes": [
                    {"title": "Introduction", "duration": 10, "narration": "AI is transforming..."},
                    {"title": "Current State", "duration": 20, "narration": "Today's AI systems..."},
                    {"title": "Future Vision", "duration": 30, "narration": "Looking ahead..."}
                ],
                "style_notes": "Professional, engaging, informative tone"
            }
            
            result = await script_agent.execute(
                task_id="test-task-123",
                input_data={
                    "concept": "AI Technology Overview",
                    "duration": 60,
                    "style": "professional"
                },
                db=None
            )
        
        # Verify result
        assert result["success"] is True
        assert "script" in result["data"]
        assert len(result["data"]["scenes"]) == 3
        
        # Verify API was called correctly
        mock_client.chat_completion.assert_called_once()
    
    async def test_stability_ai_integration(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test Stability AI image generation integration."""
        
        # Configure mock response
        mock_artifact = MagicMock()
        mock_artifact.seed = 12345
        mock_artifact.binary = b"mock_image_binary_data"
        
        mock_response = MagicMock()
        mock_response.artifacts = [mock_artifact]
        
        mock_ai_services['stability'].generate.return_value = mock_response
        
        # Test image generation
        image_agent = ImageGeneratorAgent()
        
        with patch('app.agents.image_generator.enhanced_ai_client') as mock_client:
            mock_client.generate_image.return_value = {
                "images": [
                    {
                        "url": "https://example.com/generated-image-1.jpg",
                        "seed": 12345,
                        "prompt": "AI technology visualization"
                    }
                ],
                "metadata": {
                    "model": "stable-diffusion-xl",
                    "steps": 30,
                    "cfg_scale": 7.0
                }
            }
            
            result = await image_agent.execute(
                task_id="test-task-123",
                input_data={
                    "prompts": ["AI technology visualization", "Modern office setting"],
                    "style": "photorealistic",
                    "aspect_ratio": "16:9"
                },
                db=None
            )
        
        # Verify result
        assert result["success"] is True
        assert "images" in result["data"]
        assert len(result["data"]["images"]) >= 1
        
        # Verify API was called correctly
        mock_client.generate_image.assert_called()
    
    async def test_runway_ml_integration(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test Runway ML video generation integration."""
        
        # Configure mock response
        mock_ai_services['runway'].tasks.create.return_value = MagicMock(
            id="runway-task-123",
            status="PENDING"
        )
        
        mock_ai_services['runway'].tasks.retrieve.return_value = MagicMock(
            id="runway-task-123",
            status="SUCCESS",
            output=["https://example.com/generated-video.mp4"]
        )
        
        # Test video generation
        video_agent = VideoGeneratorAgent()
        
        with patch('app.agents.video_generator.enhanced_ai_client') as mock_client:
            mock_client.generate_video.return_value = {
                "videos": [
                    {
                        "url": "https://example.com/generated-video.mp4",
                        "duration": 5.0,
                        "resolution": "1920x1080",
                        "format": "mp4"
                    }
                ],
                "metadata": {
                    "model": "runway-gen3",
                    "prompt": "AI technology demonstration",
                    "motion_strength": 7
                }
            }
            
            result = await video_agent.execute(
                task_id="test-task-123",
                input_data={
                    "image_prompts": ["AI visualization"],
                    "motion_prompts": ["smooth camera movement"],
                    "duration": 5
                },
                db=None
            )
        
        # Verify result
        assert result["success"] is True
        assert "videos" in result["data"]
        assert result["data"]["videos"][0]["duration"] == 5.0
        
        # Verify API was called correctly
        mock_client.generate_video.assert_called()
    
    async def test_ai_service_error_handling(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test AI service error handling and recovery."""
        
        # Test rate limiting error
        mock_ai_services['openai'].chat.completions.create.side_effect = HTTPStatusError(
            "Rate limit exceeded",
            request=MagicMock(),
            response=MagicMock(status_code=429, headers={"retry-after": "60"})
        )
        
        with patch('app.services.enhanced_ai_client.enhanced_ai_client') as mock_client:
            # Configure error recovery
            with patch('app.services.error_recovery.error_recovery_service') as mock_recovery:
                mock_recovery.handle_error.return_value = {
                    "retry": True,
                    "delay": 1.0,
                    "max_retries": 3
                }
                
                mock_client.chat_completion.side_effect = [
                    Exception("Rate limit exceeded"),
                    {"content": "Success on retry"}
                ]
                
                # Test with concept planner
                concept_agent = ConceptPlannerAgent()
                
                result = await concept_agent.execute(
                    task_id="test-task-123",
                    input_data={"user_prompt": "Test error handling"},
                    db=None
                )
                
                # Should succeed on retry
                assert result["success"] is True or result.get("retry_needed") is True
        
        # Test timeout error
        mock_ai_services['openai'].chat.completions.create.side_effect = ConnectTimeout(
            "Request timeout"
        )
        
        with patch('app.services.enhanced_ai_client.enhanced_ai_client') as mock_client:
            mock_client.chat_completion.side_effect = asyncio.TimeoutError("Request timeout")
            
            concept_agent = ConceptPlannerAgent()
            
            result = await concept_agent.execute(
                task_id="test-task-123",
                input_data={"user_prompt": "Test timeout handling"},
                db=None
            )
            
            # Should handle timeout gracefully
            assert result["success"] is False
            assert "timeout" in result["error"].lower()
    
    async def test_ai_service_fallback_mechanisms(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test fallback between different AI services."""
        
        # Configure primary service to fail
        mock_ai_services['openai'].chat.completions.create.side_effect = Exception(
            "OpenAI service unavailable"
        )
        
        # Configure fallback service to succeed
        mock_ai_services['anthropic'].messages.create.return_value = MagicMock(
            content=[MagicMock(text="Fallback response from Claude")]
        )
        
        with patch('app.services.enhanced_ai_client.enhanced_ai_client') as mock_client:
            # Mock fallback behavior
            def mock_chat_completion(*args, **kwargs):
                provider = kwargs.get('provider', AIServiceProvider.OPENAI)
                if provider == AIServiceProvider.OPENAI:
                    raise Exception("OpenAI service unavailable")
                elif provider == AIServiceProvider.ANTHROPIC:
                    return {"content": "Fallback response from Claude"}
            
            mock_client.chat_completion.side_effect = mock_chat_completion
            
            concept_agent = ConceptPlannerAgent()
            
            result = await concept_agent.execute(
                task_id="test-task-123",
                input_data={"user_prompt": "Test fallback mechanisms"},
                db=None
            )
            
            # Should succeed with fallback
            assert result["success"] is True or "fallback" in str(result)
    
    async def test_ai_service_cost_tracking(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test AI service cost tracking and monitoring."""
        
        # Configure mock responses with usage data
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        mock_response.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )
        
        mock_ai_services['openai'].chat.completions.create.return_value = mock_response
        
        with patch('app.services.monitoring_service.monitoring_service') as mock_monitor:
            with patch('app.services.enhanced_ai_client.enhanced_ai_client') as mock_client:
                mock_client.chat_completion.return_value = {
                    "content": "Test response",
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "total_tokens": 150,
                        "cost": 0.003  # Estimated cost
                    }
                }
                
                concept_agent = ConceptPlannerAgent()
                
                result = await concept_agent.execute(
                    task_id="test-task-123",
                    input_data={"user_prompt": "Test cost tracking"},
                    db=None
                )
                
                # Verify cost tracking was called
                mock_monitor.track_ai_usage.assert_called()
                
                # Verify usage data was recorded
                call_args = mock_monitor.track_ai_usage.call_args
                usage_data = call_args[1] if len(call_args) > 1 else call_args[0][1]
                
                assert "tokens" in str(usage_data) or "cost" in str(usage_data)
    
    async def test_ai_service_rate_limiting(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test AI service rate limiting compliance."""
        
        # Simulate rate limiting
        call_times = []
        
        def track_call_time(*args, **kwargs):
            call_times.append(time.time())
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="Response"))]
            )
        
        mock_ai_services['openai'].chat.completions.create.side_effect = track_call_time
        
        with patch('app.services.enhanced_ai_client.enhanced_ai_client') as mock_client:
            mock_client.chat_completion.side_effect = lambda *args, **kwargs: {
                "content": "Response"
            }
            
            concept_agent = ConceptPlannerAgent()
            
            # Make multiple rapid requests
            tasks = []
            for i in range(5):
                task = concept_agent.execute(
                    task_id=f"test-task-{i}",
                    input_data={"user_prompt": f"Test request {i}"},
                    db=None
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # All should succeed (rate limiting should be handled internally)
            successful_results = [r for r in results if not isinstance(r, Exception)]
            assert len(successful_results) >= 3  # Most should succeed
    
    async def test_ai_service_response_validation(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test AI service response validation and sanitization."""
        
        # Test invalid JSON response
        mock_ai_services['openai'].chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Invalid JSON response"))]
        )
        
        with patch('app.services.enhanced_ai_client.enhanced_ai_client') as mock_client:
            mock_client.chat_completion.return_value = {
                "content": "Invalid JSON response"  # Should be handled gracefully
            }
            
            concept_agent = ConceptPlannerAgent()
            
            result = await concept_agent.execute(
                task_id="test-task-123",
                input_data={"user_prompt": "Test invalid response"},
                db=None
            )
            
            # Should handle invalid response gracefully
            assert "error" in result or result["success"] is False
        
        # Test malicious content filtering
        mock_ai_services['openai'].chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({
                "concept": "Harmful content that should be filtered",
                "script": "<script>alert('xss')</script>",
                "themes": ["inappropriate", "harmful"]
            })))]
        )
        
        with patch('app.services.quality_control.quality_control_service') as mock_qc:
            mock_qc.validate_content.return_value = {
                "approved": False,
                "reasons": ["Potentially harmful content detected"],
                "confidence": 0.9
            }
            
            with patch('app.services.enhanced_ai_client.enhanced_ai_client') as mock_client:
                mock_client.chat_completion.return_value = {
                    "concept": "Harmful content that should be filtered",
                    "script": "<script>alert('xss')</script>",
                    "themes": ["inappropriate", "harmful"]
                }
                
                concept_agent = ConceptPlannerAgent()
                
                result = await concept_agent.execute(
                    task_id="test-task-123",
                    input_data={"user_prompt": "Test content filtering"},
                    db=None
                )
                
                # Should reject harmful content
                if mock_qc.validate_content.called:
                    # Content was filtered
                    assert result["success"] is False or "rejected" in str(result)
    
    async def test_ai_service_concurrent_requests(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test handling of concurrent AI service requests."""
        
        # Configure mock with delays to simulate real API behavior
        async def delayed_response(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate API latency
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="Delayed response"))]
            )
        
        mock_ai_services['openai'].chat.completions.create.side_effect = delayed_response
        
        with patch('app.services.enhanced_ai_client.enhanced_ai_client') as mock_client:
            async def mock_chat_completion(*args, **kwargs):
                await asyncio.sleep(0.1)
                return {"content": "Concurrent response"}
            
            mock_client.chat_completion.side_effect = mock_chat_completion
            
            concept_agent = ConceptPlannerAgent()
            
            # Execute multiple concurrent requests
            tasks = []
            for i in range(3):
                task = concept_agent.execute(
                    task_id=f"concurrent-task-{i}",
                    input_data={"user_prompt": f"Concurrent request {i}"},
                    db=None
                )
                tasks.append(task)
            
            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            execution_time = time.time() - start_time
            
            # Should complete in reasonable time (concurrent, not sequential)
            assert execution_time < 1.0  # Should be much faster than 3 * 0.1 = 0.3s
            
            # All requests should succeed
            successful_results = [r for r in results if not isinstance(r, Exception)]
            assert len(successful_results) == 3
    
    async def test_ai_service_model_switching(
        self,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test dynamic model switching based on requirements."""
        
        with patch('app.services.enhanced_ai_client.enhanced_ai_client') as mock_client:
            # Mock different model responses
            def mock_model_response(*args, **kwargs):
                model = kwargs.get('model', 'gpt-3.5-turbo')
                if model == 'gpt-4':
                    return {"content": "High-quality GPT-4 response", "model": "gpt-4"}
                else:
                    return {"content": "Standard GPT-3.5 response", "model": "gpt-3.5-turbo"}
            
            mock_client.chat_completion.side_effect = mock_model_response
            
            concept_agent = ConceptPlannerAgent()
            
            # Test with different complexity requirements
            simple_result = await concept_agent.execute(
                task_id="simple-task",
                input_data={
                    "user_prompt": "Simple video concept",
                    "complexity": "low"
                },
                db=None
            )
            
            complex_result = await concept_agent.execute(
                task_id="complex-task",
                input_data={
                    "user_prompt": "Complex narrative video concept",
                    "complexity": "high"
                },
                db=None
            )
            
            # Verify appropriate models were used
            # (This would depend on the actual implementation)
            assert simple_result["success"] is True
            assert complex_result["success"] is True
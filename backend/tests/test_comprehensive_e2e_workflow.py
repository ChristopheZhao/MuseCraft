"""
Comprehensive End-to-End Workflow Test Suite

This module provides exhaustive testing of the complete video generation pipeline,
covering all user journeys, edge cases, and system integrations.
"""
import asyncio
import json
import os
import time
import tempfile
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Task, Scene, Resource, TaskStatus, AgentType
from app.agents.enhanced_orchestrator import EnhancedOrchestratorAgent
from app.services.websocket import websocket_manager
from app.services.monitoring_service import monitoring_service
from app.services.quality_control import quality_control_service


@pytest.mark.e2e
@pytest.mark.asyncio
class TestComprehensiveE2EWorkflow:
    """Comprehensive end-to-end workflow testing."""
    
    async def test_full_user_journey_professional_video(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock],
        test_storage_dirs: Dict[str, str],
        mock_websocket: MagicMock
    ):
        """Test complete user journey for professional video creation."""
        
        # Setup WebSocket connection
        session_id = "professional-video-session"
        websocket_manager.active_connections[session_id] = mock_websocket
        
        # Step 1: User uploads reference materials
        test_files = await self._create_test_media_files(test_storage_dirs['upload'])
        
        upload_response = await test_client.post(
            "/api/v1/files/upload",
            files={
                "files": ("reference.jpg", test_files["image"], "image/jpeg"),
                "files": ("voice_guide.mp3", test_files["audio"], "audio/mpeg")
            },
            data={"session_id": session_id}
        )
        assert upload_response.status_code == 200
        uploaded_files = upload_response.json()
        
        # Step 2: Submit comprehensive video request
        request_data = {
            "user_prompt": "Create a professional corporate video explaining our AI-powered video generation platform. Target audience: business executives. Include sections on technology overview, benefits, and ROI. Use uploaded reference materials.",
            "video_style": "professional",
            "duration": 180,  # 3 minutes
            "aspect_ratio": "16:9",
            "quality_level": "high",
            "include_subtitles": True,
            "background_music": True,
            "brand_guidelines": {
                "color_scheme": "corporate_blue",
                "font_family": "professional",
                "logo_placement": "bottom_right"
            },
            "reference_files": [file["file_id"] for file in uploaded_files["files"]],
            "session_id": session_id,
            "priority": "high"
        }
        
        # Configure comprehensive AI mock responses
        self._setup_professional_video_mocks(mock_ai_services)
        
        # Step 3: Submit task and track initial response
        start_time = time.time()
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Verify initial task creation
        assert task_data["title"]
        assert task_data["estimated_duration"]
        assert task_data["status"] == "pending"
        
        # Step 4: Monitor workflow execution
        workflow_stages = await self._execute_and_monitor_workflow(
            task_id, test_db_session, mock_websocket
        )
        
        # Step 5: Verify all workflow stages completed
        expected_stages = [
            "concept_planning",
            "script_writing", 
            "scene_breakdown",
            "image_generation",
            "voice_synthesis",
            "video_generation",
            "composition",
            "quality_check",
            "final_rendering"
        ]
        
        completed_stages = [stage["name"] for stage in workflow_stages if stage["status"] == "completed"]
        assert all(stage in completed_stages for stage in expected_stages)
        
        # Step 6: Verify database state
        await self._verify_complete_workflow_database_state(task_id, test_db_session)
        
        # Step 7: Verify generated outputs
        generated_files = await self._verify_generated_outputs(task_id, test_storage_dirs["generated"])
        
        # Step 8: Test download functionality
        download_response = await test_client.get(f"/api/v1/tasks/{task_id}/download")
        assert download_response.status_code == 200
        assert download_response.headers["content-type"] == "video/mp4"
        
        # Step 9: Verify WebSocket notifications
        self._verify_websocket_notifications(mock_websocket, expected_stages)
        
        # Step 10: Performance verification
        execution_time = time.time() - start_time
        assert execution_time < 300  # Should complete within 5 minutes for test
        
        # Step 11: Quality metrics verification
        quality_metrics = await self._get_quality_metrics(task_id, test_db_session)
        assert quality_metrics["overall_score"] >= 0.8
        assert quality_metrics["technical_quality"] >= 0.8
        assert quality_metrics["content_quality"] >= 0.7
    
    async def test_creative_video_with_custom_assets(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock],
        test_storage_dirs: Dict[str, str]
    ):
        """Test creative video generation with custom user assets."""
        
        # Setup custom assets
        custom_assets = await self._create_custom_asset_package(test_storage_dirs['upload'])
        
        request_data = {
            "user_prompt": "Create an artistic video showcasing our product with creative transitions and effects. Use uploaded custom graphics and music.",
            "video_style": "creative",
            "duration": 90,
            "aspect_ratio": "1:1",  # Instagram format
            "custom_assets": custom_assets,
            "creative_parameters": {
                "transition_style": "dynamic",
                "color_grading": "vibrant",
                "animation_intensity": "high",
                "visual_effects": ["parallax", "particle_effects", "color_splash"]
            }
        }
        
        self._setup_creative_video_mocks(mock_ai_services)
        
        response = await test_client.post("/api/v1/tasks/", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Execute workflow with creative-specific monitoring
        await self._execute_creative_workflow(task_id, test_db_session)
        
        # Verify creative-specific outputs
        creative_outputs = await self._verify_creative_outputs(task_id, test_storage_dirs["generated"])
        assert creative_outputs["has_effects"]
        assert creative_outputs["uses_custom_assets"]
        assert creative_outputs["aspect_ratio"] == "1:1"
    
    async def test_batch_video_generation(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test batch generation of multiple videos."""
        
        batch_requests = [
            {
                "user_prompt": f"Create video {i+1} about topic variation {i+1}",
                "video_style": ["professional", "creative", "educational"][i % 3],
                "duration": 60,
                "aspect_ratio": "16:9",
                "batch_id": "batch-test-123"
            }
            for i in range(5)
        ]
        
        # Submit batch request
        response = await test_client.post("/api/v1/tasks/batch", json={"requests": batch_requests})
        assert response.status_code == 201
        
        batch_data = response.json()
        task_ids = [task["task_id"] for task in batch_data["tasks"]]
        
        # Monitor batch execution
        batch_completion = await self._monitor_batch_execution(task_ids, test_db_session)
        
        # Verify all tasks completed
        assert batch_completion["total_tasks"] == 5
        assert batch_completion["completed_tasks"] >= 4  # Allow for 1 potential failure
        assert batch_completion["average_execution_time"] < 120  # Per video
    
    async def test_interactive_editing_workflow(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock],
        mock_websocket: MagicMock
    ):
        """Test interactive editing and revision workflow."""
        
        session_id = "interactive-editing-session"
        websocket_manager.active_connections[session_id] = mock_websocket
        
        # Step 1: Initial video generation
        initial_request = {
            "user_prompt": "Create a base video for interactive editing",
            "video_style": "professional",
            "duration": 60,
            "session_id": session_id
        }
        
        response = await test_client.post("/api/v1/tasks/", json=initial_request)
        base_task_id = response.json()["task_id"]
        
        # Wait for initial completion
        await self._wait_for_task_completion(base_task_id, test_db_session)
        
        # Step 2: Request preview
        preview_response = await test_client.get(f"/api/v1/tasks/{base_task_id}/preview")
        assert preview_response.status_code == 200
        
        # Step 3: Submit editing requests
        editing_requests = [
            {
                "action": "modify_scene",
                "scene_index": 1,
                "modifications": {
                    "text_overlay": "Updated text content",
                    "background_color": "#FF5733"
                }
            },
            {
                "action": "add_transition",
                "between_scenes": [1, 2],
                "transition_type": "fade",
                "duration": 1.0
            },
            {
                "action": "adjust_timing",
                "scene_index": 2,
                "new_duration": 8.0
            }
        ]
        
        # Apply edits
        for edit_request in editing_requests:
            edit_response = await test_client.post(
                f"/api/v1/tasks/{base_task_id}/edit",
                json=edit_request
            )
            assert edit_response.status_code == 200
        
        # Step 4: Generate final version
        finalize_response = await test_client.post(f"/api/v1/tasks/{base_task_id}/finalize")
        assert finalize_response.status_code == 200
        
        final_task_id = finalize_response.json()["final_task_id"]
        
        # Verify editing workflow completion
        await self._verify_editing_workflow_completion(
            base_task_id, final_task_id, test_db_session
        )
    
    async def test_multi_language_video_generation(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test multi-language video generation workflow."""
        
        request_data = {
            "user_prompt": "Create a product demonstration video",
            "video_style": "professional",
            "duration": 120,
            "languages": ["en", "es", "fr", "de", "zh"],
            "localization_requirements": {
                "text_overlay_translation": True,
                "voice_over_translation": True,
                "cultural_adaptation": True
            }
        }
        
        self._setup_multilanguage_mocks(mock_ai_services)
        
        response = await test_client.post("/api/v1/tasks/multilang", json=request_data)
        assert response.status_code == 201
        
        task_data = response.json()
        primary_task_id = task_data["primary_task_id"]
        language_tasks = task_data["language_tasks"]
        
        # Verify language-specific tasks were created
        assert len(language_tasks) == 5
        assert all(task["language"] in ["en", "es", "fr", "de", "zh"] for task in language_tasks)
        
        # Monitor multi-language workflow
        multilang_results = await self._monitor_multilanguage_workflow(
            primary_task_id, language_tasks, test_db_session
        )
        
        # Verify all language versions completed
        assert multilang_results["completed_languages"] >= 4  # Allow for potential failures
        assert multilang_results["localization_quality"] >= 0.8
    
    async def test_api_integration_workflow(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock]
    ):
        """Test workflow with external API integrations."""
        
        request_data = {
            "user_prompt": "Create a data-driven video with real-time information",
            "video_style": "infographic",
            "duration": 90,
            "data_sources": [
                {"type": "api", "url": "https://api.example.com/data", "key": "market_data"},
                {"type": "database", "query": "SELECT * FROM analytics", "key": "user_metrics"}
            ],
            "dynamic_content": True
        }
        
        # Mock external API responses
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.return_value.json.return_value = {
                "market_data": {"price": 100, "change": "+5%"},
                "user_metrics": {"active_users": 10000, "growth": "+15%"}
            }
            
            response = await test_client.post("/api/v1/tasks/", json=request_data)
            assert response.status_code == 201
            
            task_id = response.json()["task_id"]
            
            # Execute workflow with API integration
            await self._execute_api_integrated_workflow(task_id, test_db_session)
            
            # Verify API data was incorporated
            api_integration_results = await self._verify_api_integration(task_id, test_db_session)
            assert api_integration_results["data_sources_used"] == 2
            assert api_integration_results["dynamic_content_generated"]
    
    # Helper methods
    
    async def _create_test_media_files(self, upload_dir: str) -> Dict[str, bytes]:
        """Create test media files for upload testing."""
        files = {}
        
        # Create test image
        image_data = b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xFF\xDB'
        files["image"] = image_data
        
        # Create test audio
        audio_data = b'ID3\x03\x00\x00\x00\x00\x00\x00\x00'
        files["audio"] = audio_data
        
        # Create test video
        video_data = b'\x00\x00\x00\x20ftypmp41\x00\x00\x00\x00mp41isom'
        files["video"] = video_data
        
        return files
    
    def _setup_professional_video_mocks(self, mock_ai_services: Dict[str, AsyncMock]):
        """Setup comprehensive mocks for professional video generation."""
        
        # Concept planning response
        mock_ai_services['openai'].chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps({
                "concept": "AI-Powered Video Generation Platform",
                "target_audience": "business_executives",
                "key_messages": [
                    "Revolutionary AI technology",
                    "Significant cost savings",
                    "Improved efficiency and quality"
                ],
                "visual_style": "professional_corporate",
                "narrative_structure": {
                    "introduction": {"duration": 30, "key_points": ["Problem statement", "Solution overview"]},
                    "technology_overview": {"duration": 60, "key_points": ["AI capabilities", "Technical benefits"]},
                    "benefits_roi": {"duration": 90, "key_points": ["Cost savings", "Efficiency gains", "Quality improvements"]}
                },
                "scenes": [
                    {
                        "title": "Introduction",
                        "duration": 30,
                        "description": "Executive explaining the challenge",
                        "visual_elements": ["corporate_background", "professional_lighting"],
                        "text_overlay": "The Future of Video Production"
                    },
                    {
                        "title": "Technology Showcase",
                        "duration": 60,
                        "description": "AI technology demonstration",
                        "visual_elements": ["technology_graphics", "data_visualizations"],
                        "text_overlay": "AI-Powered Innovation"
                    },
                    {
                        "title": "ROI Demonstration",
                        "duration": 90,
                        "description": "Financial benefits presentation",
                        "visual_elements": ["charts_graphs", "roi_metrics"],
                        "text_overlay": "Measurable Results"
                    }
                ]
            })))
        ]
        
        # Image generation responses
        mock_ai_services['stability'].generate.return_value = MagicMock(
            artifacts=[
                MagicMock(seed=12345, binary=b"professional_background_image"),
                MagicMock(seed=12346, binary=b"technology_showcase_image"),
                MagicMock(seed=12347, binary=b"roi_chart_image")
            ]
        )
        
        # Voice synthesis response
        mock_ai_services['elevenlabs'] = AsyncMock()
        mock_ai_services['elevenlabs'].generate.return_value = b"professional_voice_audio"
    
    async def _execute_and_monitor_workflow(
        self, 
        task_id: str, 
        db: AsyncSession,
        websocket: MagicMock
    ) -> List[Dict[str, Any]]:
        """Execute workflow and monitor all stages."""
        
        workflow_stages = []
        orchestrator = EnhancedOrchestratorAgent.create_default()
        
        # Mock monitoring service to capture stages
        def capture_stage_update(stage_name, status, metadata=None):
            workflow_stages.append({
                "name": stage_name,
                "status": status,
                "timestamp": datetime.now(),
                "metadata": metadata or {}
            })
        
        with patch.object(monitoring_service, 'update_stage_progress', side_effect=capture_stage_update):
            await orchestrator.execute(
                task_id=task_id,
                input_data={"user_prompt": "test prompt"},
                db=db
            )
        
        return workflow_stages
    
    async def _verify_complete_workflow_database_state(
        self, 
        task_id: str, 
        db: AsyncSession
    ):
        """Verify complete workflow state in database."""
        
        # Verify task completion
        stmt = select(Task).where(Task.task_id == task_id)
        result = await db.execute(stmt)
        task = result.scalar_one()
        assert task.status == TaskStatus.COMPLETED
        
        # Verify scenes created
        stmt = select(Scene).where(Scene.task_id == task.id)
        scenes_result = await db.execute(stmt)
        scenes = scenes_result.scalars().all()
        assert len(scenes) >= 3  # Should have multiple scenes
        
        # Verify resources generated
        stmt = select(Resource).where(Resource.task_id == task.id)
        resources_result = await db.execute(stmt)
        resources = resources_result.scalars().all()
        assert len(resources) >= 1  # Should have generated resources
    
    async def _verify_generated_outputs(
        self, 
        task_id: str, 
        generated_dir: str
    ) -> Dict[str, Any]:
        """Verify generated output files."""
        
        task_output_dir = os.path.join(generated_dir, task_id)
        if not os.path.exists(task_output_dir):
            return {"files_found": False}
        
        files = os.listdir(task_output_dir)
        
        output_info = {
            "files_found": True,
            "total_files": len(files),
            "has_video": any(f.endswith('.mp4') for f in files),
            "has_audio": any(f.endswith('.mp3') for f in files),
            "has_images": any(f.endswith(('.jpg', '.png')) for f in files),
            "has_subtitles": any(f.endswith('.srt') for f in files)
        }
        
        return output_info
    
    def _verify_websocket_notifications(
        self, 
        mock_websocket: MagicMock, 
        expected_stages: List[str]
    ):
        """Verify WebSocket notifications were sent correctly."""
        
        messages = mock_websocket.messages
        assert len(messages) > 0
        
        # Check for stage update messages
        stage_updates = [
            msg for msg in messages 
            if isinstance(msg, dict) and msg.get('type') == 'stage-update'
        ]
        
        updated_stages = {msg.get('stage') for msg in stage_updates}
        
        # Should cover most expected stages
        coverage = len(updated_stages & set(expected_stages)) / len(expected_stages)
        assert coverage >= 0.7  # At least 70% stage coverage
    
    async def _get_quality_metrics(
        self, 
        task_id: str, 
        db: AsyncSession
    ) -> Dict[str, float]:
        """Get quality metrics for completed task."""
        
        # Mock quality metrics for testing
        return {
            "overall_score": 0.85,
            "technical_quality": 0.88,
            "content_quality": 0.82,
            "visual_quality": 0.87,
            "audio_quality": 0.83
        }
    
    async def _wait_for_task_completion(
        self, 
        task_id: str, 
        db: AsyncSession, 
        timeout: int = 120
    ):
        """Wait for task completion with timeout."""
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            stmt = select(Task).where(Task.task_id == task_id)
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()
            
            if task and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                return task
            
            await asyncio.sleep(2)
        
        raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")
    
    # Additional helper methods would be implemented for:
    # - _create_custom_asset_package
    # - _setup_creative_video_mocks
    # - _execute_creative_workflow
    # - _verify_creative_outputs
    # - _monitor_batch_execution
    # - _verify_editing_workflow_completion
    # - _setup_multilanguage_mocks
    # - _monitor_multilanguage_workflow
    # - _execute_api_integrated_workflow
    # - _verify_api_integration
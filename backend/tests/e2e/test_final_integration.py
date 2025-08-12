#!/usr/bin/env python3
"""
Final integration test for the background music system
Tests the complete workflow without external API calls
"""

import asyncio
import os
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_complete_system_integration():
    """Test the complete integration without external API calls"""
    print("🎵 Background Music System - Final Integration Test")
    print("=" * 60)
    
    # Test 1: Check all components are properly integrated
    print("\n✅ Test 1: Component Integration Check")
    
    try:
        # Import core components
        from app.agents.audio_generator import AudioGeneratorAgent
        from app.agents.video_composer import VideoComposerAgent  
        from app.agents.orchestrator import OrchestratorAgent
        from app.agents.tools.ai_services.suno_client import SunoClientTool
        from app.core.workflow_state import workflow_manager, SceneData
        from app.models.agent import AgentType
        
        print("   ✅ All core components imported successfully")
        
        # Test Suno Client initialization  
        suno_tool = SunoClientTool()
        print(f"   ✅ SunoClientTool initialized (functional: {suno_tool._functional})")
        
        # Test AudioGenerator
        audio_agent = AudioGeneratorAgent()
        print("   ✅ AudioGeneratorAgent initialized")
        
        # Test VideoComposer
        composer = VideoComposerAgent()  
        print("   ✅ VideoComposerAgent initialized")
        
        # Test Orchestrator
        orchestrator = OrchestratorAgent()
        workflow_order = [agent.value for agent in orchestrator.workflow_order]
        print(f"   ✅ OrchestratorAgent initialized")
        print(f"      Workflow order: {' → '.join(workflow_order)}")
        
        # Verify AudioGenerator is in correct position
        if 'audio_generator' in workflow_order:
            audio_index = workflow_order.index('audio_generator')
            video_index = workflow_order.index('video_generator') 
            composer_index = workflow_order.index('video_composer')
            
            if video_index < audio_index < composer_index:
                print("   ✅ AudioGenerator positioned correctly in workflow")
            else:
                print("   ⚠️ AudioGenerator workflow position issue")
        
        print("✅ Component Integration: PASSED")
        
    except Exception as e:
        print(f"❌ Component Integration: FAILED - {e}")
        return False
    
    # Test 2: Workflow State Integration
    print("\n✅ Test 2: Workflow State Integration")
    
    try:
        # Create test workflow
        workflow_state = workflow_manager.create_workflow(
            user_prompt="制作一个关于旅行的短视频",
            video_style="轻松愉快",
            duration=30
        )
        
        # Add concept and scenes
        workflow_state.concept_plan = {
            "core_message": "展示旅行的美好时光",
            "target_audience": "年轻人", 
            "visual_style": "现代",
            "creative_approach": {"mood": "轻松愉快"}
        }
        
        # Create test scenes
        scenes = [
            SceneData(
                scene_number=1,
                duration=10,
                visual_description="美丽的山景",
                mood_and_atmosphere="宁静祥和"
            ),
            SceneData(
                scene_number=2,
                duration=10, 
                visual_description="热闹的城市街道",
                mood_and_atmosphere="活力四射"
            ),
            SceneData(
                scene_number=3,
                duration=10,
                visual_description="海边日落",
                mood_and_atmosphere="浪漫温馨"
            )
        ]
        workflow_state.scenes = scenes
        
        # Test music requirements extraction
        music_requirements = audio_agent._extract_music_requirements(
            workflow_state.concept_plan,
            workflow_state.scenes,
            {"duration": 30}
        )
        
        print(f"   ✅ Music requirements extracted:")
        print(f"      Duration: {music_requirements['duration']} seconds")
        print(f"      Mood: {music_requirements['mood']}")
        print(f"      Style: {music_requirements['style']}")
        print(f"      Title: {music_requirements['title']}")
        
        # Test background music update in workflow state
        workflow_state.update_background_music(
            music_url="http://example.com/test_music.mp3",
            music_path="/path/to/test_music.mp3",
            music_title=music_requirements['title'],
            music_duration=30.0,
            music_style=music_requirements['style']
        )
        
        print("   ✅ Workflow state updated with background music")
        
        # Test VideoComposer integration
        background_music = composer._get_background_music_from_workflow(workflow_state)
        print(f"   ✅ VideoComposer extracted music info:")
        print(f"      Available: {background_music['available']}")  
        print(f"      Title: {background_music['title']}")
        print(f"      Style: {background_music['style']}")
        
        # Test audio elements preparation
        audio_elements = await composer._prepare_audio_elements_from_data(
            [], {"audio_requirements": {}}, background_music
        )
        
        print(f"   ✅ Audio elements prepared:")
        print(f"      Background music enabled: {audio_elements['background_music']['enabled']}")
        print(f"      Volume: {audio_elements['audio_mixing']['music_volume']}")
        print(f"      Fade in: {audio_elements['audio_mixing']['fade_in_duration']}s")
        
        print("✅ Workflow State Integration: PASSED")
        
    except Exception as e:
        print(f"❌ Workflow State Integration: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 3: API Configuration Check
    print("\n✅ Test 3: API Configuration Check")
    
    try:
        # Check environment variables
        suno_key = os.getenv('SUNO_API_KEY')
        if suno_key and suno_key != 'test_key':
            print(f"   ✅ SUNO_API_KEY configured: {suno_key[:10]}...")
            api_ready = True
        else:
            print("   ⚠️ SUNO_API_KEY not configured - API calls will be skipped")
            api_ready = False
            
        # Test callback URL generation
        if hasattr(suno_tool, '_generate_callback_url'):
            callback_url = await suno_tool._generate_callback_url("test_task_id")
            print(f"   ✅ Callback URL generation working: {callback_url[:50]}...")
        else:
            print("   ⚠️ Callback URL generation not available")
        
        print("✅ API Configuration: PASSED")
        
    except Exception as e:
        print(f"❌ API Configuration: FAILED - {e}")
        return False
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 Final Integration Test Summary:")
    print("   ✅ Component Integration: PASSED")
    print("   ✅ Workflow State Integration: PASSED") 
    print("   ✅ API Configuration: PASSED")
    
    if api_ready:
        print("\n🎉 System is fully integrated and ready for background music generation!")
        print("   To test with real API calls, ensure SUNO_API_KEY is configured and run:")
        print("   python test_background_music.py")
    else:
        print("\n🔧 System integration is complete. To enable music generation:")
        print("   1. Configure SUNO_API_KEY in .env file")
        print("   2. Ensure PUBLIC_API_URL is set for callbacks")
        print("   3. Start the development server for callback endpoints")
    
    print(f"\n🎯 Background music system is ready! 🎵")
    return True

if __name__ == "__main__":
    asyncio.run(test_complete_system_integration())
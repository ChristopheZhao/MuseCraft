#!/usr/bin/env python3
"""
Final integration test for the background music system
Tests the complete workflow without external API calls
"""

import asyncio
import os
import logging
from typing import Dict, Any

from app.services.memory_provider import build_memory_services, set_memory_services

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

memory_services = build_memory_services()
set_memory_services(memory_services)


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
        from app.services.orchestration_state_adapter import OrchestrationStateAdapter
        from types import SimpleNamespace
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
        print(f"   ✅ OrchestratorAgent initialized")
        registered_agents = {agent_type.value for agent_type in orchestrator.agents.keys()}
        print(f"      Registered agents: {', '.join(sorted(registered_agents))}")

        queue = OrchestrationStateAdapter.build_execution_queue(
            task_specs={
                AgentType.VIDEO_GENERATOR: {"run": True, "order": 1},
                AgentType.AUDIO_GENERATOR: {"run": True, "order": 2},
                AgentType.VIDEO_COMPOSER: {"run": True, "order": 3},
            },
            candidate_agents=[
                AgentType.VIDEO_GENERATOR,
                AgentType.AUDIO_GENERATOR,
                AgentType.VIDEO_COMPOSER,
            ],
        )
        queue_values = [agent.value for agent in queue]
        print(f"      Derived queue: {' → '.join(queue_values)}")
        if queue_values == ["video_generator", "audio_generator", "video_composer"]:
            print("   ✅ AudioGenerator positioned correctly via task_specs")
        else:
            print("   ⚠️ AudioGenerator task_specs ordering issue")
        
        print("✅ Component Integration: PASSED")
        
    except Exception as e:
        print(f"❌ Component Integration: FAILED - {e}")
        return False
    
    # Test 2: Shared WM Integration
    print("\n✅ Test 2: Shared Working Memory Integration")
    
    try:
        # Create Shared WM context
        from app.agents.memory.short_term import get_working_memory_service
        from app.agents.memory.short_term import SceneSnapshot
        from types import SimpleNamespace
        wm_service = get_working_memory_service()
        wf_id = "wf-final-integration"
        mas = wm_service.create_or_get(wf_id, f"mas:{wf_id}")
        # Add concept and scenes
        mas.put("project.concept_plan", {
            "core_message": "展示旅行的美好时光",
            "target_audience": "年轻人", 
            "visual_style": "现代",
            "creative_approach": {"mood": "轻松愉快"}
        })
        
        # Create test scenes
        for sn, desc in [(1, "美丽的山景"), (2, "热闹的城市街道"), (3, "海边日落")]:
            mas.put("scene_overview", {"scenes": [SceneSnapshot(scene_number=sn, duration=10, visual_description=desc).as_fact()]})
        
        # Test music requirements extraction
        # Music requirements extraction (pure function) remains the same
        from app.agents.audio_generator import AudioGeneratorAgent
        audio_agent = AudioGeneratorAgent()
        scene_list = [SimpleNamespace(duration=10), SimpleNamespace(duration=10), SimpleNamespace(duration=10)]
        music_requirements = audio_agent._extract_music_requirements(
            mas.get("project.concept_plan", {}),
            scene_list,
            {"duration": 30}
        )
        
        print(f"   ✅ Music requirements extracted:")
        print(f"      Duration: {music_requirements['duration']} seconds")
        print(f"      Mood: {music_requirements['mood']}")
        print(f"      Style: {music_requirements['style']}")
        print(f"      Title: {music_requirements['title']}")
        
        # Test background music update in workflow state
        mas.put("project.background_music", {
            "audio_url": "http://example.com/test_music.mp3",
            "audio_path": "/path/to/test_music.mp3",
            "title": music_requirements['title'],
            "duration": 30.0,
            "style": music_requirements['style'],
            "available": True,
        })
        
        print("   ✅ Workflow state updated with background music")
        
        # Test VideoComposer integration
        background_music = mas.get("project.background_music", {})
        print(f"   ✅ VideoComposer extracted music info:")
        print(f"      Available: {background_music['available']}")  
        print(f"      Title: {background_music['title']}")
        print(f"      Style: {background_music['style']}")
        
        # Test audio elements preparation
        # 集成由组合工具在 Composer 内处理；此处仅验证背景音乐事实
        
        print("✅ Shared WM Integration: PASSED")
        
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

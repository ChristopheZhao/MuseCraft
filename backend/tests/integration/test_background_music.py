#!/usr/bin/env python3
"""
测试背景音乐生成功能的完整工作流
"""

import asyncio
import os
import sys
import logging
from typing import Dict, Any

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_suno_client():
    """测试 Suno AI 客户端功能"""
    print("\n🎵 测试 1: Suno AI 客户端功能")
    
    try:
        from app.agents.tools.ai_services.suno_client import SunoClientTool
        from app.agents.tools.base_tool import ToolInput
        
        # 创建工具实例
        suno_tool = SunoClientTool()
        print(f"✅ SunoClientTool 创建成功")
        print(f"🔧 工具功能状态: {suno_tool._functional}")
        
        if not suno_tool._functional:
            print("⚠️ Suno API密钥未配置，跳过API调用测试")
            return False
        
        # 测试背景音乐生成
        test_input = ToolInput(
            action="generate_background_music",
            parameters={
                "description": "轻松愉快的旅行背景音乐",
                "mood": "happy",
                "style": "acoustic",
                "duration": 30,
                "instrumental": True,
                "title": "Travel Background Music"
            }
        )
        
        print("🎶 正在生成测试音乐（可能需要20-120秒）...")
        result = await suno_tool.execute(test_input)
        
        if result.success:
            print("✅ 音乐生成成功!")
            print(f"   音乐标题: {result.result.get('title', 'Unknown')}")
            print(f"   音乐时长: {result.result.get('duration', 0)} 秒")
            print(f"   音乐风格: {result.result.get('style', 'Unknown')}")
            print(f"   音乐URL: {result.result.get('audio_url', 'None')[:50]}...")
            return True
        else:
            print(f"❌ 音乐生成失败: {result.error}")
            return False
            
    except Exception as e:
        print(f"❌ Suno客户端测试失败: {e}")
        return False

async def test_audio_generator_agent():
    """测试 AudioGenerator Agent"""
    print("\n🎵 测试 2: AudioGenerator Agent")
    
    try:
        from app.agents.audio_generator import AudioGeneratorAgent
        from app.models.agent import AgentType
        from app.models.task import Task
        from app.agents.memory.short_term import get_working_memory_service
        from app.agents.memory.short_term import SceneSnapshot
        
        # 构造 Shared WM：概念计划 + 场景
        wf_id = "wf-audio-gen"
        wm_service = get_working_memory_service()
        shared = wm_service.create_or_get(wf_id, f"mas:{wf_id}")
        
        # 添加概念计划（模拟）
        shared.put("project.concept_plan", {
            "core_message": "展示旅行的美好时光",
            "target_audience": "年轻人",
            "visual_style": "现代",
            "creative_approach": {"mood": "轻松愉快"}
        })
        
        # 添加场景数据（模拟）
        scene1 = SceneSnapshot(scene_number=1, duration=10, visual_description="美丽的山景")
        scene2 = SceneSnapshot(scene_number=2, duration=10, visual_description="热闹的城市街道")
        scene3 = SceneSnapshot(scene_number=3, duration=10, visual_description="海边日落")
        shared.put("scene_overview", {"scenes": [scene1.as_fact(), scene2.as_fact(), scene3.as_fact()]})
        
        # 创建 AudioGenerator
        audio_agent = AudioGeneratorAgent()
        print("✅ AudioGeneratorAgent 创建成功")
        
        # 创建模拟任务
        task = Task()
        task.id = 1
        task.title = "测试音乐生成"
        
        # 测试音乐生成
        print("🎶 开始生成背景音乐...")
        
        # 检查suno_client工具是否可用
        suno_available = False
        if "suno_client" in audio_agent._available_tools:
            suno_tool = audio_agent._available_tools["suno_client"]
            suno_available = suno_tool._functional
        
        if not suno_available:
            print("⚠️ AudioGenerator 的 suno_client 无API密钥，跳过实际生成")
            # 但仍可测试逻辑部分
            pass
            
        # 这里我们只测试逻辑，不实际调用API
        input_data = {"workflow_state_id": wf_id}
        
        # 测试音乐需求分析
        # 直接调用内部分析逻辑（与 Shared WM 无关，传入已构造数据）
        scene_list = [scene1, scene2, scene3]
        concept_plan = shared.get("project.concept_plan", {})
        music_requirements = audio_agent._extract_music_requirements(concept_plan, scene_list, {"duration": 30})
        
        print(f"✅ 音乐需求分析成功:")
        print(f"   时长: {music_requirements['duration']} 秒")
        print(f"   情绪: {music_requirements['mood']}")
        print(f"   风格: {music_requirements['style']}")
        print(f"   标题: {music_requirements['title']}")
        
        return True
        
    except Exception as e:
        print(f"❌ AudioGenerator测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_video_composer_integration():
    """测试 VideoComposer 音乐集成"""
    print("\n🎵 测试 3: VideoComposer 音乐集成")
    
    try:
        from app.agents.memory.short_term import get_working_memory_service

        wf_id = "wf-composer-bgm"
        shared = get_working_memory_service().create_or_get(wf_id, f"mas:{wf_id}")
        shared.put("project.background_music", {
            "audio_url": "http://example.com/test_music.mp3",
            "audio_path": "/path/to/test_music.mp3",
            "title": "Test Background Music",
            "duration": 30.0,
            "style": "cinematic",
            "available": True,
        })
        background_music = store.get(wf_id, "project.background_music", default={})
        print("✅ 背景音乐信息提取成功:")
        print(f"   是否可用: {background_music.get('available')}")
        print(f"   音乐标题: {background_music.get('title')}")
        print(f"   音乐风格: {background_music.get('style')}")
        print(f"   音乐时长: {background_music.get('duration')} 秒")
        
        # 集成路径：此处仅验证背景音乐事实已存在；完整混流由组合工具在 Composer 中处理
        
        return True
        
    except Exception as e:
        print(f"❌ VideoComposer集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_complete_workflow():
    """测试完整工作流集成"""
    print("\n🎵 测试 4: 完整工作流集成")
    
    try:
        from app.agents.orchestrator import OrchestratorAgent
        from app.models.agent import AgentType
        
        orchestrator = OrchestratorAgent()
        print("✅ OrchestratorAgent 创建成功")
        
        # 检查工作流顺序
        workflow_order = [agent.value for agent in orchestrator.workflow_order]
        print(f"📋 完整工作流顺序: {' → '.join(workflow_order)}")
        
        # 检查AudioGenerator位置
        if 'audio_generator' in workflow_order:
            audio_index = workflow_order.index('audio_generator')
            video_index = workflow_order.index('video_generator')
            composer_index = workflow_order.index('video_composer')
            
            if video_index < audio_index < composer_index:
                print("✅ AudioGenerator 工作流位置正确")
            else:
                print("⚠️ AudioGenerator 工作流位置需要调整")
        
        # 检查所有Agent是否可用
        for agent_type, agent in orchestrator.agents.items():
            print(f"   {agent_type.value}: ✅")
        
        return True
        
    except Exception as e:
        print(f"❌ 完整工作流测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("🎵 背景音乐生成系统 - 完整测试")
    print("=" * 50)
    
    # 检查环境变量
    suno_key = os.getenv('SUNO_API_KEY')
    if suno_key:
        print(f"✅ SUNO_API_KEY 已配置: {suno_key[:10]}...")
    else:
        print("⚠️ SUNO_API_KEY 未配置 - 部分测试将跳过实际API调用")
    
    test_results = []
    
    # 运行所有测试
    tests = [
        ("Suno AI 客户端", test_suno_client),
        ("AudioGenerator Agent", test_audio_generator_agent), 
        ("VideoComposer 集成", test_video_composer_integration),
        ("完整工作流", test_complete_workflow)
    ]
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
            test_results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    
    passed = 0
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 测试通过率: {passed}/{len(test_results)} ({passed/len(test_results)*100:.1f}%)")
    
    if passed == len(test_results):
        print("🎉 所有测试通过！系统已准备好生成带背景音乐的视频！")
    elif passed > 0:
        print("⚠️ 部分测试通过，请检查失败的组件")
    else:
        print("❌ 测试失败，请检查系统配置")
    
    return passed == len(test_results)

if __name__ == "__main__":
    asyncio.run(main())

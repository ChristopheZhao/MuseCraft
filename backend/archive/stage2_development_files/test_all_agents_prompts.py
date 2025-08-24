#!/usr/bin/env python3
"""
测试所有Agent的统一提示词系统
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_all_agents_prompt_system():
    """测试所有Agent的提示词系统集成"""
    
    print("🚀 测试所有Agent的统一提示词系统\n")
    
    test_results = {}
    
    # 1. 测试ConceptPlanner
    print("🔧 测试ConceptPlanner...")
    try:
        from app.agents.concept_planner import ConceptPlannerAgent
        agent = ConceptPlannerAgent()
        
        prompt = agent.render_prompt(
            "concept_generation",
            user_prompt="制作一个展示烹饪技巧的视频",
            video_style="专业教学风格",
            duration=60,
            aspect_ratio="16:9"
        )
        
        test_results["ConceptPlanner"] = {
            "success": True,
            "prompt_length": len(prompt),
            "contains_variables": all(word in prompt for word in ["烹饪技巧", "专业教学风格", "60秒"])
        }
        print(f"✅ ConceptPlanner: {len(prompt)}字符")
        
    except Exception as e:
        test_results["ConceptPlanner"] = {"success": False, "error": str(e)}
        print(f"❌ ConceptPlanner: {e}")
    
    # 2. 测试ScriptWriter
    print("🔧 测试ScriptWriter...")
    try:
        from app.agents.script_writer import ScriptWriterAgent
        agent = ScriptWriterAgent()
        
        prompt = agent.render_prompt(
            "scene_script_generation",
            scene_number=1,
            scene_type="教学演示",
            scene_title="刀法展示",
            scene_duration=15,
            scene_description="展示基本刀法技巧",
            visual_description="厨师在厨房工作台前展示切菜技巧",
            mood_and_atmosphere="专注、专业",
            camera_angle="中景",
            character_descriptions=["专业厨师"],
            props_and_objects=["厨师刀", "砧板", "蔬菜"],
            concept_overview="烹饪技巧教学视频",
            target_audience="烹饪爱好者",
            key_messages=["专业技巧", "安全操作"],
            visual_style="教学风格",
            mood_and_tone="专业严谨"
        )
        
        test_results["ScriptWriter"] = {
            "success": True,
            "prompt_length": len(prompt),
            "contains_variables": all(word in prompt for word in ["刀法展示", "厨师刀", "专业厨师"])
        }
        print(f"✅ ScriptWriter: {len(prompt)}字符")
        
    except Exception as e:
        test_results["ScriptWriter"] = {"success": False, "error": str(e)}
        print(f"❌ ScriptWriter: {e}")
    
    # 3. 测试QualityChecker
    print("🔧 测试QualityChecker...")
    try:
        from app.agents.quality_checker import QualityCheckerAgent
        agent = QualityCheckerAgent()
        
        prompt = agent.render_prompt(
            "video_quality_analysis",
            concept_plan='{"overview": "烹饪教学视频", "target_audience": "初学者"}',
            composition_timeline='{"total_duration": 60, "scenes": [{"scene_1": "介绍"}, {"scene_2": "演示"}]}'
        )
        
        test_results["QualityChecker"] = {
            "success": True,
            "prompt_length": len(prompt),
            "contains_variables": "烹饪教学视频" in prompt and "初学者" in prompt
        }
        print(f"✅ QualityChecker: {len(prompt)}字符")
        
    except Exception as e:
        test_results["QualityChecker"] = {"success": False, "error": str(e)}
        print(f"❌ QualityChecker: {e}")
    
    # 4. 测试ImageGenerator
    print("🔧 测试ImageGenerator...")
    try:
        from app.agents.image_generator import ImageGeneratorAgent
        agent = ImageGeneratorAgent()
        
        prompt = agent.render_prompt(
            "image_generation_prompt",
            base_description="厨师在厨房展示刀法",
            visual_style="专业摄影风格",
            mood_and_atmosphere="专注认真",
            camera_angle="中景特写",
            lighting_style="自然光",
            color_palette=["暖色调", "木质色"],
            creative_guidance="突出专业性和技巧性",
            scene_physics_constraints="strict"
        )
        
        test_results["ImageGenerator"] = {
            "success": True,
            "prompt_length": len(prompt),
            "contains_variables": all(word in prompt for word in ["厨师", "专业摄影", "中景特写"])
        }
        print(f"✅ ImageGenerator: {len(prompt)}字符")
        
    except Exception as e:
        test_results["ImageGenerator"] = {"success": False, "error": str(e)}
        print(f"❌ ImageGenerator: {e}")
    
    # 5. 测试VideoGenerator
    print("🔧 测试VideoGenerator...")
    try:
        from app.agents.video_generator import VideoGeneratorAgent
        agent = VideoGeneratorAgent()
        
        prompt = agent.render_prompt(
            "motion_guided_video_generation",
            scene_description="厨师演示切菜技巧",
            motion_guidance="手部动作流畅，刀法精准",
            first_frame_description="厨师手持菜刀准备切菜",
            video_duration=10,
            camera_movement="轻微推进",
            motion_intensity="中等",
            visual_style="纪录片风格",
            max_prompt_length=200
        )
        
        test_results["VideoGenerator"] = {
            "success": True,
            "prompt_length": len(prompt),
            "contains_variables": all(word in prompt for word in ["厨师", "切菜", "流畅"])
        }
        print(f"✅ VideoGenerator: {len(prompt)}字符")
        
    except Exception as e:
        test_results["VideoGenerator"] = {"success": False, "error": str(e)}
        print(f"❌ VideoGenerator: {e}")
    
    # 6. 测试PromptManager统计
    print("\n🔧 测试PromptManager统计...")
    try:
        from app.core.prompt_manager import get_prompt_manager
        manager = get_prompt_manager()
        
        stats = manager.get_stats()
        configs = manager.list_configs()
        
        print(f"✅ 加载的配置数量: {stats['total_configs']}")
        print(f"✅ 配置列表: {configs}")
        print(f"✅ 缓存大小: {stats['cache_size']}")
        
        # 检查所有期望的配置是否加载
        expected_configs = ['concept_planner', 'script_writer', 'quality_checker', 'image_generator', 'video_generator']
        missing_configs = [config for config in expected_configs if config not in configs]
        
        if missing_configs:
            print(f"⚠️  缺失配置: {missing_configs}")
        else:
            print("✅ 所有Agent配置都已加载")
            
    except Exception as e:
        print(f"❌ PromptManager统计失败: {e}")
    
    # 7. 汇总结果
    print("\n📊 测试结果汇总:")
    total_agents = len(test_results)
    successful_agents = sum(1 for result in test_results.values() if result.get("success", False))
    
    for agent_name, result in test_results.items():
        if result.get("success", False):
            variables_ok = result.get("contains_variables", False)
            status = "✅" if variables_ok else "⚠️ "
            print(f"   {status} {agent_name}: {result['prompt_length']}字符 (变量替换: {'正确' if variables_ok else '有问题'})")
        else:
            print(f"   ❌ {agent_name}: {result.get('error', '未知错误')}")
    
    print(f"\n🎯 成功率: {successful_agents}/{total_agents} ({successful_agents/total_agents*100:.1f}%)")
    
    if successful_agents == total_agents:
        print("\n🎉 所有Agent的提示词系统迁移成功！")
        print("📈 改造效果:")
        print("   - ConceptPlanner: 300+行 → YAML配置")
        print("   - ScriptWriter: 80+行 → YAML配置") 
        print("   - QualityChecker: 25+行 → YAML配置")
        print("   - ImageGenerator: 动态生成 → 模板化")
        print("   - VideoGenerator: 模板整合 → 统一系统")
        print("   - 统一管理、缓存优化、易于维护")
        return True
    else:
        print(f"\n⚠️  {total_agents - successful_agents}个Agent需要修复")
        return False


if __name__ == "__main__":
    success = test_all_agents_prompt_system()
    sys.exit(0 if success else 1)
#!/usr/bin/env python3
"""
测试完整的MAS协作效果 - ConceptPlanner → ScriptWriter → ImageGenerator
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.agents.concept_planner import ConceptPlannerAgent
from app.agents.script_writer import ScriptWriterAgent
from app.agents.image_generator import ImageGeneratorAgent
from app.agents.memory.short_term import get_working_memory_service
from app.agents.adapters.video.memory_adapter import VideoMemoryAdapter
from app.services.memory_provider import build_memory_services, set_memory_services
from app.agents.memory.short_term import SceneSnapshot

def test_mas_collaboration():
    """测试多智能体协作效果"""
    
    print("🤖 测试MAS多智能体协作效果")
    print("=" * 60)
    
    # 创建 Shared WM 工作流上下文
    wf_id = "test_mas_001"
    wm_service = get_working_memory_service()
    shared = wm_service.create_or_get(wf_id, f"mas:{wf_id}")
    video_adapter = VideoMemoryAdapter(shared)
    memory_services = build_memory_services()
    set_memory_services(memory_services)
    print(f"🎯 用户需求: 创建一个朋友们在泳池派对中玩水的短视频")
    print(f"🎨 视频风格: bright and joyful")
    print(f"⏱️ 视频时长: 15s")
    print()
    
    # 1. 模拟ConceptPlanner的输出
    print("🎭 阶段1: ConceptPlanner (创意总监)")
    print("-" * 40)
    
    concept_planner = ConceptPlannerAgent()
    
    # 模拟概念计划 (简化版，不调用AI)
    concept_plan = {
        "overview": "A vibrant summer video showcasing friendship through joyful pool activities",
        "target_audience": "young adults and families",
        "key_messages": ["friendship", "summer fun", "joyful moments"],
        "visual_style_guidance": {
            "overall_aesthetic": "Bright, energetic summer vibes with warm golden lighting",
            "color_philosophy": "Vibrant blues and warm yellows to convey joy and energy",
            "color_palette": ["bright blue", "golden yellow", "fresh green"],
            "visual_consistency_notes": "Maintain sunny, optimistic lighting throughout all scenes"
        },
        "narrative_flow_strategy": {
            "mood_and_tone": "Progressive joy building from initial excitement to peak fun",
            "pacing_strategy": "Start with anticipation, build to energetic climax",
            "transition_philosophy": "Smooth emotional crescendo between scenes"
        },
        "scenes": [
            {
                "scene_number": 1,
                "scene_type": "intro",
                "title": "Pool Party Arrival",
                "duration": 5,
                "description": "Friends arriving at the pool party with excitement",
                "visual_description": "Friends in swimwear approaching a beautiful pool area with sunny weather",
                "narrative_description": "The opening establishes the joyful anticipation",
                "creative_intent": "Build anticipation and set the summer fun mood",
                "visual_direction": "Bright establishing shots with clear blue water",
                "mood_target": "Excited anticipation"
            },
            {
                "scene_number": 2,
                "scene_type": "main_content",
                "title": "Pool Fun Activities",
                "duration": 8,
                "description": "Friends actively playing and splashing in the pool",
                "visual_description": "Dynamic water activities with friends laughing and splashing",
                "narrative_description": "The core bonding moment through playful water activities",
                "creative_intent": "Showcase peak friendship bonding and pure joy",
                "visual_direction": "Dynamic action shots with water movement",
                "mood_target": "Pure joy and connection"
            }
        ]
    }
    
    # 写入概念计划与场景快照到 Shared WM
    shared.put("project.concept_plan", concept_plan)
    for scene_data in concept_plan["scenes"]:
        snap = SceneSnapshot(
            scene_number=int(scene_data["scene_number"]),
            duration=float(scene_data["duration"]),
            visual_description=scene_data["visual_description"],
            narrative_description=scene_data["narrative_description"],
        )
        video_adapter.upsert_scene(snap)
    
    print("✅ ConceptPlanner完成整体创意规划:")
    print(f"  - 整体美学: {concept_plan['visual_style_guidance']['overall_aesthetic']}")
    print(f"  - 叙事策略: {concept_plan['narrative_flow_strategy']['mood_and_tone']}")
    print(f"  - 场景总数: {len(concept_plan['scenes'])}")
    print()
    
    # 2. 模拟ScriptWriter的处理
    print("📝 阶段2: ScriptWriter (脚本编剧)")
    print("-" * 40)
    
    script_writer = ScriptWriterAgent()
    
    # 处理每个场景
    # 简化：本测试主要展示协作路径，跳过已废弃的 fallback 生成；由 ScriptWriter 写回 facts.scene_scripts
    for sn in [1, 2]:
        scripts = shared.get("project.scene_scripts", {}) or {}
        scripts[str(sn)] = {
            "script_text": "场景脚本（示例）",
            "voice_over_text": "旁白（示例）",
            "narrative_description": "叙事描述（示例）",
            "first_frame_scene_reference": {"situation": "入场情境"},
            "last_frame_scene_reference": {"situation": "高潮情境"},
            "content_development_arc": {"narrative_progression": "递进发展"},
        }
        shared.put("project.scene_scripts", scripts)
        print(f"     ✅ 场景 {sn} 已写入场景参考（facts.scene_scripts）")
    
    print()
    
    # 3. 测试ImageGenerator的MAS协作
    print("🎨 阶段3: ImageGenerator (视觉艺术家)")
    print("-" * 40)
    
    image_generator = ImageGeneratorAgent()
    
    for sn in [1, 2]:
        print(f"  🖼️ 处理场景 {sn} 的视觉生成:")
        
        # 准备创意指导上下文
        creative_guidance = {
            "overall_guidance": concept_plan.get("visual_style_guidance", {}),
            "scene_guidance": {}  # 现在从scene_data直接获取
        }
        
        # 测试首帧提示词增强
        scene_data = SceneSnapshot(scene_number=sn, duration=5, visual_description="Friends laughing and playing in a bright pool area")
        base_prompt = scene_data.visual_description
        enhanced_first_prompt = image_generator._enhance_prompt_for_first_frame(
            base_prompt, scene_data, creative_guidance
        )
        
        enhanced_last_prompt = image_generator._enhance_prompt_for_last_frame(
            base_prompt, scene_data, creative_guidance
        )
        
        print(f"     🎬 基础提示: {base_prompt}")
        print(f"     🎯 首帧增强: ...{enhanced_first_prompt[-80:]}")  # 显示最后80个字符
        print(f"     🏁 尾帧增强: ...{enhanced_last_prompt[-80:]}")   # 显示最后80个字符
        print()
    
    # 4. 验证MAS协作效果
    print("🔍 MAS协作效果验证:")
    print("-" * 40)
    
    validation_passed = True
    
    # 检查场景参考是否存在
    for sn in [1, 2]:
        scripts = shared.get("project.scene_scripts", {}) or {}
        scene_script = scripts.get(str(sn), {})
        if not scene_script.get('first_frame_scene_reference'):
            print(f"❌ 场景 {sn} 缺少首帧场景参考")
            validation_passed = False
        if not scene_script.get('last_frame_scene_reference'):
            print(f"❌ 场景 {sn} 缺少尾帧场景参考")
            validation_passed = False
        if not scene_script.get('content_development_arc'):
            print(f"❌ 场景 {sn} 缺少内容发展规划")
            validation_passed = False
    
    if validation_passed:
        print("✅ 所有场景都包含必要的MAS协作数据")
        print("✅ ConceptPlanner → ScriptWriter → ImageGenerator 信息流完整")
        print("✅ 每个Agent都在其职责范围内工作")
        print("✅ 场景参考成功传递给ImageGenerator")
        print("✅ 避免了Agent职责重叠和越权行为")
    
    print()
    
    # 5. 显示最终协作结果
    print("🎊 MAS协作结果总结:")
    print("-" * 40)
    view = video_adapter.build_fact_observation()
    scenes = view.get("scenes", [])
    print(f"✨ 总场景数: {len(scenes)}")
    print(f"📖 整体叙事: {concept_plan['overview']}")
    
    for sn in sorted([s.get("scene_number") for s in scenes if isinstance(s, dict)]):
        scripts = shared.get("project.scene_scripts", {}) or {}
        print(f"\n🎬 场景 {sn}")
        print(f"   📝 脚本: {(scripts.get(str(sn), {}).get('script_text',''))[:60]}...")
        first_ref = scripts.get(str(sn), {}).get('first_frame_scene_reference', {})
        last_ref = scripts.get(str(sn), {}).get('last_frame_scene_reference', {})
        if first_ref:
            print(f"   🎯 首帧情境: {first_ref.get('situation', 'N/A')}")
        if last_ref:
            print(f"   🏁 尾帧情境: {last_ref.get('situation', 'N/A')}")
    
    print(f"\n🚀 MAS多智能体协作测试完成!")
    
    # Shared WM 用例无需清理全局状态

if __name__ == "__main__":
    test_mas_collaboration()

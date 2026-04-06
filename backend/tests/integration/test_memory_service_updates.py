#!/usr/bin/env python3
"""
测试记忆服务对新MAS数据结构的支持
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.memory_provider import build_memory_services, set_memory_services

async def test_memory_service_updates():
    """测试记忆服务的新数据结构支持"""
    
    print("🧪 测试记忆服务MAS数据结构支持")
    print("=" * 60)
    
    workflow_id = "test_workflow_mas_001"
    
    # 测试1：存储增强的ConceptPlanner数据
    print("\n📋 测试1：存储增强的ConceptPlanner数据")
    print("-" * 40)
    
    enhanced_concept_plan = {
        "overview": "A heartwarming video about friendship",
        "target_audience": "young adults",
        "key_messages": ["friendship", "joy", "memories"],
        "visual_style_guidance": {
            "overall_aesthetic": "Bright and vibrant summer vibes",
            "color_philosophy": "Warm, energetic colors",
            "color_palette": ["bright blue", "sunny yellow", "fresh green"],
            "visual_consistency_notes": "Maintain sunny lighting throughout",
            "artistic_direction": "Modern, dynamic cinematography",
            "composition_philosophy": "Rule of thirds with dynamic movement",
            "visual_hierarchy": "Focus on human connections",
            "brand_alignment": "Youthful and energetic brand image"
        },
        "narrative_flow_strategy": {
            "mood_and_tone": "Joyful progression from anticipation to celebration",
            "pacing_strategy": "Build energy towards climax",
            "transition_philosophy": "Smooth emotional flow",
            "story_arc_design": "Three-act structure with emotional peak",
            "emotional_beats": "Anticipation → Excitement → Joy → Reflection",
            "audience_engagement_strategy": "Hook with relatable moments",
            "call_to_action_integration": "Celebrate your friendships"
        },
        "agent_collaboration_guidance": {
            "script_writer_guidance": {
                "narrative_priorities": "Focus on emotional connections",
                "dialogue_style": "Natural and conversational",
                "scene_development_approach": "Build from calm to energetic",
                "content_arc_strategy": "Each scene develops the friendship theme"
            },
            "visual_artist_guidance": {
                "creative_interpretation_scope": "Freedom within color palette",
                "visual_problem_solving": "Use lighting to convey mood",
                "consistency_requirements": "Maintain character appearances",
                "quality_standards": "High-quality, professional imagery"
            }
        },
        "scenes": [
            {
                "scene_number": 1,
                "scene_type": "intro",
                "title": "Friends Arrive",
                "final_duration": 3.5,
                "duration_reasoning": "场景时长3.5秒基于: 视觉复杂度[moderate], 内容密度[medium], 场景类型[intro]",
                "suggested_duration": 3.5,
                "visual_description": "Friends arriving at pool party location",
                "creative_intent": "Set anticipatory mood",
                "mood_target": "Excited anticipation"
            }
        ]
    }
    
    services = build_memory_services()
    set_memory_services(services)
    gms = services.global_service
    success = await gms.store_creative_guidance(
        workflow_id=workflow_id,
        concept_plan=enhanced_concept_plan,
        agent_name="concept_planner"
    )
    
    print(f"✅ ConceptPlanner数据存储: {'成功' if success else '失败'}")
    
    # 测试2：检索增强的创意指导
    print("\n📋 测试2：检索增强的创意指导")
    print("-" * 40)
    
    guidance = await gms.retrieve_creative_guidance(
        workflow_id=workflow_id,
        scene_number=1
    )
    
    if guidance["has_guidance"]:
        overall = guidance["overall_guidance"]
        print("✅ 整体指导检索成功:")
        print(f"   - 视觉风格指导字段数: {len(overall.get('visual_style_guidance', {}))}")
        print(f"   - 叙事流策略字段数: {len(overall.get('narrative_flow_strategy', {}))}")
        print(f"   - Agent协作指导: {'✅ 存在' if overall.get('agent_collaboration_guidance') else '❌ 缺失'}")
        
        scene = guidance.get("scene_guidance", {})
        if scene:
            print(f"\n✅ 场景指导检索成功:")
            context = scene.get("context", {})
            print(f"   - 动态时长: {context.get('duration')}秒")
            print(f"   - 时长理由: {context.get('duration_reasoning', 'N/A')[:50]}...")
            print(f"   - 建议时长: {context.get('suggested_duration')}秒")
    
    # 测试3：存储ScriptWriter场景参考
    print("\n📋 测试3：存储ScriptWriter场景参考")
    print("-" * 40)
    
    scene_references = {
        "script_text": "Friends excitedly approach the pool area",
        "voice_over_text": "The best moments start with anticipation",
        "first_frame_scene_reference": {
            "situation": "Friends walking towards pool entrance",
            "character_emotional_state": "Excited and happy",
            "key_visual_elements": ["pool entrance", "bright sunlight", "smiling faces"],
            "action_potential": "About to enter pool area",
            "narrative_context": "Opening moment of fun day"
        },
        "last_frame_scene_reference": {
            "situation": "Friends at poolside ready to jump",
            "character_emotional_state": "Peak excitement",
            "key_visual_elements": ["pool edge", "clear water", "ready poses"],
            "action_completion": "Arrived and ready",
            "transition_preparation": "Ready for main action"
        },
        "content_development_arc": {
            "scene_concept_duration": "Dynamic 3.5 seconds",
            "narrative_progression": "From arrival to readiness",
            "emotional_journey": "Building excitement",
            "action_sequence": "Walk → Arrive → Prepare"
        }
    }
    
    ref_success = await gms.store_scene_references(
        workflow_id=workflow_id,
        scene_number=1,
        scene_references=scene_references,
        agent_name="script_writer"
    )
    
    print(f"✅ ScriptWriter场景参考存储: {'成功' if ref_success else '失败'}")
    
    # 测试4：检索ScriptWriter场景参考
    print("\n📋 测试4：检索ScriptWriter场景参考")
    print("-" * 40)
    
    retrieved_refs = await gms.retrieve_scene_references(
        workflow_id=workflow_id,
        scene_number=1,
        agent_name="image_generator"
    )
    
    if retrieved_refs:
        print("✅ 场景参考检索成功:")
        
        first_ref = retrieved_refs.get("first_frame_scene_reference", {})
        if first_ref:
            print(f"\n   🎬 首帧参考:")
            print(f"      - 情境: {first_ref.get('situation', 'N/A')}")
            print(f"      - 情感状态: {first_ref.get('character_emotional_state', 'N/A')}")
            print(f"      - 视觉元素: {first_ref.get('key_visual_elements', [])}")
        
        last_ref = retrieved_refs.get("last_frame_scene_reference", {})
        if last_ref:
            print(f"\n   🏁 尾帧参考:")
            print(f"      - 情境: {last_ref.get('situation', 'N/A')}")
            print(f"      - 情感状态: {last_ref.get('character_emotional_state', 'N/A')}")
            print(f"      - 动作完成: {last_ref.get('action_completion', 'N/A')}")
        
        arc = retrieved_refs.get("content_development_arc", {})
        if arc:
            print(f"\n   📈 内容发展:")
            print(f"      - 场景概念时长: {arc.get('scene_concept_duration', 'N/A')}")
            print(f"      - 叙事进展: {arc.get('narrative_progression', 'N/A')}")
            print(f"      - 情感旅程: {arc.get('emotional_journey', 'N/A')}")
    
    # 测试5：获取工作流记忆统计
    print("\n📋 测试5：工作流记忆统计")
    print("-" * 40)
    
    stats = await gms.get_workflow_memory_stats(workflow_id)
    
    workflow_stats = stats.get("workflow_specific", {})
    if workflow_stats:
        print(f"✅ 工作流统计:")
        print(f"   - 场景数量: {workflow_stats.get('scenes_count', 0)}")
        print(f"   - 存储时间: {workflow_stats.get('stored_at', 'N/A')}")
    
    # 验证新数据结构支持
    print("\n🔍 新数据结构支持验证:")
    print("-" * 40)
    
    validations = []
    
    # 检查Agent协作指导
    if overall.get("agent_collaboration_guidance"):
        validations.append("✅ 支持Agent协作指导存储和检索")
    else:
        validations.append("❌ 缺少Agent协作指导支持")
    
    # 检查动态时长数据
    if context.get("duration_reasoning"):
        validations.append("✅ 支持动态时长理由存储")
    else:
        validations.append("❌ 缺少动态时长理由支持")
    
    # 检查场景参考数据
    if retrieved_refs and "first_frame_scene_reference" in retrieved_refs:
        validations.append("✅ 支持ScriptWriter场景参考存储和检索")
    else:
        validations.append("❌ 缺少场景参考数据支持")
    
    # 检查增强的视觉指导
    visual_guide = overall.get("visual_style_guidance", {})
    if "composition_philosophy" in visual_guide and "visual_hierarchy" in visual_guide:
        validations.append("✅ 支持增强的视觉指导字段")
    else:
        validations.append("❌ 缺少增强的视觉指导字段")
    
    for validation in validations:
        print(f"   {validation}")
    
    all_good = all("✅" in v for v in validations)
    
    print(f"\n🎊 记忆服务更新测试{'完全成功' if all_good else '需要调整'}!")
    
    if all_good:
        print("   - 完整支持MAS协作数据结构")
        print("   - 支持动态时长和场景参考")
        print("   - 增强的创意指导存储完善")

async def main():
    await test_memory_service_updates()

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
独立测试记忆服务的新数据结构支持
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 直接导入需要的组件，避免循环导入
from app.agents.memory.long_term.manager import MemoryManager
from app.agents.memory.long_term.stores import DictMemoryStore, MemoryItem, MemoryType, MemoryImportance

async def test_memory_service_data_structures():
    """测试记忆服务对新MAS数据结构的支持"""
    
    print("🧪 独立测试记忆服务MAS数据结构支持")
    print("=" * 60)
    
    # 初始化记忆管理器
    default_store = DictMemoryStore()
    memory_manager = MemoryManager(
        stores={"default": default_store},
        config={
            "enable_consolidation": False,
            "enable_cleanup": False
        }
    )
    
    workflow_id = "test_mas_workflow_001"
    
    # 测试1：存储增强的ConceptPlanner数据结构
    print("\n📋 测试1：存储增强的ConceptPlanner记忆")
    print("-" * 40)
    
    enhanced_creative_guidance = {
        "agent_role": "Creative Director",
        "workflow_id": workflow_id,
        "creative_vision": "A vibrant friendship video",
        "visual_style_guidance": {
            "overall_aesthetic": "Bright summer vibes",
            "color_philosophy": "Warm and energetic",
            "color_palette": ["blue", "yellow", "green"],
            "visual_consistency_notes": "Maintain sunny lighting",
            "composition_philosophy": "Dynamic framing",
            "visual_hierarchy": "Focus on human connections",
            "brand_alignment": "Youthful energy"
        },
        "narrative_flow_strategy": {
            "mood_and_tone": "Joyful progression",
            "pacing_strategy": "Build to climax",
            "transition_philosophy": "Smooth flow",
            "story_arc_design": "Three-act structure",
            "emotional_beats": "Anticipation → Joy",
            "audience_engagement_strategy": "Relatable moments",
            "call_to_action_integration": "Celebrate friendship"
        },
        "agent_collaboration_guidance": {
            "script_writer_guidance": {
                "narrative_priorities": "Emotional connections",
                "content_arc_strategy": "Scene-based development"
            },
            "visual_artist_guidance": {
                "creative_interpretation_scope": "Within palette",
                "quality_standards": "Professional quality"
            }
        },
        "timestamp": datetime.now().isoformat()
    }
    
    concept_memory_id = await memory_manager.store_memory(
        content=enhanced_creative_guidance,
        memory_type=MemoryType.CONCEPTUAL,
        importance=MemoryImportance.HIGH,
        tags=["creative_direction", "mas_enhanced"],
        agent_id="concept_planner",
        task_id=workflow_id
    )
    
    print(f"✅ ConceptPlanner记忆存储成功: ID={concept_memory_id[:8]}...")
    
    # 测试2：存储ScriptWriter场景参考数据
    print("\n📋 测试2：存储ScriptWriter场景参考")
    print("-" * 40)
    
    scene_reference_data = {
        "agent_role": "Script Writer - Scene References",
        "workflow_id": workflow_id,
        "scene_number": 1,
        "first_frame_scene_reference": {
            "situation": "Friends approaching pool",
            "character_emotional_state": "Excited anticipation",
            "key_visual_elements": ["pool entrance", "sunlight"],
            "action_potential": "About to enter",
            "narrative_context": "Opening excitement"
        },
        "last_frame_scene_reference": {
            "situation": "Friends at poolside",
            "character_emotional_state": "Peak excitement",
            "key_visual_elements": ["pool edge", "water"],
            "action_completion": "Ready to jump",
            "transition_preparation": "Main action ready"
        },
        "content_development_arc": {
            "scene_concept_duration": "Dynamic 3.5s",
            "narrative_progression": "Arrival to readiness",
            "emotional_journey": "Building excitement",
            "action_sequence": "Walk → Arrive → Ready"
        },
        "timestamp": datetime.now().isoformat()
    }
    
    script_memory_id = await memory_manager.store_memory(
        content=scene_reference_data,
        memory_type=MemoryType.EPISODIC,
        importance=MemoryImportance.HIGH,
        tags=["scene_references", "scene_1", "mas_collaboration"],
        agent_id="script_writer",
        task_id=workflow_id
    )
    
    print(f"✅ ScriptWriter场景参考存储成功: ID={script_memory_id[:8]}...")
    
    # 测试3：存储动态时长数据
    print("\n📋 测试3：存储动态时长计算数据")
    print("-" * 40)
    
    dynamic_duration_data = {
        "agent_role": "Concept Planner - Duration Calculator",
        "workflow_id": workflow_id,
        "scene_number": 1,
        "duration_analysis": {
            "final_duration": 3.5,
            "suggested_duration": 3.5,
            "duration_reasoning": "场景时长3.5秒基于: 视觉复杂度[moderate], 内容密度[medium], 场景类型[intro]",
            "complexity_factors": {
                "visual_complexity": "moderate",
                "content_density": "medium",
                "scene_type_adjustment": 0.9
            }
        },
        "timestamp": datetime.now().isoformat()
    }
    
    duration_memory_id = await memory_manager.store_memory(
        content=dynamic_duration_data,
        memory_type=MemoryType.PROCEDURAL,
        importance=MemoryImportance.MEDIUM,
        tags=["duration_planning", "dynamic_timing", "scene_1"],
        agent_id="concept_planner",
        task_id=workflow_id
    )
    
    print(f"✅ 动态时长数据存储成功: ID={duration_memory_id[:8]}...")
    
    # 测试4：检索和验证数据
    print("\n📋 测试4：检索和验证存储的数据")
    print("-" * 40)
    
    # 检索创意指导
    creative_memories = await memory_manager.retrieve_memories(
        tags=["creative_direction"],
        task_id=workflow_id,
        limit=1
    )
    
    if creative_memories:
        creative_content = creative_memories[0].content
        visual_guide = creative_content.get("visual_style_guidance", {})
        
        print("✅ 创意指导检索成功:")
        print(f"   - 视觉风格字段数: {len(visual_guide)}")
        print(f"   - 包含构图哲学: {'✅' if 'composition_philosophy' in visual_guide else '❌'}")
        print(f"   - 包含Agent协作: {'✅' if 'agent_collaboration_guidance' in creative_content else '❌'}")
    
    # 检索场景参考
    scene_ref_memories = await memory_manager.retrieve_memories(
        tags=["scene_references", "scene_1"],
        task_id=workflow_id,
        limit=1
    )
    
    if scene_ref_memories:
        scene_ref = scene_ref_memories[0].content
        first_frame = scene_ref.get("first_frame_scene_reference", {})
        
        print("\n✅ 场景参考检索成功:")
        if first_frame:
            print(f"   - 首帧情境: {first_frame.get('situation', 'N/A')}")
            print(f"   - 情感状态: {first_frame.get('character_emotional_state', 'N/A')}")
        else:
            print("   - 首帧参考: 未找到")
        print(f"   - 内容发展: {'✅' if 'content_development_arc' in scene_ref else '❌'}")
    
    # 检索时长数据
    duration_memories = await memory_manager.retrieve_memories(
        tags=["duration_planning"],
        task_id=workflow_id,
        limit=1
    )
    
    if duration_memories:
        duration_data = duration_memories[0].content
        duration_analysis = duration_data.get("duration_analysis", {})
        
        print("\n✅ 时长数据检索成功:")
        print(f"   - 最终时长: {duration_analysis.get('final_duration')}秒")
        print(f"   - 时长理由: {duration_analysis.get('duration_reasoning', '')[:50]}...")
    
    # 测试5：记忆统计
    print("\n📋 测试5：记忆系统统计")
    print("-" * 40)
    
    stats = await memory_manager.get_memory_stats()
    
    print(f"✅ 记忆统计:")
    print(f"   - 总记忆数: {stats.get('total_memories', stats.get('total_items', 0))}")
    print(f"   - 短期记忆: {stats.get('short_term_count', stats.get('short_term', {}).get('count', 0))}")
    print(f"   - 长期记忆: {stats.get('long_term_count', stats.get('long_term', {}).get('count', 0))}")
    print(f"   - 情节记忆: {stats.get('episodic_count', stats.get('episodic', {}).get('count', 0))}")
    
    # 验证新数据结构支持
    print("\n🔍 MAS数据结构支持验证:")
    print("-" * 40)
    
    validations = []
    
    # 验证各项支持
    if creative_memories and "agent_collaboration_guidance" in creative_memories[0].content:
        validations.append("✅ 支持Agent协作指导存储")
    else:
        validations.append("❌ 缺少Agent协作指导")
    
    if scene_ref_memories and "first_frame_scene_reference" in scene_ref_memories[0].content:
        validations.append("✅ 支持场景参考数据存储")
    else:
        validations.append("❌ 缺少场景参考数据")
    
    if duration_memories and "duration_reasoning" in duration_memories[0].content.get("duration_analysis", {}):
        validations.append("✅ 支持动态时长数据存储")
    else:
        validations.append("❌ 缺少动态时长数据")
    
    if visual_guide.get("composition_philosophy") and visual_guide.get("visual_hierarchy"):
        validations.append("✅ 支持增强的视觉指导")
    else:
        validations.append("❌ 缺少增强视觉指导")
    
    for validation in validations:
        print(f"   {validation}")
    
    all_good = all("✅" in v for v in validations)
    
    print(f"\n🎊 记忆服务MAS数据结构测试{'完全成功' if all_good else '需要调整'}!")
    
    if all_good:
        print("   📝 记忆系统完全支持新的MAS协作数据结构")
        print("   🔄 支持动态时长和场景参考存储")
        print("   🎯 增强的创意指导完整保存")
        print("   🚀 可以支持完整的MAS工作流")

async def main():
    await test_memory_service_data_structures()

if __name__ == "__main__":
    asyncio.run(main())

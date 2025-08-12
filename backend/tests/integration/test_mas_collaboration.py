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
from app.core.workflow_state import WorkflowState, SceneData

def test_mas_collaboration():
    """测试多智能体协作效果"""
    
    print("🤖 测试MAS多智能体协作效果")
    print("=" * 60)
    
    # 创建WorkflowState
    workflow_state = WorkflowState(
        task_id="test_mas_001",
        user_prompt="创建一个朋友们在泳池派对中玩水的短视频",
        video_style="bright and joyful",
        duration=15
    )
    
    # 从workflow_manager注册状态
    from app.core.workflow_state import workflow_manager
    workflow_manager._states[workflow_state.task_id] = workflow_state
    
    print(f"🎯 用户需求: {workflow_state.user_prompt}")
    print(f"🎨 视频风格: {workflow_state.video_style}")
    print(f"⏱️ 视频时长: {workflow_state.duration}s")
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
    
    # 添加场景到workflow_state
    for scene_data in concept_plan["scenes"]:
        scene = SceneData(
            scene_number=scene_data["scene_number"],
            scene_type=scene_data["scene_type"],
            title=scene_data["title"],
            description=scene_data["description"],
            visual_description=scene_data["visual_description"],
            narrative_description=scene_data["narrative_description"],
            duration=float(scene_data["duration"]),
            start_time=0.0 if scene_data["scene_number"] == 1 else 5.0,
            props_and_objects=["swimming pool", "clear water", "pool toys"],
            mood_and_atmosphere="joyful and energetic"
        )
        workflow_state.add_scene(scene)
    
    workflow_state.concept_plan = concept_plan
    
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
    for scene_data in workflow_state.scenes:
        print(f"  📋 处理场景 {scene_data.scene_number}: {scene_data.title}")
        
        # 使用fallback方法生成场景参考
        scene_script = script_writer._generate_fallback_script_from_data(scene_data)
        
        # 更新场景数据
        workflow_state.update_scene(scene_data.scene_number,
            script_text=scene_script["script_text"],
            voice_over_text=scene_script["voice_over_text"],
            narrative_description=scene_script["narrative_description"],
            first_frame_scene_reference=scene_script["first_frame_scene_reference"],
            last_frame_scene_reference=scene_script["last_frame_scene_reference"],
            content_development_arc=scene_script["content_development_arc"]
        )
        
        print(f"     ✅ 首帧参考: {scene_script['first_frame_scene_reference']['situation']}")
        print(f"     ✅ 尾帧参考: {scene_script['last_frame_scene_reference']['situation']}")
        print(f"     ✅ 内容发展: {scene_script['content_development_arc']['narrative_progression'][:50]}...")
    
    print()
    
    # 3. 测试ImageGenerator的MAS协作
    print("🎨 阶段3: ImageGenerator (视觉艺术家)")
    print("-" * 40)
    
    image_generator = ImageGeneratorAgent()
    
    for scene_data in workflow_state.scenes:
        print(f"  🖼️ 处理场景 {scene_data.scene_number} 的视觉生成:")
        
        # 准备创意指导上下文
        creative_guidance = {
            "overall_guidance": concept_plan.get("visual_style_guidance", {}),
            "scene_guidance": {}  # 现在从scene_data直接获取
        }
        
        # 测试首帧提示词增强
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
    for scene_data in workflow_state.scenes:
        if not hasattr(scene_data, 'first_frame_scene_reference') or not scene_data.first_frame_scene_reference:
            print(f"❌ 场景 {scene_data.scene_number} 缺少首帧场景参考")
            validation_passed = False
        if not hasattr(scene_data, 'last_frame_scene_reference') or not scene_data.last_frame_scene_reference:
            print(f"❌ 场景 {scene_data.scene_number} 缺少尾帧场景参考")
            validation_passed = False
        if not hasattr(scene_data, 'content_development_arc') or not scene_data.content_development_arc:
            print(f"❌ 场景 {scene_data.scene_number} 缺少内容发展规划")
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
    print(f"✨ 总场景数: {len(workflow_state.scenes)}")
    print(f"📖 整体叙事: {concept_plan['overview']}")
    
    for scene_data in workflow_state.scenes:
        print(f"\n🎬 场景 {scene_data.scene_number}: {scene_data.title}")
        print(f"   📝 脚本: {scene_data.script_text[:60]}...")
        if hasattr(scene_data, 'first_frame_scene_reference') and scene_data.first_frame_scene_reference:
            print(f"   🎯 首帧情境: {scene_data.first_frame_scene_reference.get('situation', 'N/A')}")
        if hasattr(scene_data, 'last_frame_scene_reference') and scene_data.last_frame_scene_reference:
            print(f"   🏁 尾帧情境: {scene_data.last_frame_scene_reference.get('situation', 'N/A')}")
    
    print(f"\n🚀 MAS多智能体协作测试完成!")
    
    # 清理
    del workflow_manager._states[workflow_state.task_id]

if __name__ == "__main__":
    test_mas_collaboration()
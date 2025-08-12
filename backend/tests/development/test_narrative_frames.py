#!/usr/bin/env python3
"""
测试叙事驱动的首尾帧提示词生成
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.agents.image_generator import ImageGeneratorAgent
from app.core.workflow_state import SceneData

def test_narrative_frame_prompts():
    """测试叙事驱动的首尾帧提示词生成"""
    
    print("🧪 测试叙事驱动的首尾帧提示词生成")
    print("=" * 60)
    
    # 创建ImageGenerator实例
    image_gen = ImageGeneratorAgent()
    
    # 模拟场景数据
    scene_data = SceneData(
        scene_number=2,
        scene_type="main_content",
        title="Pool Fun Scene",
        description="Friends enjoying a pool party",
        narrative_description="This scene shows the core bonding moment where friends create lasting memories through playful water activities",
        visual_description="A group of friends splashing water in a beautiful pool setting",
        duration=8.0,
        start_time=5.0,
        character_descriptions=["enthusiastic friends", "joyful participants"],
        props_and_objects=["swimming pool", "clear water", "pool deck"],
        mood_and_atmosphere="joyful and carefree",
        camera_angle="wide shot",
        lighting_style="bright summer lighting",
        art_style="realistic",
        color_palette=["bright blue", "warm yellow", "vibrant green"]
    )
    
    # 模拟创意指导数据
    creative_guidance = {
        "overall_guidance": {
            "narrative_flow_strategy": {
                "mood_and_tone": "Progressive joy and connection",
                "pacing_strategy": "Building energy and excitement",
                "transition_philosophy": "Smooth emotional crescendo between scenes"
            }
        },
        "scene_guidance": {
            "creative_intent": "Showcase the peak moment of friendship and fun",
            "mood_target": "Pure joy and connection",
            "narrative_direction": "Emphasize the bonding aspect of shared experiences"
        }
    }
    
    base_prompt = "Friends in a swimming pool having fun together"
    
    print(f"📝 基础提示词: {base_prompt}")
    print(f"🎬 场景类型: {scene_data.scene_type}")
    print(f"📖 叙事描述: {scene_data.narrative_description}")
    print(f"🎯 创意意图: {creative_guidance['scene_guidance']['creative_intent']}")
    print(f"💭 情感目标: {creative_guidance['scene_guidance']['mood_target']}")
    print()
    
    # 测试首帧提示词
    print("🎬 首帧提示词生成:")
    print("-" * 40)
    first_frame_prompt = image_gen._enhance_prompt_for_first_frame(
        base_prompt, scene_data, creative_guidance
    )
    print(f"首帧: {first_frame_prompt}")
    print()
    
    # 测试尾帧提示词
    print("🎬 尾帧提示词生成:")
    print("-" * 40)
    last_frame_prompt = image_gen._enhance_prompt_for_last_frame(
        base_prompt, scene_data, creative_guidance
    )
    print(f"尾帧: {last_frame_prompt}")
    print()
    
    # 测试不同场景类型
    print("🎭 不同场景类型测试:")
    print("-" * 40)
    
    scene_types = ["intro", "main_content", "transition", "outro"]
    
    for scene_type in scene_types:
        print(f"\n📋 场景类型: {scene_type}")
        scene_data.scene_type = scene_type
        
        first_prompt = image_gen._enhance_prompt_for_first_frame(
            base_prompt, scene_data, creative_guidance
        )
        last_prompt = image_gen._enhance_prompt_for_last_frame(
            base_prompt, scene_data, creative_guidance
        )
        
        print(f"  首帧关键词: {first_prompt.split(', ')[-3:]}")  # 显示最后3个增强关键词
        print(f"  尾帧关键词: {last_prompt.split(', ')[-3:]}")   # 显示最后3个增强关键词

if __name__ == "__main__":
    test_narrative_frame_prompts()
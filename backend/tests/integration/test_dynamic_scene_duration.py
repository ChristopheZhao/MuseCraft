#!/usr/bin/env python3
"""
测试基于场景概念的动态时长设计
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.agents.utils import SceneDurationCalculator, SceneComplexity, ContentDensity

def test_dynamic_scene_duration():
    """测试动态场景时长计算"""
    
    print("🧪 测试基于场景概念的动态时长设计")
    print("=" * 60)
    
    # 测试场景1：简单场景
    print("\n📋 测试场景1：简单静态场景")
    print("-" * 40)
    
    simple_scene = {
        "scene_number": 1,
        "scene_type": "intro",
        "title": "Opening Shot",
        "description": "A peaceful morning scene",
        "visual_description": "Sunrise over a calm lake",
        "narrative_description": "Setting the peaceful mood",
        "characters": [],
        "props": ["lake", "sun"],
        "mood_target": "calm"
    }
    
    complexity = SceneDurationCalculator._analyze_scene_complexity(simple_scene)
    density = SceneDurationCalculator._analyze_content_density(simple_scene)
    duration = SceneDurationCalculator.calculate_scene_duration(simple_scene, 30, 5)
    
    print(f"🔍 场景分析:")
    print(f"   - 视觉复杂度: {complexity.value}")
    print(f"   - 内容密度: {density.value}")
    print(f"   - 计算时长: {duration:.1f}秒")
    print(f"   - 预期: 简单场景应该较短(2-4秒)")
    
    # 测试场景2：复杂动态场景
    print("\n📋 测试场景2：复杂动态场景")
    print("-" * 40)
    
    complex_scene = {
        "scene_number": 2,
        "scene_type": "main_content",
        "title": "Pool Party Fun",
        "description": "Friends having an exciting pool party",
        "visual_description": "Multiple friends jumping, splashing, playing water games, laughing and dancing by the pool",
        "narrative_description": "This is the emotional peak of the video where friendships are celebrated through joyful water activities. The scene captures the essence of summer fun and deep connections between friends.",
        "characters": ["friend1", "friend2", "friend3", "friend4", "friend5"],
        "props": ["pool", "water toys", "floats", "music speakers", "drinks", "decorations"],
        "mood_target": "extremely joyful and energetic",
        "emotional_tone": "intense happiness and excitement",
        "visual_priorities": ["water splashes", "laughing faces", "dynamic movements", "colorful atmosphere"]
    }
    
    complexity2 = SceneDurationCalculator._analyze_scene_complexity(complex_scene)
    density2 = SceneDurationCalculator._analyze_content_density(complex_scene)
    duration2 = SceneDurationCalculator.calculate_scene_duration(complex_scene, 30, 5)
    
    print(f"🔍 场景分析:")
    print(f"   - 视觉复杂度: {complexity2.value}")
    print(f"   - 内容密度: {density2.value}")
    print(f"   - 计算时长: {duration2:.1f}秒")
    print(f"   - 预期: 复杂场景应该较长(6-10秒)")
    
    # 测试场景3：过渡场景
    print("\n📋 测试场景3：简短过渡场景")
    print("-" * 40)
    
    transition_scene = {
        "scene_number": 3,
        "scene_type": "transition",
        "title": "Time Lapse",
        "description": "Sun moving across sky",
        "visual_description": "Time lapse of sun movement",
        "narrative_description": "Time passing",
        "characters": [],
        "props": ["sun", "clouds"],
        "mood_target": "transitional"
    }
    
    complexity3 = SceneDurationCalculator._analyze_scene_complexity(transition_scene)
    density3 = SceneDurationCalculator._analyze_content_density(transition_scene)
    duration3 = SceneDurationCalculator.calculate_scene_duration(transition_scene, 30, 5)
    
    print(f"🔍 场景分析:")
    print(f"   - 视觉复杂度: {complexity3.value}")
    print(f"   - 内容密度: {density3.value}")
    print(f"   - 计算时长: {duration3:.1f}秒")
    print(f"   - 预期: 过渡场景应该很短(2-3秒)")
    
    # 测试完整场景序列优化
    print("\n🎬 测试完整场景序列优化")
    print("-" * 40)
    
    all_scenes = [
        simple_scene,
        complex_scene,
        transition_scene,
        {
            "scene_number": 4,
            "scene_type": "climax",
            "title": "Group Jump",
            "description": "All friends jump into pool together",
            "visual_description": "Synchronized group jump creating huge splash",
            "narrative_description": "The ultimate moment of unity and joy",
            "characters": ["all friends"],
            "props": ["pool"],
            "mood_target": "peak excitement",
            "emotional_tone": "thrilling"
        },
        {
            "scene_number": 5,
            "scene_type": "outro",
            "title": "Sunset Reflection",
            "description": "Friends relaxing as sun sets",
            "visual_description": "Friends sitting by pool edge watching sunset",
            "narrative_description": "Peaceful conclusion reflecting on memories made",
            "characters": ["friends"],
            "props": ["pool", "sunset"],
            "mood_target": "warm and reflective"
        }
    ]
    
    total_duration = 30.0
    optimized_scenes = SceneDurationCalculator.optimize_scene_durations(
        all_scenes, total_duration
    )
    
    print(f"视频总时长: {total_duration}秒")
    print(f"场景数量: {len(optimized_scenes)}")
    print()
    
    total_calculated = 0
    for scene in optimized_scenes:
        print(f"场景 {scene['scene_number']}: {scene['title']}")
        print(f"   类型: {scene['scene_type']}")
        print(f"   建议时长: {scene['suggested_duration']:.1f}秒")
        print(f"   最终时长: {scene['final_duration']:.1f}秒")
        print(f"   理由: {scene.get('duration_reasoning', 'N/A')}")
        print()
        total_calculated += scene['final_duration']
    
    print(f"📊 时长分配总结:")
    print(f"   - 计算总时长: {total_calculated:.1f}秒")
    print(f"   - 目标总时长: {total_duration}秒")
    print(f"   - 差异: {abs(total_calculated - total_duration):.1f}秒")
    
    # 验证动态时长的优势
    print("\n✨ 动态时长设计的优势:")
    print("-" * 40)
    
    advantages = [
        "✅ 复杂场景自动获得更多展示时间",
        "✅ 简单过渡场景不会浪费时间", 
        "✅ 基于内容需求而非硬编码分配时长",
        "✅ 考虑情感强度和叙事需求",
        "✅ 自动平衡整体视频节奏",
        "✅ 适应不同类型的视频内容"
    ]
    
    for advantage in advantages:
        print(f"   {advantage}")
    
    print("\n🎊 动态场景时长测试完成!")
    
    # 验证是否符合预期
    if (duration < 4.0 and  # 简单场景较短
        duration2 > 6.0 and  # 复杂场景较长
        duration3 < 3.5 and  # 过渡场景很短
        abs(total_calculated - total_duration) < 2.0):  # 总时长接近目标
        print("🚀 所有测试通过，动态时长计算工作正常!")
    else:
        print("⚠️ 某些测试未达预期，需要调整参数")

if __name__ == "__main__":
    test_dynamic_scene_duration()
#!/usr/bin/env python3
"""
测试修复后的narrative_structure_generation_tool
"""
import sys
sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.core.workflow_state import SceneData
from app.agents.tools.ai_services.narrative_structure_generation_tool import NarrativeStructureGenerationTool

def test_scene_data_access():
    """测试SceneData对象访问修复"""
    
    print("🧪 Testing SceneData attribute access fix...")
    
    # 创建模拟的SceneData对象
    scene1 = SceneData(
        scene_number=1,
        title="开场场景", 
        description="视频的开头部分",
        duration=5.0
    )
    
    scene2 = SceneData(
        scene_number=2,
        title="发展场景",
        description="故事的发展部分", 
        duration=8.0
    )
    
    scenes = [scene1, scene2]
    concept_plan = {
        'overview': '测试概念计划',
        'visual_style': 'cinematic',
        'mood_and_tone': 'dramatic'
    }
    
    # 初始化工具
    tool = NarrativeStructureGenerationTool()
    
    try:
        # 测试构建提示词 - 这里应该不会再出错
        prompt = tool._build_narrative_structure_prompt(scenes, concept_plan)
        
        print("✅ SceneData对象属性访问成功!")
        print(f"✅ 生成的提示词长度: {len(prompt)}")
        print(f"✅ 场景信息正确提取:")
        print(f"   - 场景1: {scene1.title} ({scene1.duration}秒)")
        print(f"   - 场景2: {scene2.title} ({scene2.duration}秒)")
        
        # 检查提示词是否包含正确的场景信息
        if "开场场景" in prompt and "发展场景" in prompt:
            print("✅ 提示词包含正确的场景信息")
        else:
            print("❌ 提示词缺少场景信息")
            
        # 同时测试字典格式的向下兼容性
        print("\n🔄 测试字典格式向下兼容性...")
        dict_scenes = [
            {"title": "字典场景1", "description": "字典格式测试", "duration": 3.0},
            {"title": "字典场景2", "description": "兼容性测试", "duration": 4.0}
        ]
        
        dict_prompt = tool._build_narrative_structure_prompt(dict_scenes, concept_plan)
        
        if "字典场景1" in dict_prompt and "字典场景2" in dict_prompt:
            print("✅ 字典格式向下兼容性正常")
        else:
            print("❌ 字典格式兼容性有问题")
            
        print(f"\n✅ narrative_structure_generation_tool修复成功！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_scene_data_access()
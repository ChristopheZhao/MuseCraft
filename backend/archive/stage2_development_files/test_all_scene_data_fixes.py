#!/usr/bin/env python3
"""
测试所有SceneData对象属性访问修复
"""
import sys
sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.core.workflow_state import SceneData
from app.agents.tools.ai_services.narrative_structure_generation_tool import NarrativeStructureGenerationTool
from app.agents.tools.ai_services.script_generation_tool import ScriptGenerationTool

def test_all_scene_data_fixes():
    """测试所有工具的SceneData修复"""
    
    print("🧪 Testing All SceneData Object Fixes...")
    
    # 创建测试数据
    scene1 = SceneData(
        scene_number=1,
        title="测试场景1", 
        description="第一个测试场景",
        duration=5.0
    )
    
    scene2 = SceneData(
        scene_number=2,
        title="测试场景2",
        description="第二个测试场景", 
        duration=8.0
    )
    
    scenes = [scene1, scene2]
    concept_plan = {
        'overview': '测试概念计划',
        'visual_style': 'cinematic',
        'mood_and_tone': 'dramatic'
    }
    
    print("\n🔧 测试 NarrativeStructureGenerationTool...")
    try:
        narrative_tool = NarrativeStructureGenerationTool()
        narrative_prompt = narrative_tool._build_narrative_structure_prompt(scenes, concept_plan)
        
        if "测试场景1" in narrative_prompt and "测试场景2" in narrative_prompt:
            print("✅ NarrativeStructureGenerationTool 修复成功")
        else:
            print("❌ NarrativeStructureGenerationTool 仍有问题")
            
    except Exception as e:
        print(f"❌ NarrativeStructureGenerationTool 测试失败: {e}")
    
    print("\n🔧 测试 ScriptGenerationTool...")
    try:
        script_tool = ScriptGenerationTool()
        
        # 测试 _get_scene_attribute 方法
        title = script_tool._get_scene_attribute(scene1, 'title')
        duration = script_tool._get_scene_attribute(scene1, 'duration')
        
        if title == "测试场景1" and duration == 5.0:
            print("✅ ScriptGenerationTool._get_scene_attribute 工作正常")
        else:
            print(f"❌ ScriptGenerationTool._get_scene_attribute 有问题: title={title}, duration={duration}")
        
        # 测试字典兼容性
        dict_scene = {"title": "字典场景", "duration": 3.0, "scene_number": 3}
        dict_title = script_tool._get_scene_attribute(dict_scene, 'title')
        dict_duration = script_tool._get_scene_attribute(dict_scene, 'duration')
        
        if dict_title == "字典场景" and dict_duration == 3.0:
            print("✅ ScriptGenerationTool 字典兼容性正常")
        else:
            print(f"❌ ScriptGenerationTool 字典兼容性有问题: title={dict_title}, duration={dict_duration}")
            
    except Exception as e:
        print(f"❌ ScriptGenerationTool 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ 所有SceneData对象属性访问修复测试完成！")

if __name__ == "__main__":
    test_all_scene_data_fixes()
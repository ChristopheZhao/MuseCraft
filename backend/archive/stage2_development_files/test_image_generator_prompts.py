#!/usr/bin/env python3
"""
测试ImageGenerator的提示词系统
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_image_generator_prompt_templates():
    """测试ImageGenerator的提示词模板"""
    
    print("🔧 测试ImageGenerator提示词模板系统...")
    
    try:
        from app.core.prompt_manager import get_prompt_manager
        
        # 获取PromptManager实例
        manager = get_prompt_manager()
        
        # 测试image_generator配置是否加载
        configs = manager.list_configs()
        print(f"✅ 已加载配置: {configs}")
        
        if 'image_generator' not in configs:
            print("❌ image_generator配置未加载")
            return False
        
        # 测试基础模板渲染
        test_templates = [
            "professional_image_prompt_generation",
            "frame_generation_prompt", 
            "complete_frame_analysis",
            "prompt_integration",
            "image_generation_prompt"
        ]
        
        for template_name in test_templates:
            try:
                result = manager.render_template(
                    config_name="image_generator",
                    template_name=template_name,
                    variables={
                        "frame_specific_instruction": "测试指令",
                        "base_prompt": "测试基础提示词",
                        "scene_number": 1,
                        "scene_title": "测试场景",
                        "scene_duration": 10,
                        "scene_description": "测试场景描述",
                        "frame_type": "first",
                        "base_description": "测试描述",
                        "visual_style": "专业风格",
                        "mood_and_atmosphere": "专业氛围",
                        "camera_angle": "中景",
                        "lighting_style": "自然光",
                        "color_palette": ["暖色调"],
                        "creative_guidance": "测试指导",
                        "scene_physics_constraints": "strict",
                        # 其他所需变量
                        "mood_and_atmosphere": "专业",
                        "camera_angle": "中景",
                        "props_and_objects": ["道具1"],
                        "character_descriptions": ["角色1"],
                        "visual_description": "视觉描述",
                        "overall_concept": "整体概念",
                        "visual_style_requirements": "风格要求",
                        "target_mood": "目标情绪",
                        "core_description": "核心描述",
                        "detailed_objects": ["物体1"],
                        "detailed_characters": ["角色1"],
                        "detailed_environment": "环境描述",
                        "composition_layout": "构图布局",
                        "lighting_and_mood": "光影氛围",
                        "scene_mood": "场景氛围",
                        "art_style": "艺术风格"
                    },
                    use_cache=False
                )
                
                if result and len(result) > 50:  # 基本长度检查
                    print(f"✅ {template_name}: {len(result)}字符")
                else:
                    print(f"⚠️ {template_name}: 渲染结果太短 ({len(result) if result else 0}字符)")
                    
            except Exception as e:
                print(f"❌ {template_name}: 渲染失败 - {e}")
        
        print("\n🎉 ImageGenerator提示词模板系统测试完成!")
        return True
        
    except Exception as e:
        print(f"❌ ImageGenerator测试失败: {e}")
        return False

if __name__ == "__main__":
    success = test_image_generator_prompt_templates()
    sys.exit(0 if success else 1)
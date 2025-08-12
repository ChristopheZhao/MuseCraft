#!/usr/bin/env python3
"""
测试ConceptPlanner增强的整体构思输出
"""

import sys
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.agents.concept_planner import ConceptPlannerAgent

def test_concept_planner_enhanced_output():
    """测试ConceptPlanner增强的MAS协作指导输出"""
    
    print("🧪 测试ConceptPlanner增强整体构思")
    print("=" * 60)
    
    # 创建ConceptPlanner实例
    concept_planner = ConceptPlannerAgent()
    
    print("✅ ConceptPlanner初始化成功")
    print(f"   - Agent类型: {concept_planner.agent_type}")
    print(f"   - Agent名称: {concept_planner.agent_name}")
    print()
    
    # 测试增强的提示词构建
    print("🎭 测试增强的创意指导提示词:")
    print("-" * 40)
    
    user_prompt = "创建一个展示朋友间深厚友谊的温馨短视频"
    video_style = "温馨感人"
    duration = 20
    aspect_ratio = "16:9"
    
    enhanced_prompt = concept_planner._build_concept_prompt(
        user_prompt, video_style, duration, aspect_ratio
    )
    
    print(f"📝 用户需求: {user_prompt}")
    print(f"🎨 视频风格: {video_style}")
    print(f"⏱️ 时长: {duration}s")
    print(f"📐 比例: {aspect_ratio}")
    print()
    
    # 检查增强的结构元素
    print("🔍 检查增强的提示词结构:")
    print("-" * 40)
    
    enhanced_elements = [
        ("visual_style_guidance", "视觉风格指导"),
        ("composition_philosophy", "构图哲学"), 
        ("visual_hierarchy", "视觉层级"),
        ("brand_alignment", "品牌对齐"),
        ("narrative_flow_strategy", "叙事流策略"),
        ("story_arc_design", "故事弧设计"),
        ("emotional_beats", "情感节拍"),
        ("audience_engagement_strategy", "观众参与策略"),
        ("agent_collaboration_guidance", "智能体协作指导"),
        ("script_writer_guidance", "脚本编剧指导"),
        ("visual_artist_guidance", "视觉艺术家指导"),
        ("motion_director_guidance", "动作导演指导"),
        ("workflow_optimization", "工作流优化"),
        ("review_criteria", "审查标准")
    ]
    
    found_elements = []
    missing_elements = []
    
    for element, description in enhanced_elements:
        if element in enhanced_prompt:
            found_elements.append(f"✅ {description} ({element})")
        else:
            missing_elements.append(f"❌ {description} ({element})")
    
    print("增强元素检查结果:")
    for element in found_elements:
        print(f"   {element}")
    
    if missing_elements:
        print("\n缺失元素:")
        for element in missing_elements:
            print(f"   {element}")
    
    print()
    
    # 检查MAS协作指导
    print("🤖 MAS协作指导检查:")  
    print("-" * 40)
    
    mas_indicators = [
        "Script Writer will use your narrative guidance",
        "Visual Artist will interpret your visual guidance", 
        "Motion Director will follow your movement philosophy",
        "autonomous specialists to collaborate effectively",
        "Multi-Agent Collaboration",
        "agent_collaboration_guidance"
    ]
    
    mas_found = []
    for indicator in mas_indicators:
        if indicator in enhanced_prompt:
            mas_found.append(f"✅ {indicator}")
        else:
            mas_found.append(f"❌ {indicator}")
    
    for indicator in mas_found:
        print(f"   {indicator}")
    
    print()
    
    # 模拟解析测试（测试JSON结构完整性）
    print("📋 JSON结构完整性测试:")
    print("-" * 40)
    
    # 提取JSON模板部分
    json_start = enhanced_prompt.find('{')
    json_end = enhanced_prompt.rfind('}') + 1
    
    if json_start != -1 and json_end != -1:
        json_template = enhanced_prompt[json_start:json_end]
        
        # 计算嵌套结构
        open_braces = json_template.count('{{')
        close_braces = json_template.count('}}')
        
        print(f"✅ JSON模板提取成功")
        print(f"   - 模板长度: {len(json_template)} 字符")
        print(f"   - 开放花括号: {open_braces}")
        print(f"   - 关闭花括号: {close_braces}")
        print(f"   - 结构平衡: {'✅ 平衡' if open_braces == close_braces else '❌ 不平衡'}")
        
        # 检查关键字段
        required_fields = [
            "overview", "target_audience", "key_messages",
            "visual_style_guidance", "narrative_flow_strategy", "scenes",
            "agent_collaboration_guidance", "production_guidance"
        ]
        
        field_check = []
        for field in required_fields:
            if f'"{field}"' in json_template:
                field_check.append(f"✅ {field}")
            else:
                field_check.append(f"❌ {field}")
        
        print(f"\n   关键字段检查:")
        for field in field_check:
            print(f"     {field}")
    else:
        print("❌ JSON模板提取失败")
    
    print()
    
    # 验证增强效果
    print("🎯 增强效果验证:")
    print("-" * 40)
    
    improvements = []
    
    # 检查是否有详细的MAS指导
    if "agent_collaboration_guidance" in enhanced_prompt:
        improvements.append("✅ 增加了详细的多智能体协作指导")
    else:
        improvements.append("❌ 缺少多智能体协作指导")
    
    # 检查是否有增强的视觉指导
    if "composition_philosophy" in enhanced_prompt and "visual_hierarchy" in enhanced_prompt:
        improvements.append("✅ 增强了视觉风格指导的深度")
    else:
        improvements.append("❌ 视觉指导未充分增强")
    
    # 检查是否有详细的叙事策略
    if "story_arc_design" in enhanced_prompt and "emotional_beats" in enhanced_prompt:
        improvements.append("✅ 增强了叙事流策略的细节")
    else:
        improvements.append("❌ 叙事策略未充分增强")
    
    # 检查工作流优化
    if "workflow_optimization" in enhanced_prompt and "review_criteria" in enhanced_prompt:
        improvements.append("✅ 添加了工作流和质量管理指导")
    else:
        improvements.append("❌ 缺少工作流优化指导")
    
    for improvement in improvements:
        print(f"   {improvement}")
    
    print()
    
    # 整体评估
    all_good = all("✅" in improvement for improvement in improvements)
    mas_coverage = len([x for x in mas_found if "✅" in x]) / len(mas_found)
    
    print("🏆 整体评估:")
    print("-" * 40)
    print(f"   📊 MAS协作覆盖率: {mas_coverage:.1%}")
    print(f"   🎯 增强完成度: {'🚀 完全成功' if all_good else '⚠️ 需要调整'}")
    print(f"   📈 结构完整性: {'✅ 完整' if json_start != -1 else '❌ 不完整'}")
    
    if all_good and mas_coverage > 0.8:
        print("\n🎊 ConceptPlanner增强测试完全成功!")
        print("   - 提供了详细的创意指导")
        print("   - 支持完整的MAS协作")
        print("   - 结构化的智能体指导")
        print("   - 优化的工作流管理")
    else:
        print("\n⚠️ ConceptPlanner增强需要进一步完善")

if __name__ == "__main__":
    test_concept_planner_enhanced_output()
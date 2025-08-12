#!/usr/bin/env python3
"""
正确的MAS协作设计 - ImageGenerator应该如何与其他Agent协作
"""

def correct_enhance_prompt_for_first_frame(base_prompt: str, scene_data, creative_guidance: dict) -> str:
    """
    正确的MAS协作模式 - ImageGenerator根据其他Agent的设计来执行任务
    
    职责分工：
    - ConceptPlanner: 整体构思和叙事策略
    - ScriptWriter: 具体场景设计和事件规划  
    - ImageGenerator: 根据既定设计生成视觉内容
    """
    
    # 从创意记忆中获取ConceptPlanner的整体构思
    overall_guidance = creative_guidance.get("overall_guidance", {})
    scene_guidance = creative_guidance.get("scene_guidance", {})
    
    enhancements = []
    
    # 1. 遵循ConceptPlanner的整体叙事策略
    narrative_flow = overall_guidance.get("narrative_flow_strategy", {})
    if narrative_flow:
        mood_tone = narrative_flow.get("mood_and_tone", "")
        if mood_tone:
            enhancements.append(f"narrative mood: {mood_tone} - opening phase")
            
        pacing_strategy = narrative_flow.get("pacing_strategy", "")
        if pacing_strategy:
            enhancements.append(f"pacing approach: {pacing_strategy} - scene start")
    
    # 2. 按照ScriptWriter对当前场景的具体规划
    # 场景的叙事功能（由ConceptPlanner定义）
    narrative_description = getattr(scene_data, 'narrative_description', '')
    if narrative_description:
        enhancements.append(f"scene narrative function: {narrative_description} - initial moment")
    
    # 3. 执行ScriptWriter定义的创意意图
    creative_intent = scene_guidance.get("creative_intent", "")
    if creative_intent:
        enhancements.append(f"creative direction: {creative_intent} - opening state")
    
    # 4. 实现ScriptWriter规划的情感目标
    mood_target = scene_guidance.get("mood_target", "")
    if mood_target:
        enhancements.append(f"emotional target: {mood_target} - building phase")
    
    # 5. 应用ScriptWriter的视觉指导
    visual_direction = scene_guidance.get("visual_direction", "")
    if visual_direction:
        enhancements.append(f"visual guidance: {visual_direction} - first frame")
    
    # 6. 遵循ConceptPlanner的视觉一致性要求
    visual_style_guidance = overall_guidance.get("visual_style_guidance", {})
    if visual_style_guidance:
        visual_consistency = visual_style_guidance.get("visual_consistency_notes", "")
        if visual_consistency:
            enhancements.append(f"visual consistency: {visual_consistency}")
    
    # 7. ImageGenerator的专业技能 - 视觉构图
    enhancements.extend([
        "establishing composition",
        "clear scene opening",
        "visual narrative setup"
    ])
    
    return f"{base_prompt}, {', '.join(enhancements)}"


def correct_enhance_prompt_for_last_frame(base_prompt: str, scene_data, creative_guidance: dict) -> str:
    """
    正确的MAS协作模式 - 尾帧设计基于其他Agent的规划
    """
    
    overall_guidance = creative_guidance.get("overall_guidance", {})
    scene_guidance = creative_guidance.get("scene_guidance", {})
    
    enhancements = []
    
    # 1. 遵循ConceptPlanner的叙事完成策略
    narrative_flow = overall_guidance.get("narrative_flow_strategy", {})
    if narrative_flow:
        mood_tone = narrative_flow.get("mood_and_tone", "")
        if mood_tone:
            enhancements.append(f"narrative mood: {mood_tone} - completion phase")
            
        transition_philosophy = narrative_flow.get("transition_philosophy", "")
        if transition_philosophy:
            enhancements.append(f"transition approach: {transition_philosophy}")
    
    # 2. 完成ScriptWriter定义的场景功能
    narrative_description = getattr(scene_data, 'narrative_description', '')
    if narrative_description:
        enhancements.append(f"scene narrative function: {narrative_description} - completion moment")
    
    # 3. 实现ScriptWriter的创意意图完成状态
    creative_intent = scene_guidance.get("creative_intent", "")
    if creative_intent:
        enhancements.append(f"creative direction: {creative_intent} - achieved state")
    
    # 4. 达成ScriptWriter的情感目标
    mood_target = scene_guidance.get("mood_target", "")
    if mood_target:
        enhancements.append(f"emotional target: {mood_target} - realized")
    
    # 5. 应用ScriptWriter的视觉指导完成版
    visual_direction = scene_guidance.get("visual_direction", "")
    if visual_direction:
        enhancements.append(f"visual guidance: {visual_direction} - final frame")
    
    # 6. 保持ConceptPlanner要求的视觉一致性
    visual_style_guidance = overall_guidance.get("visual_style_guidance", {})
    if visual_style_guidance:
        visual_consistency = visual_style_guidance.get("visual_consistency_notes", "")
        if visual_consistency:
            enhancements.append(f"visual consistency: {visual_consistency}")
    
    # 7. ImageGenerator的专业技能 - 完成构图
    enhancements.extend([
        "scene completion composition",
        "narrative closure visual",
        "smooth transition setup"
    ])
    
    return f"{base_prompt}, {', '.join(enhancements)}"


def demonstrate_mas_collaboration():
    """
    演示正确的MAS协作流程
    """
    
    print("🏗️ 正确的MAS协作架构")
    print("=" * 60)
    
    print("\n1. ConceptPlanner 的职责:")
    print("   - 整体故事构思")
    print("   - 叙事流动策略")
    print("   - 视觉一致性规划")
    
    print("\n2. ScriptWriter 的职责:")
    print("   - 具体场景设计")
    print("   - 创意意图定义")
    print("   - 视觉指导方向")
    
    print("\n3. ImageGenerator 的职责:")
    print("   - 接收上游Agent的设计")
    print("   - 按照既定规划生成图片")
    print("   - 应用专业的视觉构图技能")
    
    print("\n❌ 错误做法:")
    print("   - ImageGenerator自己分析场景内容")
    print("   - ImageGenerator自己推断事件类型")
    print("   - ImageGenerator重复其他Agent的工作")
    
    print("\n✅ 正确做法:")
    print("   - ImageGenerator严格按照记忆中的设计执行")
    print("   - ImageGenerator专注于视觉实现技能")
    print("   - ImageGenerator与其他Agent真正协作")
    
    print("\n🔄 信息流:")
    print("   用户输入 → ConceptPlanner → ScriptWriter → ImageGenerator")
    print("              ↓             ↓             ↓")
    print("           整体构思       场景脚本      视觉实现")


if __name__ == "__main__":
    demonstrate_mas_collaboration()
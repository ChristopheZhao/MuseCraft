#!/usr/bin/env python3
"""
测试场景连续性分析完整流程
"""
import asyncio
import json
import os
import sys

# 添加项目路径
sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.agents.image_generator import ImageGeneratorAgent

async def test_scene_continuity_analysis():
    """测试场景连续性分析"""
    
    print("🧪 Testing Scene Continuity Analysis...")
    
    # 初始化 ImageGenerator 并设置工具
    from app.agents.tools.tool_registry import ToolRegistry
    
    agent = ImageGeneratorAgent()
    tool_registry = ToolRegistry()
    agent.tool_registry = tool_registry
    
    # 模拟场景数据
    class MockScene:
        def __init__(self, scene_number, title, description):
            self.scene_number = scene_number
            self.title = title
            self.description = description
            self.narrative_description = f"{title} - {description}"
            self.initial_state_description = f"初始状态：{title}"
            self.target_outcome_description = f"结果状态：{description}"
    
    # 模拟前一场景和当前场景
    previous_scene = MockScene(
        scene_number=3,
        title="金丹稳定",
        description="修士盘坐，金丹在丹田中稳定运转，元婴即将成形但尚未完全显现"
    )
    
    current_scene = MockScene(
        scene_number=4, 
        title="元婴显现",
        description="金丹破碎，元婴完全显现，修士突破到元婴境界"
    )
    
    # 模拟概念计划
    concept_plan = {
        "overview": "修仙突破的故事，展现从金丹到元婴的关键时刻",
        "scenes": [
            {"scene_number": 3, "description": "金丹稳定"},
            {"scene_number": 4, "description": "元婴显现"}
        ]
    }
    
    try:
        print(f"🔄 分析场景连续性: Scene {previous_scene.scene_number} -> Scene {current_scene.scene_number}")
        
        # 创建模拟的workflow state
        class MockWorkflowState:
            def __init__(self):
                self.user_prompt = "创造一个修仙突破的视频"
                self.video_style = "cinematic"
                self.duration = 30
        
        # 模拟 workflow manager
        from app.core.workflow_state import workflow_manager
        mock_workflow = MockWorkflowState()
        workflow_manager._workflows["test_workflow_123"] = mock_workflow
        
        # 调用场景连续性分析
        analysis_result = await agent._analyze_scene_continuity_with_llm(
            current_scene=current_scene,
            previous_scene=previous_scene,
            concept_plan=concept_plan,
            workflow_state_id="test_workflow_123"
        )
        
        print(f"✅ 分析结果:")
        print(f"   策略: {analysis_result['strategy']}")
        print(f"   推理: {analysis_result['reasoning']}")
        print(f"   置信度: {analysis_result['confidence_score']}")
        
        if 'analysis_dimensions' in analysis_result:
            print(f"   分析维度: {analysis_result['analysis_dimensions']}")
        
        # 验证结果合理性
        expected_strategy = "continue_from_previous"  # 金丹到元婴应该是连续过程
        if analysis_result['strategy'] == expected_strategy:
            print(f"✅ 策略合理: 选择了 {expected_strategy}")
        else:
            print(f"⚠️  策略意外: 期望 {expected_strategy}, 得到 {analysis_result['strategy']}")
        
        # 测试新图像策略的情况
        print(f"\n🔄 测试不连续场景...")
        
        discontinuous_scene = MockScene(
            scene_number=5,
            title="新的场景",
            description="完全不同的地点和角色，与前面场景无关"
        )
        
        analysis_result_2 = await agent._analyze_scene_continuity_with_llm(
            current_scene=discontinuous_scene,
            previous_scene=current_scene,
            concept_plan=concept_plan,
            workflow_state_id="test_workflow_123"
        )
        
        print(f"✅ 不连续场景分析结果:")
        print(f"   策略: {analysis_result_2['strategy']}")
        print(f"   推理: {analysis_result_2['reasoning']}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_scene_continuity_analysis())
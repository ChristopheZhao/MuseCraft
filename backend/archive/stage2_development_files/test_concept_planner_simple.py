#!/usr/bin/env python3
"""
简单测试新的ConceptPlannerAgent
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# 确保工具注册
from app.agents.tools import register_default_tools
register_default_tools()

from app.agents.concept_planner import ConceptPlannerAgent
from app.core.workflow_state import WorkflowState, workflow_manager
from app.models import Task, AgentExecution, TaskStatus

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_concept_planner_integration():
    """测试ConceptPlanner的实际集成"""
    print("\n🧠 测试新ConceptPlannerAgent实际集成...")
    
    agent = ConceptPlannerAgent()
    print(f"✅ ConceptPlanner工具: {agent.get_tool_names()}")
    
    # 创建测试数据
    test_prompt = "修仙小说，男主角突破元婴境界的场景"
    
    try:
        # 创建工作流
        workflow_state = workflow_manager.create_workflow(
            test_prompt, "cinematic", 30, "16:9"
        )
        workflow_state_id = workflow_state.task_id
        print(f"✅ 创建工作流: {workflow_state_id}")
        
        # 模拟输入数据
        input_data = {
            "user_prompt": test_prompt,
            "video_style": "cinematic", 
            "duration": 30,
            "aspect_ratio": "16:9",
            "workflow_state_id": workflow_state_id
        }
        
        # 模拟task和execution
        class MockTask:
            def __init__(self):
                self.id = 1
                self.task_id = "test_task"
        
        class MockExecution:
            def __init__(self):
                self.id = 1
                self.retry_count = 0
                self.max_retries = 3
                self.tokens_used = 0
            
            def update_progress(self, percentage, substep):
                print(f"  📈 Progress: {percentage}% - {substep}")
            
            def update_token_usage(self, tokens):
                self.tokens_used += tokens
                print(f"  🔢 Token usage: +{tokens} (total: {self.tokens_used})")
        
        class MockDB:
            def add(self, obj): pass
            def commit(self): pass  
            def refresh(self, obj): pass
        
        task = MockTask()
        execution = MockExecution()
        db = MockDB()
        
        # 执行概念规划
        print("🚀 开始执行概念规划...")
        result = await agent._execute_impl(task, input_data, execution, db)
        
        print("✅ 概念规划执行成功！")
        print(f"📊 结果总结:")
        print(f"  - 总场景数: {result.get('total_scenes', 0)}")
        print(f"  - 规划方式: {result.get('planning_approach', 'unknown')}")
        print(f"  - LLM驱动: {result.get('llm_driven', False)}")
        print(f"  - 视频风格: {result.get('video_style', 'unknown')}")
        
        # 显示场景详情
        scenes = result.get('scenes', [])
        print(f"\n📝 场景详情:")
        for i, scene in enumerate(scenes[:3]):
            script = scene.get('script_text', '')[:30]
            duration = scene.get('duration', 0)
            scene_type = scene.get('scene_type', 'unknown')
            print(f"  场景{i+1}: {duration}秒 [{scene_type}] - {script}...")
        
        if len(scenes) > 3:
            print(f"  ... 还有{len(scenes)-3}个场景")
        
        # 验证workflow_state是否更新
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if workflow_state and workflow_state.scenes:
            scene_count = len(workflow_state.scenes)
            print(f"✅ WorkflowState更新成功，存储了{scene_count}个场景")
        else:
            print("⚠️ WorkflowState未正确更新")
        
        return {
            "success": True,
            "total_scenes": result.get('total_scenes', 0),
            "planning_approach": result.get('planning_approach', 'unknown'),
            "llm_driven": result.get('llm_driven', False)
        }
        
    except Exception as e:
        print(f"❌ 概念规划失败: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

async def main():
    """主测试函数"""
    print("🚀 ConceptPlannerAgent集成测试\n")
    
    result = await test_concept_planner_integration()
    
    print(f"\n{'='*60}")
    print("📊 测试总结")
    print('='*60)
    
    if result.get("success"):
        print("🎉 ConceptPlannerAgent集成测试成功！")
        print(f"  - 场景规划: ✅ {result.get('total_scenes', 0)}个场景")
        print(f"  - LLM驱动: ✅ {result.get('llm_driven', False)}")
        print(f"  - 规划方式: ✅ {result.get('planning_approach', 'unknown')}")
        print("\n🎯 结论: 新的Function Call版本ConceptPlannerAgent工作正常！")
    else:
        print("❌ ConceptPlannerAgent集成测试失败")
        print(f"  错误: {result.get('error', 'Unknown error')}")
        print("\n⚠️ 需要进一步调试和修复")

if __name__ == "__main__":
    asyncio.run(main())
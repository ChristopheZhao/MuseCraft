#!/usr/bin/env python3
"""
测试API工作流程是否可以正常启动 - MAS智能风格决策适配验证
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

async def test_workflow_creation():
    """测试WorkflowState创建是否正常工作"""
    print("🏗️ 测试WorkflowState创建...")
    
    try:
        from app.core.workflow_state import workflow_manager
        
        # 测试新的智能风格决策接口
        workflow = workflow_manager.create_workflow(
            user_prompt="制作一个关于人工智能的短视频",
            style_preference="希望有科技感和专业性",
            duration=30
        )
        
        print(f"   ✅ WorkflowState创建成功")
        print(f"   任务ID: {workflow.task_id}")
        print(f"   用户需求: {workflow.user_prompt}")
        print(f"   风格偏好: {workflow.style_preference}")
        print(f"   智能风格设计: {workflow.intelligent_style_design}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ WorkflowState创建失败: {e}")
        return False

async def test_concept_planner_tools():
    """测试ConceptPlannerAgent工具访问"""
    print("\n🎭 测试ConceptPlannerAgent工具访问...")
    
    try:
        from app.agents.concept_planner import ConceptPlannerAgent
        
        agent = ConceptPlannerAgent()
        
        # 检查可用工具
        available_tools = agent.get_available_tools()
        tool_names = [tool.metadata.name for tool in available_tools]
        
        print(f"   可用工具: {tool_names}")
        
        if "concept_generation_tool" in tool_names:
            print("   ✅ ConceptPlannerAgent可以访问concept_generation_tool")
            return True
        else:
            print("   ❌ ConceptPlannerAgent无法访问concept_generation_tool")
            return False
            
    except Exception as e:
        print(f"   ❌ ConceptPlannerAgent测试失败: {e}")
        return False

async def test_api_request_format():
    """测试API请求格式"""
    print("\n🌐 测试API请求格式...")
    
    try:
        from app.api.v1.endpoints.tasks import TaskCreateRequest
        
        # 测试新的请求格式
        test_request = TaskCreateRequest(
            user_prompt="制作一个展示春天花园的视频",
            style_preference="希望温馨自然一些",
            duration=30
        )
        
        print(f"   ✅ 新API请求格式验证成功")
        print(f"   用户需求: {test_request.user_prompt}")
        print(f"   风格偏好: {test_request.style_preference}")
        print(f"   时长: {test_request.duration}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ API请求格式测试失败: {e}")
        return False

async def main():
    """运行API工作流程测试"""
    print("🚀 MAS智能风格决策 - API工作流程测试\n")
    
    tests = [
        test_workflow_creation,
        test_concept_planner_tools,
        test_api_request_format
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"   ❌ 测试执行异常: {e}")
            results.append(False)
    
    # 汇总结果
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 API工作流程测试结果: {passed}/{total}")
    
    if passed == total:
        print("✅ API工作流程适配完成！MAS测试可以正常启动")
    elif passed >= 2:
        print("⚠️ 大部分适配完成，应该可以进行基本的MAS测试")
    else:
        print("❌ 多项适配失败，需要进一步修复")
    
    print("\n🎯 关键适配验证:")
    print("1. WorkflowState支持intelligent_style_design字段")
    print("2. API接口移除硬编码video_style参数")
    print("3. ConceptPlannerAgent可以使用ConceptGenerationTool")
    print("4. 用户原始需求和智能风格设计都得到保留")

if __name__ == "__main__":
    asyncio.run(main())
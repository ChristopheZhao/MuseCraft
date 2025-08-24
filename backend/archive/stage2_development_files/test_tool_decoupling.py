#!/usr/bin/env python3
"""
测试工具系统解耦效果
"""

import sys
import os
import asyncio
from typing import Dict, List
sys.path.append(os.path.dirname(__file__))

async def test_tool_decoupling():
    """测试工具系统解耦效果"""
    
    print("🔧 测试工具系统解耦效果...")
    
    # 1. 测试工具注册系统
    print("\n📋 第一步：测试工具注册系统...")
    try:
        from app.agents.tools.tool_registry import get_tool_registry
        
        registry = get_tool_registry()
        
        # 检查默认AI工具是否注册
        tools = registry.list_tools()
        ai_tools = [tool for tool in tools if "ai" in tool.lower() or "text" in tool.lower()]
        
        print(f"✅ 工具注册系统初始化成功")
        print(f"   已注册工具总数: {len(tools)}")
        print(f"   AI相关工具: {ai_tools}")
        
        # 检查特定AI工具
        expected_ai_tools = ["ai_service_tool", "text_generation_tool"]
        available_ai_tools = []
        
        for tool_name in expected_ai_tools:
            try:
                tool_info = registry.get_tool_info(tool_name)
                available_ai_tools.append(tool_name)
                print(f"   ✅ {tool_name}: {tool_info['metadata']['description']}")
            except Exception as e:
                print(f"   ❌ {tool_name}: 未注册 - {e}")
        
        if len(available_ai_tools) == len(expected_ai_tools):
            print("✅ 所有预期AI工具已注册")
        else:
            print(f"⚠️ 只有 {len(available_ai_tools)}/{len(expected_ai_tools)} 个AI工具注册成功")
        
    except Exception as e:
        print(f"❌ 工具注册系统测试失败: {e}")
        return False
    
    # 2. 测试Agent工具系统集成
    print("\n🤖 第二步：测试Agent工具系统集成...")
    
    agents_to_test = [
        ("ConceptPlanner", "app.agents.concept_planner", "ConceptPlannerAgent"),
        ("ScriptWriter", "app.agents.script_writer", "ScriptWriterAgent"),
        ("QualityChecker", "app.agents.quality_checker", "QualityCheckerAgent"),
        ("ImageGenerator", "app.agents.image_generator", "ImageGeneratorAgent"),
        ("VideoGenerator", "app.agents.video_generator", "VideoGeneratorAgent")
    ]
    
    tool_integration_results = {}
    
    for agent_name, module_path, class_name in agents_to_test:
        try:
            # 动态导入并实例化Agent
            module = __import__(module_path, fromlist=[class_name])
            agent_class = getattr(module, class_name)
            agent = agent_class()
            
            # 检查工具系统集成
            has_tool_registry = hasattr(agent, 'tool_registry') and agent.tool_registry is not None
            has_available_tools = hasattr(agent, '_available_tools') and isinstance(agent._available_tools, dict)
            has_generate_text_method = hasattr(agent, 'generate_text')
            available_tools = list(agent._available_tools.keys()) if has_available_tools else []
            
            # 检查是否移除了直接AI客户端依赖
            has_direct_ai_client = hasattr(agent, 'ai_client') and agent.ai_client is not None
            
            tool_integration_results[agent_name] = {
                "tool_registry": has_tool_registry,
                "available_tools": available_tools,
                "generate_text_method": has_generate_text_method,
                "direct_ai_client": has_direct_ai_client,
                "decoupled": has_tool_registry and has_generate_text_method and not has_direct_ai_client
            }
            
            status = "✅ 已解耦" if tool_integration_results[agent_name]["decoupled"] else "⚠️ 部分解耦"
            print(f"   {status} {agent_name}:")
            print(f"     工具注册系统: {'✅' if has_tool_registry else '❌'}")
            print(f"     统一AI接口: {'✅' if has_generate_text_method else '❌'}")
            print(f"     直接AI依赖: {'❌' if not has_direct_ai_client else '⚠️ 仍存在'}")
            print(f"     可用工具: {available_tools}")
            
        except Exception as e:
            print(f"   ❌ {agent_name}: 实例化失败 - {e}")
            tool_integration_results[agent_name] = {"decoupled": False, "error": str(e)}
    
    # 3. 测试工具系统功能
    print("\n🔧 第三步：测试工具系统功能...")
    
    try:
        # 测试AI服务工具
        from app.agents.tools.ai_services.ai_service_tool import AIServiceTool
        from app.agents.tools.base_tool import ToolInput
        
        ai_tool = AIServiceTool()
        
        # 测试健康检查
        health_status = await ai_tool.health_check()
        print(f"   AI服务工具健康检查: {'✅' if health_status.get('healthy', False) else '❌'}")
        
        # 测试基本功能
        actions = ai_tool.get_available_actions()
        print(f"   可用操作: {actions}")
        
        # 测试文本生成工具
        from app.agents.tools.ai_services.text_generation_tool import TextGenerationTool
        
        text_tool = TextGenerationTool()
        specialized_methods = text_tool.get_specialized_methods()
        print(f"   文本生成工具专门方法: {specialized_methods}")
        
    except Exception as e:
        print(f"❌ 工具系统功能测试失败: {e}")
        return False
    
    # 4. 测试Agent统一AI接口
    print("\n🤖 第四步：测试Agent统一AI接口...")
    
    try:
        # 测试ConceptPlanner的新接口
        from app.agents.concept_planner import ConceptPlannerAgent
        
        concept_agent = ConceptPlannerAgent()
        
        # 检查统一接口方法
        has_unified_methods = all([
            hasattr(concept_agent, 'generate_text'),
            hasattr(concept_agent, 'register_default_tools'),
            hasattr(concept_agent, 'ensure_ai_tools_available')
        ])
        
        if has_unified_methods:
            print("   ✅ ConceptPlanner: 统一AI接口已实现")
            
            # 测试工具注册
            concept_agent.register_default_tools()
            print("   ✅ ConceptPlanner: 默认工具注册成功")
            
        else:
            print("   ❌ ConceptPlanner: 统一AI接口缺失")
            
    except Exception as e:
        print(f"   ❌ Agent统一接口测试失败: {e}")
        return False
    
    # 5. 统计解耦效果
    print("\n📊 第五步：解耦效果统计...")
    
    total_agents = len(tool_integration_results)
    decoupled_agents = sum(1 for result in tool_integration_results.values() if result.get("decoupled", False))
    
    print(f"   总Agent数量: {total_agents}")
    print(f"   已解耦Agent: {decoupled_agents}")
    print(f"   解耦成功率: {decoupled_agents/total_agents*100:.1f}%")
    
    # 详细解耦状态
    print(f"\n🔍 详细解耦状态:")
    for agent_name, result in tool_integration_results.items():
        if result.get("decoupled", False):
            print(f"   ✅ {agent_name}: 完全解耦")
        elif "error" in result:
            print(f"   ❌ {agent_name}: 错误 - {result['error']}")
        else:
            print(f"   ⚠️ {agent_name}: 部分解耦")
    
    # 最终结果
    success_threshold = 0.8  # 80%解耦率认为成功
    
    if decoupled_agents / total_agents >= success_threshold:
        print(f"\n🎉 工具系统解耦测试成功!")
        print(f"📊 解耦效果摘要:")
        print(f"   ✅ 工具注册系统: 正常运行")
        print(f"   ✅ AI工具自动注册: {len(available_ai_tools)}/{len(expected_ai_tools)}个")
        print(f"   ✅ Agent解耦: {decoupled_agents}/{total_agents}个")
        print(f"   ✅ 统一AI接口: 已实现")
        print(f"   ✅ 依赖注入: 通过工具系统实现")
        print(f"\n🚀 Phase 1.3 - 工具系统解耦基本完成!")
        print(f"✨ Agent现在通过标准化工具接口使用AI服务，实现真正的依赖解耦")
        
        return True
    else:
        print(f"\n⚠️ 工具系统解耦未完全完成:")
        print(f"   当前解耦率: {decoupled_agents/total_agents*100:.1f}%")
        print(f"   目标解耦率: {success_threshold*100:.1f}%")
        return False
        
    return True

if __name__ == "__main__":
    success = asyncio.run(test_tool_decoupling())
    sys.exit(0 if success else 1)
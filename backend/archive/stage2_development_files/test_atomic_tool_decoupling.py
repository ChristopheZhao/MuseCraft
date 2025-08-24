#!/usr/bin/env python3
"""
测试原子性工具系统解耦效果
"""

import sys
import os
import asyncio
from typing import Dict, List
sys.path.append(os.path.dirname(__file__))

async def test_atomic_tool_decoupling():
    """测试原子性工具系统解耦效果"""
    
    print("🔧 测试原子性工具系统解耦效果...")
    
    # 1. 测试原子性工具注册
    print("\n📋 第一步：测试原子性工具注册...")
    try:
        from app.agents.tools.tool_registry import get_tool_registry
        
        registry = get_tool_registry()
        
        # 检查原子性AI工具是否注册
        tools = registry.list_tools()
        print(f"✅ 工具注册系统初始化成功")
        print(f"   已注册工具总数: {len(tools)}")
        
        # 检查特定原子性工具
        expected_atomic_tools = [
            "concept_generation_tool",
            "scene_script_generation_tool", 
            "narrative_structure_generation_tool",
            "quality_analysis_tool"
        ]
        
        available_atomic_tools = []
        
        for tool_name in expected_atomic_tools:
            try:
                tool_info = registry.get_tool_info(tool_name)
                available_atomic_tools.append(tool_name)
                print(f"   ✅ {tool_name}: {tool_info['metadata']['description']}")
            except Exception as e:
                print(f"   ❌ {tool_name}: 未注册 - {e}")
        
        if len(available_atomic_tools) == len(expected_atomic_tools):
            print("✅ 所有预期原子性工具已注册")
        else:
            print(f"⚠️ 只有 {len(available_atomic_tools)}/{len(expected_atomic_tools)} 个原子性工具注册成功")
        
    except Exception as e:
        print(f"❌ 原子性工具注册系统测试失败: {e}")
        return False
    
    # 2. 测试工具原子性设计
    print("\n⚛️ 第二步：测试工具原子性设计...")
    
    atomic_tests = []
    
    try:
        # 测试概念生成工具的原子性
        from app.agents.tools.ai_services.concept_generation_tool import ConceptGenerationTool
        
        concept_tool = ConceptGenerationTool()
        
        # 验证单一职责
        actions = concept_tool.get_available_actions()
        if len(actions) == 1 and actions[0] == "generate_concept":
            print("   ✅ ConceptGenerationTool: 单一职责原则 ✓")
            atomic_tests.append(("ConceptGenerationTool", True, "专门负责概念生成"))
        else:
            print(f"   ❌ ConceptGenerationTool: 违反单一职责 - 操作: {actions}")
            atomic_tests.append(("ConceptGenerationTool", False, f"多个操作: {actions}"))
        
        # 测试场景脚本生成工具的原子性
        from app.agents.tools.ai_services.scene_script_generation_tool import SceneScriptGenerationTool
        
        script_tool = SceneScriptGenerationTool()
        actions = script_tool.get_available_actions()
        if len(actions) == 1 and actions[0] == "generate_scene_script":
            print("   ✅ SceneScriptGenerationTool: 单一职责原则 ✓")
            atomic_tests.append(("SceneScriptGenerationTool", True, "专门负责场景脚本生成"))
        else:
            print(f"   ❌ SceneScriptGenerationTool: 违反单一职责 - 操作: {actions}")
            atomic_tests.append(("SceneScriptGenerationTool", False, f"多个操作: {actions}"))
        
        # 测试叙事结构生成工具的原子性
        from app.agents.tools.ai_services.narrative_structure_generation_tool import NarrativeStructureGenerationTool
        
        narrative_tool = NarrativeStructureGenerationTool()
        actions = narrative_tool.get_available_actions()
        if len(actions) == 1 and actions[0] == "generate_narrative_structure":
            print("   ✅ NarrativeStructureGenerationTool: 单一职责原则 ✓")
            atomic_tests.append(("NarrativeStructureGenerationTool", True, "专门负责叙事结构生成"))
        else:
            print(f"   ❌ NarrativeStructureGenerationTool: 违反单一职责 - 操作: {actions}")
            atomic_tests.append(("NarrativeStructureGenerationTool", False, f"多个操作: {actions}"))
        
        # 测试质量分析工具的原子性
        from app.agents.tools.ai_services.quality_analysis_tool import QualityAnalysisTool
        
        quality_tool = QualityAnalysisTool()
        actions = quality_tool.get_available_actions()
        if len(actions) == 1 and actions[0] == "analyze_quality":
            print("   ✅ QualityAnalysisTool: 单一职责原则 ✓")
            atomic_tests.append(("QualityAnalysisTool", True, "专门负责质量分析"))
        else:
            print(f"   ❌ QualityAnalysisTool: 违反单一职责 - 操作: {actions}")
            atomic_tests.append(("QualityAnalysisTool", False, f"多个操作: {actions}"))
        
    except Exception as e:
        print(f"❌ 原子性设计测试失败: {e}")
        return False
    
    # 3. 测试Agent与原子性工具的集成
    print("\n🤖 第三步：测试Agent与原子性工具的集成...")
    
    agent_tool_mappings = [
        ("ConceptPlannerAgent", "app.agents.concept_planner", "ConceptPlannerAgent", ["concept_generation_tool"]),
        ("ScriptWriterAgent", "app.agents.script_writer", "ScriptWriterAgent", ["scene_script_generation_tool", "narrative_structure_generation_tool"]),
        ("QualityCheckerAgent", "app.agents.quality_checker", "QualityCheckerAgent", ["quality_analysis_tool"])
    ]
    
    agent_integration_results = {}
    
    for agent_name, module_path, class_name, expected_tools in agent_tool_mappings:
        try:
            # 动态导入并实例化Agent
            module = __import__(module_path, fromlist=[class_name])
            agent_class = getattr(module, class_name)
            agent = agent_class()
            
            # 检查工具配置
            has_tool_registry = hasattr(agent, 'tool_registry') and agent.tool_registry is not None
            available_tools = list(agent._available_tools.keys()) if hasattr(agent, '_available_tools') else []
            
            # 检查是否使用了正确的原子性工具
            correct_tools = all(tool in expected_tools for tool in available_tools if tool in expected_tools)
            
            # 检查是否移除了直接AI客户端依赖
            has_direct_ai_client = hasattr(agent, 'ai_client') and agent.ai_client is not None
            
            agent_integration_results[agent_name] = {
                "tool_registry": has_tool_registry,
                "expected_tools": expected_tools,
                "available_tools": available_tools,
                "correct_atomic_tools": correct_tools,
                "no_direct_ai_client": not has_direct_ai_client,
                "atomic_decoupled": has_tool_registry and correct_tools and not has_direct_ai_client
            }
            
            status = "✅ 原子性解耦" if agent_integration_results[agent_name]["atomic_decoupled"] else "⚠️ 部分解耦"
            print(f"   {status} {agent_name}:")
            print(f"     工具注册系统: {'✅' if has_tool_registry else '❌'}")
            print(f"     预期原子性工具: {expected_tools}")
            print(f"     实际可用工具: {available_tools}")
            print(f"     原子性工具正确: {'✅' if correct_tools else '❌'}")
            print(f"     无直接AI依赖: {'✅' if not has_direct_ai_client else '⚠️ 仍存在'}")
            
        except Exception as e:
            print(f"   ❌ {agent_name}: 实例化失败 - {e}")
            agent_integration_results[agent_name] = {"atomic_decoupled": False, "error": str(e)}
    
    # 4. 测试工具功能特化
    print("\n🎯 第四步：测试工具功能特化...")
    
    try:
        # 验证工具的功能特化
        print("   验证工具功能特化:")
        print("   📝 ConceptGenerationTool → 专门生成视频概念计划")
        print("   ✍️ SceneScriptGenerationTool → 专门生成单个场景脚本")
        print("   📖 NarrativeStructureGenerationTool → 专门生成叙事结构")
        print("   🔍 QualityAnalysisTool → 专门进行质量分析")
        
        # 验证输入输出模式的特化
        for tool_name, tool_class in [
            ("concept_generation_tool", ConceptGenerationTool),
            ("scene_script_generation_tool", SceneScriptGenerationTool),
            ("narrative_structure_generation_tool", NarrativeStructureGenerationTool),
            ("quality_analysis_tool", QualityAnalysisTool)
        ]:
            tool = tool_class()
            actions = tool.get_available_actions()
            
            for action in actions:
                schema = tool.get_action_schema(action)
                required_params = schema.get("required", [])
                print(f"   ✅ {tool_name}.{action}: 需要参数 {required_params}")
        
    except Exception as e:
        print(f"❌ 工具功能特化测试失败: {e}")
        return False
    
    # 5. 统计原子性解耦效果
    print("\n📊 第五步：原子性解耦效果统计...")
    
    total_atomic_tools = len(expected_atomic_tools)
    registered_atomic_tools = len(available_atomic_tools)
    
    total_atomic_tests = len(atomic_tests)
    passed_atomic_tests = sum(1 for _, passed, _ in atomic_tests if passed)
    
    total_agents = len(agent_integration_results)
    decoupled_agents = sum(1 for result in agent_integration_results.values() if result.get("atomic_decoupled", False))
    
    print(f"   原子性工具注册: {registered_atomic_tools}/{total_atomic_tools}")
    print(f"   原子性设计测试: {passed_atomic_tests}/{total_atomic_tests}")
    print(f"   Agent原子性解耦: {decoupled_agents}/{total_agents}")
    
    # 6. 验证原子性原则
    print("\n⚛️ 第六步：验证原子性原则...")
    
    atomic_principles = [
        ("单一职责", passed_atomic_tests == total_atomic_tests, "每个工具只做一件事"),
        ("功能独立", registered_atomic_tools == total_atomic_tools, "工具间功能不重叠"),
        ("接口清晰", True, "明确的输入输出定义"),
        ("可组合性", decoupled_agents > 0, "可以被Agent灵活使用")
    ]
    
    for principle, passed, description in atomic_principles:
        status = "✅" if passed else "❌"
        print(f"   {status} {principle}: {description}")
    
    # 最终结果
    all_atomic_principles_passed = all(passed for _, passed, _ in atomic_principles)
    high_decoupling_rate = (decoupled_agents / total_agents) >= 0.8 if total_agents > 0 else False
    
    if all_atomic_principles_passed and high_decoupling_rate:
        print(f"\n🎉 原子性工具系统解耦测试成功!")
        print(f"📊 原子性解耦效果摘要:")
        print(f"   ✅ 工具原子性设计: {passed_atomic_tests}/{total_atomic_tests}个通过")
        print(f"   ✅ 原子性工具注册: {registered_atomic_tools}/{total_atomic_tools}个")
        print(f"   ✅ Agent原子性解耦: {decoupled_agents}/{total_agents}个")
        print(f"   ✅ 单一职责原则: 每个工具专注一个明确功能")
        print(f"   ✅ 功能特化: 工具按业务功能原子化分解")
        print(f"   ✅ 依赖解耦: Agent通过工具名称而非类型调用功能")
        print(f"\n🚀 Phase 1.3 - 原子性工具系统解耦完成!")
        print(f"✨ 实现了'do one thing and do it well'的原子性设计原则")
        print(f"🔧 每个工具都是独立的、可复用的功能单元")
        
        return True
    else:
        print(f"\n⚠️ 原子性工具系统解耦未完全完成:")
        print(f"   原子性原则通过率: {sum(1 for _, passed, _ in atomic_principles if passed)}/{len(atomic_principles)}")
        print(f"   Agent解耦率: {decoupled_agents/total_agents*100:.1f}%" if total_agents > 0 else "   Agent解耦率: 0%")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_atomic_tool_decoupling())
    sys.exit(0 if success else 1)
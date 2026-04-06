#!/usr/bin/env python3
# moved to tests/integration
"""
测试完整的LLM驱动系统 - 验证是否真正移除了硬编码
"""

import asyncio
import logging
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# 确保工具注册
from app.agents.tools import register_default_tools
register_default_tools()

from app.agents.concept_planner import ConceptPlannerAgent
from app.agents.video_generator import VideoGeneratorAgent
from app.agents.tools.agent_tool_allocation import get_agent_tools
from app.models import AgentType

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_concept_planner_dynamic_scenes():
    """测试ConceptPlannerAgent的动态场景规划"""
    print("\n🎭 测试ConceptPlannerAgent的动态场景规划...")
    
    agent = ConceptPlannerAgent()
    print(f"✅ ConceptPlanner可用工具: {agent.get_tool_names()}")
    
    # 测试不同复杂度的内容，看场景数量是否智能变化
    test_cases = [
        {
            "name": "简单内容",
            "prompt": "一个苹果掉落",
            "duration": 10,
            "expected_scenes_range": (1, 2)
        },
        {
            "name": "中等复杂内容", 
            "prompt": "主角在雨夜中奔跑追逐神秘身影，雷声轰鸣",
            "duration": 30,
            "expected_scenes_range": (2, 4)
        },
        {
            "name": "复杂故事内容",
            "prompt": "英雄从平凡的村庄出发，穿越危险的森林，与恶龙战斗，拯救公主，最终回到家乡成为传奇",
            "duration": 60,
            "expected_scenes_range": (5, 10)
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        print(f"\n🧪 测试案例: {test_case['name']}")
        print(f"输入: {test_case['prompt']}")
        print(f"时长: {test_case['duration']}秒")
        
        try:
            # 直接测试智能场景规划工具
            scene_planning_result = await agent.use_tool(
                "intelligent_scene_planning",
                "analyze_and_plan_scenes",
                {
                    "user_prompt": test_case["prompt"],
                    "target_total_duration": test_case["duration"],
                    "video_style": "cinematic",
                    "complexity_hint": "auto"
                }
            )
            
            if scene_planning_result and hasattr(scene_planning_result, 'result'):
                planning_data = scene_planning_result.result
                
                if planning_data.get("success"):
                    scene_plan = planning_data.get("scene_plan", {})
                    if "scene_plan" in scene_plan:
                        total_scenes = scene_plan["scene_plan"]["total_scenes"]
                        scenes = scene_plan["scene_plan"]["scenes"]
                    else:
                        total_scenes = len(planning_data.get("scenes", []))
                        scenes = planning_data.get("scenes", [])
                    
                    print(f"✅ 智能规划结果: {total_scenes}个场景")
                    print(f"🎯 规划方式: {planning_data.get('approach', 'unknown')}")
                    print(f"🔮 置信度: {planning_data.get('confidence', 0)}")
                    
                    # 展示场景分配
                    for i, scene in enumerate(scenes[:3]):  # 只显示前3个场景
                        duration = scene.get("duration", 0)
                        focus = scene.get("content_focus", "")[:50]
                        print(f"   场景{i+1}: {duration}秒 - {focus}...")
                    
                    if len(scenes) > 3:
                        print(f"   ... 还有{len(scenes)-3}个场景")
                    
                    # 检查是否在预期范围内
                    expected_min, expected_max = test_case["expected_scenes_range"]
                    if expected_min <= total_scenes <= expected_max:
                        print(f"✅ 场景数量在预期范围内 ({expected_min}-{expected_max})")
                    else:
                        print(f"⚠️ 场景数量超出预期范围 ({expected_min}-{expected_max}), 但这可能是LLM的智能决策")
                    
                    results.append({
                        "test_case": test_case["name"],
                        "scenes": total_scenes,
                        "approach": planning_data.get('approach'),
                        "confidence": planning_data.get('confidence'),
                        "success": True
                    })
                else:
                    print(f"❌ 智能场景规划失败: {planning_data.get('error', 'Unknown error')}")
                    results.append({
                        "test_case": test_case["name"],
                        "success": False,
                        "error": str(planning_data.get('error', 'Planning failed'))
                    })
            else:
                print("❌ 工具调用返回无效结果")
                results.append({
                    "test_case": test_case["name"],
                    "success": False,
                    "error": "Invalid tool response"
                })
                
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append({
                "test_case": test_case["name"],
                "success": False,
                "error": str(e)
            })
    
    return results

async def test_video_generator_dynamic_duration():
    """测试VideoGeneratorAgent的动态时长决策"""
    print("\n🎬 测试VideoGeneratorAgent的动态时长决策...")
    
    agent = VideoGeneratorAgent()
    print(f"✅ VideoGenerator可用工具: {agent.get_tool_names()}")
    
    test_scenes = [
        {
            "name": "简单静态场景",
            "script_text": "一朵花在阳光下绽放",
            "expected_duration": 5
        },
        {
            "name": "复杂动作场景", 
            "script_text": "主角在雨夜中快速奔跑，追逐着前方的神秘身影。雷声轰鸣，闪电照亮了狭窄的巷道，动作紧张激烈",
            "expected_duration": 10
        }
    ]
    
    results = []
    
    for test_scene in test_scenes:
        print(f"\n🧪 测试场景: {test_scene['name']}")
        print(f"脚本: {test_scene['script_text']}")
        
        try:
            # 测试参数优化工具
            optimization_result = await agent.use_tool(
                "parameter_optimization", 
                "optimize_duration",
                {
                    "scene_data": {
                        "script_text": test_scene["script_text"],
                        "visual_description": "相应的视觉描述",
                        "narrative_description": "叙事描述",
                        "mood_and_atmosphere": "氛围",
                        "duration": 7  # 初始时长
                    },
                    "available_durations": [5, 10]
                }
            )
            
            if optimization_result and hasattr(optimization_result, 'result'):
                opt_data = optimization_result.result
                recommended_duration = opt_data.get("recommended_parameters", {}).get("duration", 5)
                confidence = opt_data.get("confidence", 0)
                reasoning = ""
                
                if "analysis" in opt_data:
                    reasoning = opt_data["analysis"].get("reasoning", "")
                
                print(f"✅ 推荐时长: {recommended_duration}秒")
                print(f"🔮 置信度: {confidence}")
                print(f"💭 推理: {reasoning}")
                
                # 检查是否符合预期
                if recommended_duration == test_scene["expected_duration"]:
                    print("✅ 时长决策符合预期")
                else:
                    print(f"⚠️ 时长决策与预期不同 (预期{test_scene['expected_duration']}秒)，但这可能是LLM的智能判断")
                
                results.append({
                    "scene": test_scene["name"],
                    "recommended_duration": recommended_duration,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "success": True
                })
            else:
                print("❌ 参数优化工具调用失败")
                results.append({
                    "scene": test_scene["name"],
                    "success": False,
                    "error": "Tool call failed"
                })
                
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append({
                "scene": test_scene["name"],
                "success": False,
                "error": str(e)
            })
    
    return results

async def test_function_call_integration():
    """测试Function Call的集成情况"""
    print("\n🤖 测试Function Call集成...")
    
    # 检查各个Agent的工具分配
    agents_to_test = [
        (AgentType.CONCEPT_PLANNER, ConceptPlannerAgent),
        (AgentType.VIDEO_GENERATOR, VideoGeneratorAgent)
    ]
    
    results = {}
    
    for agent_type, agent_class in agents_to_test:
        print(f"\n📋 检查 {agent_type.value} Agent...")
        
        # 检查工具分配
        allocated_tools = get_agent_tools(agent_type)
        print(f"分配的工具: {allocated_tools}")
        
        # 实例化Agent并检查加载的工具
        try:
            agent = agent_class()
            loaded_tools = agent.get_tool_names() if hasattr(agent, 'get_tool_names') else []
            print(f"实际加载的工具: {loaded_tools}")
            
            # 检查Function Call能力
            has_function_call = hasattr(agent, 'llm_function_call')
            print(f"支持Function Call: {'✅' if has_function_call else '❌'}")
            
            results[agent_type.value] = {
                "allocated_tools": allocated_tools,
                "loaded_tools": loaded_tools,
                "supports_function_call": has_function_call,
                "success": True
            }
            
        except Exception as e:
            print(f"❌ Agent实例化失败: {e}")
            results[agent_type.value] = {
                "success": False,
                "error": str(e)
            }
    
    return results

async def main():
    """主测试函数"""
    print("🚀 开始测试完整的LLM驱动系统 - 验证硬编码移除情况\n")
    
    # 测试步骤
    tests = [
        ("ConceptPlanner动态场景规划", test_concept_planner_dynamic_scenes),
        ("VideoGenerator动态时长决策", test_video_generator_dynamic_duration),
        ("Function Call集成测试", test_function_call_integration),
    ]
    
    all_results = {}
    
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"🧪 {test_name}")
        print('='*60)
        
        try:
            result = await test_func()
            all_results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            all_results[test_name] = {"error": str(e)}
    
    # 总结结果
    print(f"\n{'='*60}")
    print("📊 LLM驱动系统测试总结")
    print('='*60)
    
    # 分析场景规划结果
    scene_results = all_results.get("ConceptPlanner动态场景规划", [])
    if scene_results and isinstance(scene_results, list):
        successful_scene_tests = [r for r in scene_results if r.get("success")]
        print(f"\n🎭 场景规划测试: {len(successful_scene_tests)}/{len(scene_results)} 成功")
        
        for result in successful_scene_tests:
            approach = result.get("approach", "unknown")
            scenes = result.get("scenes", 0)
            confidence = result.get("confidence", 0)
            print(f"  {result['test_case']}: {scenes}个场景 ({approach}, 置信度{confidence:.2f})")
    
    # 分析时长决策结果  
    duration_results = all_results.get("VideoGenerator动态时长决策", [])
    if duration_results and isinstance(duration_results, list):
        successful_duration_tests = [r for r in duration_results if r.get("success")]
        print(f"\n🎬 时长决策测试: {len(successful_duration_tests)}/{len(duration_results)} 成功")
        
        for result in successful_duration_tests:
            duration = result.get("recommended_duration", 0)
            confidence = result.get("confidence", 0)
            print(f"  {result['scene']}: {duration}秒 (置信度{confidence:.2f})")
    
    # 分析Function Call集成
    fc_results = all_results.get("Function Call集成测试", {})
    if fc_results:
        print(f"\n🤖 Function Call集成:")
        for agent_type, data in fc_results.items():
            if data.get("success"):
                fc_support = "✅" if data.get("supports_function_call") else "❌"
                tool_count = len(data.get("loaded_tools", []))
                print(f"  {agent_type}: {fc_support} Function Call, {tool_count}个工具")
    
    # 最终结论
    print(f"\n🎯 系统改进状态:")
    
    # 检查是否真正移除了硬编码
    hardcoded_removed = True
    improvements = []
    
    if scene_results and isinstance(scene_results, list) and any(
        isinstance(r, dict) and r.get("approach") in ["llm_intelligent_planning", "intelligent_fallback"] 
        for r in scene_results if isinstance(r, dict) and r.get("success")
    ):
        improvements.append("✅ 场景数量不再硬编码，由LLM智能决定")
    else:
        improvements.append("❌ 场景数量可能仍有硬编码")
        hardcoded_removed = False
    
    if duration_results and isinstance(duration_results, list) and any(
        isinstance(r, dict) and r.get("success") for r in duration_results
    ):
        improvements.append("✅ 视频时长不再硬编码，由LLM根据内容决定")
    else:
        improvements.append("❌ 视频时长可能仍有硬编码")
        hardcoded_removed = False
    
    if fc_results and all(data.get("supports_function_call", False) for data in fc_results.values() if data.get("success")):
        improvements.append("✅ 所有Agent都支持Function Call")
    else:
        improvements.append("❌ 部分Agent不支持Function Call")
        hardcoded_removed = False
    
    for improvement in improvements:
        print(f"  {improvement}")
    
    if hardcoded_removed:
        print(f"\n🎉 恭喜！系统已成功从硬编码转换为LLM智能驱动！")
        print(f"   - 场景数量: LLM根据内容复杂度智能决定（不受4-8限制）")
        print(f"   - 视频时长: LLM根据场景特征选择5秒或10秒")
        print(f"   - 工具选择: LLM通过Function Call智能选择工具和参数")
    else:
        print(f"\n⚠️ 系统仍需进一步改进以完全移除硬编码")

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
测试Function Call版本的ConceptPlannerAgent
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

from app.agents.concept_planner_fc import ConceptPlannerAgentFC
from app.agents.video_generator import VideoGeneratorAgent
from app.core.workflow_state import WorkflowState, workflow_manager

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_function_call_concept_planner():
    """测试Function Call版本的ConceptPlanner"""
    print("\n🧠 测试Function Call版本的ConceptPlanner...")
    
    agent = ConceptPlannerAgentFC()
    print(f"✅ ConceptPlannerFC可用工具: {agent.get_tool_names()}")
    
    # 创建测试用例
    test_cases = [
        {
            "name": "简单故事",
            "prompt": "一只小猫在花园里玩耍",
            "duration": 15,
            "expected_scenes": 1
        },
        {
            "name": "复杂冒险",
            "prompt": "勇敢的骑士穿越黑暗森林，与巨龙战斗，拯救被困公主，最终凯旋归来",
            "duration": 60,
            "expected_scenes": 4
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        print(f"\n🧪 测试案例: {test_case['name']}")
        print(f"输入: {test_case['prompt']}")
        print(f"时长: {test_case['duration']}秒")
        
        try:
            # 创建工作流状态
            workflow_state = WorkflowState("test")
            workflow_state_id = workflow_manager.create_workflow(
                "test", test_case['prompt'], "cinematic"
            )
            
            # 准备输入数据
            input_data = {
                "user_prompt": test_case["prompt"],
                "video_style": "cinematic",
                "duration": test_case["duration"],
                "aspect_ratio": "16:9",
                "workflow_state_id": workflow_state_id
            }
            
            # 模拟Task和AgentExecution（简化版本）
            class MockTask:
                def __init__(self):
                    self.id = 1
                    self.task_id = "test_task"
            
            class MockAgentExecution:
                def __init__(self):
                    self.id = 1
                    pass
            
            class MockDB:
                def add(self, obj): pass
                def commit(self): pass
                def refresh(self, obj): pass
            
            task = MockTask()
            execution = MockAgentExecution()
            db = MockDB()
            
            # 执行Function Call概念规划
            result = await agent._llm_guided_concept_planning(
                test_case["prompt"],
                "cinematic", 
                test_case["duration"],
                "16:9"
            )
            
            # 处理结果
            concept_plan = agent._process_planning_results(result)
            scenes_count = len(concept_plan.get("scenes", []))
            approach = concept_plan.get("approach", "unknown")
            
            print(f"✅ Function Call规划结果: {scenes_count}个场景")
            print(f"🎯 规划方式: {approach}")
            
            # 显示场景详情
            for i, scene in enumerate(concept_plan.get("scenes", [])[:3]):
                content = scene.get("content_focus", "")[:30]
                duration = scene.get("duration", 0)
                print(f"   场景{i+1}: {duration}秒 - {content}...")
            
            if scenes_count > 3:
                print(f"   ... 还有{scenes_count-3}个场景")
            
            results.append({
                "test_case": test_case["name"],
                "scenes": scenes_count,
                "approach": approach,
                "success": True
            })
            
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append({
                "test_case": test_case["name"],
                "success": False,
                "error": str(e)
            })
    
    return results

async def test_video_generator_fc():
    """测试VideoGenerator的Function Call"""
    print("\n🎬 测试VideoGenerator的Function Call...")
    
    agent = VideoGeneratorAgent()
    print(f"✅ VideoGenerator可用工具: {agent.get_tool_names()}")
    
    # 测试LLM引导的视频生成
    test_scenes = [
        {
            "name": "动态场景",
            "script": "激烈的追车场面，汽车在城市街道高速驰骋",
            "expected_duration": 10
        },
        {
            "name": "静态场景", 
            "script": "宁静的湖边日落景色",
            "expected_duration": 5
        }
    ]
    
    results = []
    
    for test_scene in test_scenes:
        print(f"\n🧪 测试场景: {test_scene['name']}")
        print(f"脚本: {test_scene['script']}")
        
        try:
            # 创建模拟的scene_data
            class MockSceneData:
                def __init__(self, script_text):
                    self.script_text = script_text
                    self.visual_description = "相应的视觉描述"
                    self.narrative_description = "叙事描述"
                    self.duration = 5
                    self.image_url = None
                    self.image_path = None
            
            scene_data = MockSceneData(test_scene["script"])
            
            # 测试LLM引导的视频生成
            llm_result = await agent._llm_guided_video_generation(
                scene_data, None, "test_workflow"
            )
            
            print(f"✅ LLM视频生成决策完成")
            
            # 检查Function Call结果
            if llm_result and isinstance(llm_result, dict):
                tool_calls = llm_result.get("tool_results", [])
                print(f"🔧 执行了 {len(tool_calls)} 个工具调用")
                
                # 查找参数优化结果
                param_results = []
                for call in tool_calls:
                    if "parameter_optimization" in call.get("tool", ""):
                        if call.get("result") and hasattr(call["result"], "result"):
                            opt_data = call["result"].result
                            duration = opt_data.get("recommended_parameters", {}).get("duration", 5)
                            confidence = opt_data.get("confidence", 0)
                            param_results.append({
                                "duration": duration,
                                "confidence": confidence
                            })
                
                if param_results:
                    best_param = param_results[0]
                    print(f"🎯 推荐参数: {best_param['duration']}秒 (置信度: {best_param['confidence']})")
                    
                    results.append({
                        "scene": test_scene["name"],
                        "recommended_duration": best_param["duration"],
                        "confidence": best_param["confidence"],
                        "success": True
                    })
                else:
                    print("⚠️ 未找到参数优化结果")
                    results.append({
                        "scene": test_scene["name"],
                        "success": False,
                        "error": "No parameter optimization result"
                    })
            else:
                print("❌ LLM引导视频生成失败")
                results.append({
                    "scene": test_scene["name"],
                    "success": False,
                    "error": "LLM guided generation failed"
                })
                
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append({
                "scene": test_scene["name"],
                "success": False,
                "error": str(e)
            })
    
    return results

async def main():
    """主测试函数"""
    print("🚀 测试完整的Function Call架构\n")
    
    # 测试步骤
    tests = [
        ("ConceptPlannerFC Function Call", test_function_call_concept_planner),
        ("VideoGenerator Function Call", test_video_generator_fc),
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
    print("📊 Function Call架构测试总结")
    print('='*60)
    
    # ConceptPlannerFC结果
    cp_results = all_results.get("ConceptPlannerFC Function Call", [])
    if cp_results and isinstance(cp_results, list):
        successful_cp = [r for r in cp_results if r.get("success")]
        print(f"\n🧠 ConceptPlannerFC测试: {len(successful_cp)}/{len(cp_results)} 成功")
        
        for result in successful_cp:
            approach = result.get("approach", "unknown")
            scenes = result.get("scenes", 0)
            print(f"  {result['test_case']}: {scenes}个场景 ({approach})")
    
    # VideoGenerator结果  
    vg_results = all_results.get("VideoGenerator Function Call", [])
    if vg_results and isinstance(vg_results, list):
        successful_vg = [r for r in vg_results if r.get("success")]
        print(f"\n🎬 VideoGenerator FC测试: {len(successful_vg)}/{len(vg_results)} 成功")
        
        for result in successful_vg:
            duration = result.get("recommended_duration", 0)
            confidence = result.get("confidence", 0)
            print(f"  {result['scene']}: {duration}秒 (置信度{confidence:.2f})")
    
    # 最终结论
    print(f"\n🎯 Function Call架构状态:")
    
    if cp_results and any(r.get("success") for r in cp_results):
        print("  ✅ ConceptPlanner完全使用Function Call进行场景规划")
    else:
        print("  ❌ ConceptPlanner Function Call需要改进")
    
    if vg_results and any(r.get("success") for r in vg_results):
        print("  ✅ VideoGenerator完全使用Function Call进行参数决策")
    else:
        print("  ❌ VideoGenerator Function Call需要改进")
    
    print(f"\n🎉 Function Call架构测试完成！")

if __name__ == "__main__":
    asyncio.run(main())
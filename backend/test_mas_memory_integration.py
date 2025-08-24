#!/usr/bin/env python3
"""
测试MAS记忆系统集成 - 验证Agent间记忆共享的实际使用
"""

import sys
import os
import asyncio
import uuid
from datetime import datetime
sys.path.append(os.path.dirname(__file__))

async def test_mas_memory_integration():
    """测试MAS记忆系统的端到端集成"""
    
    print("🧠 测试MAS记忆系统集成...")
    
    try:
        # 创建测试工作流ID
        test_workflow_id = f"test_workflow_{uuid.uuid4().hex[:8]}"
        print(f"📋 测试工作流ID: {test_workflow_id}")
        
        # 测试数据
        test_concept_plan = {
            "overview": "测试视频：一个关于AI技术发展的短视频",
            "visual_style": "现代科技风格",
            "mood_and_tone": "专业且引人入胜",
            "key_messages": ["AI技术发展迅速", "影响深远"],
            "target_audience": "科技爱好者",
            "scenes": [
                {
                    "scene_number": 1,
                    "title": "AI技术介绍",
                    "description": "展示AI技术的核心概念"
                },
                {
                    "scene_number": 2,
                    "title": "应用场景",
                    "description": "展示AI的实际应用"
                }
            ]
        }
        
        test_scene_references = {
            "scene_design": {
                "key_subjects": ["AI技术图标", "数据流"],
                "scene_setting": "现代化办公环境",
                "visual_style_notes": "简洁现代",
                "composition_requirements": "中心构图",
                "continuity_elements": ["蓝色主色调"]
            },
            "narrative_structure": {
                "opening_state": "静态展示",
                "main_action": "技术演示",
                "closing_state": "完成展示",
                "story_function": "技术介绍"
            },
            "visual_style_notes": "现代科技风格",
            "composition_requirements": "专业构图",
            "overall_narrative": "展示AI技术的发展历程"
        }
        
        # 第一步：测试ConceptPlanner存储创意指导
        print("\n🎭 第一步：测试ConceptPlanner存储创意指导...")
        from app.agents.concept_planner import ConceptPlannerAgent
        
        concept_agent = ConceptPlannerAgent()
        
        # 存储创意指导
        concept_stored = await concept_agent.store_creative_guidance(
            workflow_id=test_workflow_id,
            concept_plan=test_concept_plan
        )
        
        if concept_stored:
            print("✅ ConceptPlanner: 创意指导存储成功")
        else:
            print("❌ ConceptPlanner: 创意指导存储失败")
            return False
        
        # 第二步：测试ScriptWriter检索创意指导和存储场景引用
        print("\n✍️ 第二步：测试ScriptWriter记忆共享...")
        from app.agents.script_writer import ScriptWriterAgent
        
        script_agent = ScriptWriterAgent()
        
        # 检索创意指导
        retrieved_concept = await script_agent.retrieve_creative_guidance(test_workflow_id)
        
        if retrieved_concept:
            print("✅ ScriptWriter: 成功检索到创意指导")
            print(f"   检索到的概述: {retrieved_concept.get('overview', 'N/A')}")
        else:
            print("❌ ScriptWriter: 创意指导检索失败")
            return False
        
        # 存储场景引用
        scene_stored = await script_agent.store_scene_references(
            workflow_id=test_workflow_id,
            scene_number=1,
            scene_references=test_scene_references
        )
        
        if scene_stored:
            print("✅ ScriptWriter: 场景引用存储成功")
        else:
            print("❌ ScriptWriter: 场景引用存储失败")
            return False
        
        # 第三步：测试ImageGenerator检索两种记忆
        print("\n🎨 第三步：测试ImageGenerator记忆共享...")
        from app.agents.image_generator import ImageGeneratorAgent
        
        image_agent = ImageGeneratorAgent()
        
        # 检索创意指导
        retrieved_concept_by_image = await image_agent.retrieve_creative_guidance(test_workflow_id)
        
        if retrieved_concept_by_image:
            print("✅ ImageGenerator: 成功检索到创意指导")
            print(f"   检索到的视觉风格: {retrieved_concept_by_image.get('visual_style', 'N/A')}")
        else:
            print("❌ ImageGenerator: 创意指导检索失败")
            return False
        
        # 检索场景引用
        retrieved_scene_ref = await image_agent.retrieve_scene_references(test_workflow_id, 1)
        
        if retrieved_scene_ref:
            print("✅ ImageGenerator: 成功检索到场景引用")
            print(f"   检索到的场景设置: {retrieved_scene_ref.get('scene_design', {}).get('scene_setting', 'N/A')}")
        else:
            print("❌ ImageGenerator: 场景引用检索失败")
            return False
        
        # 第四步：测试VideoGenerator和QualityChecker记忆检索
        print("\n🎬 第四步：测试VideoGenerator记忆共享...")
        from app.agents.video_generator import VideoGeneratorAgent
        
        video_agent = VideoGeneratorAgent()
        
        retrieved_by_video = await video_agent.retrieve_creative_guidance(test_workflow_id)
        
        if retrieved_by_video:
            print("✅ VideoGenerator: 成功检索到创意指导")
        else:
            print("❌ VideoGenerator: 创意指导检索失败")
            return False
        
        print("\n🔍 第五步：测试QualityChecker记忆共享...")
        from app.agents.quality_checker import QualityCheckerAgent
        
        quality_agent = QualityCheckerAgent()
        
        retrieved_by_quality = await quality_agent.retrieve_creative_guidance(test_workflow_id)
        
        if retrieved_by_quality:
            print("✅ QualityChecker: 成功检索到创意指导")
        else:
            print("❌ QualityChecker: 创意指导检索失败")
            return False
        
        # 验证数据一致性
        print("\n🔬 第六步：验证记忆数据一致性...")
        
        consistency_checks = [
            (retrieved_concept, retrieved_concept_by_image, "ConceptPlanner → ImageGenerator"),
            (retrieved_concept, retrieved_by_video, "ConceptPlanner → VideoGenerator"),
            (retrieved_concept, retrieved_by_quality, "ConceptPlanner → QualityChecker")
        ]
        
        all_consistent = True
        for source_data, target_data, path in consistency_checks:
            if source_data.get("overview") == target_data.get("overview"):
                print(f"✅ 数据一致性检查: {path}")
            else:
                print(f"❌ 数据一致性检查失败: {path}")
                all_consistent = False
        
        if not all_consistent:
            return False
        
        # 测试跨Agent工作流
        print("\n🔄 第七步：测试跨Agent工作流模拟...")
        
        # 模拟一个完整的工作流：创意 → 脚本 → 图像 → 视频 → 质量检查
        workflow_steps = [
            ("ConceptPlanner", concept_agent, "存储创意指导"),
            ("ScriptWriter", script_agent, "检索创意指导 + 存储场景引用"),
            ("ImageGenerator", image_agent, "检索创意指导 + 场景引用"),
            ("VideoGenerator", video_agent, "检索创意指导"),
            ("QualityChecker", quality_agent, "检索创意指导进行质量对比")
        ]
        
        workflow_success = True
        for step_name, agent, description in workflow_steps:
            try:
                # 每个Agent都能访问记忆系统
                if hasattr(agent, 'memory_manager') and agent.memory_manager is not None:
                    print(f"✅ {step_name}: 记忆系统已激活 - {description}")
                else:
                    print(f"❌ {step_name}: 记忆系统未激活")
                    workflow_success = False
            except Exception as e:
                print(f"❌ {step_name}: 记忆系统测试失败 - {e}")
                workflow_success = False
        
        if not workflow_success:
            return False
        
        # 最终结果
        print(f"\n🎉 MAS记忆系统集成测试完全成功!")
        print(f"📊 测试结果统计:")
        print(f"   ✅ 创意指导存储: ConceptPlanner → GlobalMemoryService")
        print(f"   ✅ 创意指导检索: ScriptWriter, ImageGenerator, VideoGenerator, QualityChecker")
        print(f"   ✅ 场景引用存储: ScriptWriter → GlobalMemoryService")
        print(f"   ✅ 场景引用检索: ImageGenerator")
        print(f"   ✅ 数据一致性验证: 所有Agent检索到相同的创意指导")
        print(f"   ✅ 记忆系统激活: 所有5个Agent都具备记忆共享能力")
        print(f"\n🚀 Phase 1.2 - Agent间记忆共享机制实现完成!")
        print(f"✨ 真正的MAS架构基础已建立，各Agent可以无缝共享工作流记忆")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_mas_memory_integration())
    sys.exit(0 if success else 1)
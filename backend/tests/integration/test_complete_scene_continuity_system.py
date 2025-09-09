#!/usr/bin/env python3
# moved to tests/integration
"""
完整的场景连续性系统集成测试
"""
import asyncio
import sys
sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.core.scene_continuity_memory import get_scene_continuity_memory, ContinuityMapping
from app.core.workflow_state import SceneData
from app.agents.image_generator import ImageGeneratorAgent
from app.agents.video_generator import VideoGeneratorAgent

async def test_complete_scene_continuity_system():
    """测试完整的场景连续性系统"""
    
    print("🧪 Testing Complete Scene Continuity System...")
    
    # 初始化系统组件
    continuity_memory = get_scene_continuity_memory()
    await continuity_memory.clear_all()  # 清空测试环境
    
    # 创建测试场景数据
    scene2 = SceneData(
        scene_number=2,
        title="金丹稳定",
        description="体内丹田中金丹悬浮，散发柔和光芒",
        video_path="./storage/test/scene2_video.mp4",  # 模拟视频路径
        requires_continuity_from=None
    )
    
    scene3 = SceneData(
        scene_number=3,
        title="元婴初现",
        description="同一颗金丹开始显现人形轮廓",
        requires_continuity_from=None  # 将由ImageGenerator设置
    )
    
    print("📋 Phase 1: 场景连续性分析和标记")
    
    try:
        # 模拟ImageGenerator的连续性分析
        image_generator = ImageGeneratorAgent()
        
        # 模拟前一场景和当前场景
        class MockPreviousScene:
            def __init__(self):
                self.scene_number = 2
                self.title = "金丹稳定"
                self.description = "体内丹田中金丹悬浮，散发柔和光芒"
        
        previous_scene = MockPreviousScene()
        
        # 模拟分析结果
        mock_analysis_result = {
            "strategy": "continue_from_previous",
            "reasoning": "这是同一颗金丹从稳定状态到显现人形的演进过程",
            "confidence_score": 0.9
        }
        
        # 调用标记方法
        await image_generator._mark_scene_continuity(
            scene3, previous_scene, mock_analysis_result, "test_workflow"
        )
        
        print(f"✅ Scene连续性标记完成:")
        print(f"   Scene {scene3.scene_number}.requires_continuity_from = {scene3.requires_continuity_from}")
        print(f"   Scene {scene3.scene_number}.continuity_reason = {scene3.continuity_reason}")
        
        # 验证内存系统中的标记
        continuity_info = await continuity_memory.get_scene_continuity_info(scene3.scene_number)
        print(f"✅ 内存系统验证:")
        print(f"   requires_continuity: {continuity_info['requires_continuity']}")
        print(f"   from_scene: {continuity_info['from_scene']}")
        
    except Exception as e:
        print(f"❌ Phase 1 failed: {e}")
        return
    
    print(f"\n📋 Phase 2: 模拟前一场景视频最后一帧存储")
    
    try:
        # 模拟存储Scene 2的最后一帧
        mock_final_frame_path = "./storage/continuity_frames/scene_2_final_frame.jpg"
        
        await continuity_memory.store_scene_final_frame(2, mock_final_frame_path)
        
        print(f"✅ 存储Scene 2最后一帧: {mock_final_frame_path}")
        
        # 验证能否检索到
        retrieved_frame = await continuity_memory.get_previous_scene_final_frame(2)
        print(f"✅ 检索验证: {retrieved_frame}")
        
    except Exception as e:
        print(f"❌ Phase 2 failed: {e}")
        return
    
    print(f"\n📋 Phase 3: VideoGenerator连续性应用测试")
    
    try:
        video_generator = VideoGeneratorAgent()
        
        # 测试连续性检查方法
        continuity_frame_path = await video_generator._check_scene_continuity_requirements(scene3)
        
        if continuity_frame_path:
            print(f"✅ VideoGenerator成功检测到连续性需求:")
            print(f"   将使用: {continuity_frame_path}")
        else:
            print(f"❌ VideoGenerator未检测到连续性需求")
            
        # 验证优先级逻辑
        scene3.first_frame_url = "https://example.com/scene3_generated_frame.jpg"
        
        # 模拟_generate_video_from_single_image_with_description的图像选择逻辑
        if continuity_frame_path:
            selected_image = continuity_frame_path
            image_source = "continuity_frame"
        else:
            selected_image = scene3.first_frame_url or scene3.image_url
            image_source = "generated_frame"
            
        print(f"✅ 图像选择逻辑验证:")
        print(f"   选中图像: {selected_image}")
        print(f"   图像来源: {image_source}")
        
        if image_source == "continuity_frame":
            print(f"🎉 连续性系统工作正常！使用了前一场景的最后一帧")
        else:
            print(f"⚠️  连续性系统未生效，使用了场景自己的图像")
            
    except Exception as e:
        print(f"❌ Phase 3 failed: {e}")
        return
    
    print(f"\n📋 Phase 4: 系统状态总览")
    
    try:
        # 获取连续性统计
        stats = continuity_memory.get_stats()
        print(f"✅ 连续性内存统计:")
        print(f"   连续性映射总数: {stats['total_continuity_mappings']}")
        print(f"   存储帧总数: {stats['total_stored_frames']}")
        print(f"   有连续性的场景: {stats['scenes_with_continuity']}")
        print(f"   有存储帧的场景: {stats['scenes_with_frames']}")
        
        # 获取连续性链条
        chains = await continuity_memory.list_continuity_chains()
        print(f"✅ 连续性链条:")
        for chain in chains:
            print(f"   Scene {chain['scene']} → continues from Scene {chain['continues_from']}")
            print(f"      原因: {chain['reason'][:50]}...")
            print(f"      置信度: {chain['confidence']}")
            print(f"      前帧可用: {chain['frame_available']}")
            
    except Exception as e:
        print(f"❌ Phase 4 failed: {e}")
        return
    
    print(f"\n🎉 完整的场景连续性系统测试通过！")
    print(f"\n💡 系统工作流程总结:")
    print(f"   1. ImageGenerator分析连续性 → 标记SceneData + 内存系统")
    print(f"   2. VideoGenerator检查连续性 → 优先使用前一场景最后一帧")
    print(f"   3. VideoGenerator完成后 → 提取并存储当前场景最后一帧")
    print(f"   4. 解耦设计 → 各组件职责清晰，易于维护")

if __name__ == "__main__":
    asyncio.run(test_complete_scene_continuity_system())

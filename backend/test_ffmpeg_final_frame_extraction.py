#!/usr/bin/env python3
"""
测试修复后的FFmpeg最后一帧提取功能
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.agents.video_generator import VideoGeneratorAgent

async def test_ffmpeg_final_frame_extraction():
    """测试FFmpeg最后一帧提取功能"""
    
    print("🧪 Testing FFmpeg Final Frame Extraction...")
    
    # Windows路径转换为WSL路径
    windows_video_path = r"D:\code\agent\Opensource\vertical_application\short-video-maker\backend\storage\generated\scene_1_video.mp4"
    wsl_video_path = "/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/storage/generated/scene_1_video.mp4"
    
    print(f"📁 检查视频文件存在性:")
    print(f"   Windows路径: {windows_video_path}")
    print(f"   WSL路径: {wsl_video_path}")
    
    if os.path.exists(wsl_video_path):
        print(f"✅ 视频文件存在: {wsl_video_path}")
    else:
        print(f"❌ 视频文件不存在: {wsl_video_path}")
        return
    
    # 初始化VideoGenerator
    video_generator = VideoGeneratorAgent()
    
    try:
        print(f"\n🔄 测试FFmpeg最后一帧提取...")
        
        # 调用修复后的方法
        final_frame_path = await video_generator._extract_video_final_frame(
            wsl_video_path, scene_number=1
        )
        
        if final_frame_path:
            print(f"✅ 成功提取最后一帧!")
            print(f"   输出路径: {final_frame_path}")
            
            # 检查文件是否真的被创建
            if os.path.exists(final_frame_path):
                file_size = os.path.getsize(final_frame_path)
                print(f"   文件大小: {file_size} bytes")
                print(f"🎉 FFmpeg最后一帧提取修复成功!")
            else:
                print(f"❌ 输出文件未创建: {final_frame_path}")
        else:
            print(f"❌ 提取最后一帧失败")
            
        # 测试连续性内存系统集成
        print(f"\n🔄 测试连续性内存系统集成...")
        
        from app.core.scene_continuity_memory import get_scene_continuity_memory
        continuity_memory = get_scene_continuity_memory()
        
        if final_frame_path:
            # 存储到连续性内存
            await continuity_memory.store_scene_final_frame(1, final_frame_path)
            print(f"✅ 最后一帧已存储到连续性内存")
            
            # 验证检索
            retrieved_frame = await continuity_memory.get_previous_scene_final_frame(1)
            if retrieved_frame == final_frame_path:
                print(f"✅ 连续性内存检索验证成功")
            else:
                print(f"❌ 连续性内存检索失败: {retrieved_frame}")
        
        # 模拟Scene 2的连续性检查
        print(f"\n🔄 模拟Scene 2连续性检查...")
        
        from app.core.workflow_state import SceneData
        scene2 = SceneData(
            scene_number=2,
            requires_continuity_from=1,
            continuity_reason="测试连续性"
        )
        
        continuity_frame = await video_generator._check_scene_continuity_requirements(scene2)
        
        if continuity_frame:
            print(f"✅ Scene 2连续性检查成功!")
            print(f"   将使用连续性帧: {continuity_frame}")
            print(f"🎉 完整的连续性系统工作正常!")
        else:
            print(f"❌ Scene 2连续性检查失败")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ffmpeg_final_frame_extraction())
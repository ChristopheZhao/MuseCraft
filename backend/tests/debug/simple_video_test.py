#!/usr/bin/env python3
"""
直接测试VideoGenerator Agent的视频生成方法
"""
import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.video_generator import VideoGeneratorAgent


async def test_video_generation():
    """测试视频生成"""
    
    print("🎬 测试VideoGenerator Agent")
    
    # 检查文件
    first_frame = "./storage/generated/scene_3_first_frame.jpg"
    last_frame = "./storage/generated/scene_3_last_frame.jpg"
    
    if not os.path.exists(first_frame) or not os.path.exists(last_frame):
        print(f"❌ 图片文件不存在")
        return
    
    print(f"✅ 首帧存在: {first_frame}")
    print(f"✅ 尾帧存在: {last_frame}")
    
    # 创建VideoGenerator
    video_gen = VideoGeneratorAgent()
    
    # 故事提示
    story_prompt = "A mother duck rescues a small rabbit from water. The duck carries the rabbit on her back, swimming to shore safely."
    
    print(f"📝 故事: {story_prompt}")
    print(f"🚀 开始生成视频...")
    
    try:
        # 使用VideoGenerator的内部方法（带超时处理）
        result = await video_gen._call_tool_with_extended_timeout(
            "zhipu_client",
            "generate_video", 
            {
                "prompt": story_prompt,
                "first_frame_image": first_frame,
                "last_frame_image": last_frame,
                "model": "cogvideox-3"
            },
            timeout=300  # 5分钟超时
        )
        
        if hasattr(result, 'success') and result.success:
            video_url = result.result.get("video_url", "")
            print(f"✅ 生成成功!")
            print(f"📹 视频URL: {video_url}")
            
            # 简单检查URL
            if "aigc-files.bigmodel.cn" in video_url:
                print(f"✅ URL格式正确")
                
                # 可以选择下载视频
                print(f"💡 可以手动下载视频查看效果")
                return True
            else:
                print(f"⚠️ URL格式异常")
                return False
        else:
            error = getattr(result, 'error', 'Unknown error')
            print(f"❌ 生成失败: {error}")
            return False
            
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(test_video_generation())
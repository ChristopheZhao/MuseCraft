#!/usr/bin/env python3
"""
简单测试智谱视频生成工具
"""
import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput


async def test_video_generation():
    """测试视频生成工具"""
    
    print("🎬 测试智谱视频生成工具")
    
    # 检查文件
    # first_frame = "./storage/generated/scene_3_first_frame.jpg"
    # last_frame = "./storage/generated/scene_3_last_frame.jpg"

    first_frame = "https://multi-media-zs.oss-cn-shanghai.aliyuncs.com/audio/scene_4_first_frame.jpg"
    last_frame = "https://multi-media-zs.oss-cn-shanghai.aliyuncs.com/audio/scene_4_last_frame.jpg"
    
    # if not os.path.exists(first_frame) or not os.path.exists(last_frame):
    #     print(f"❌ 图片文件不存在")
    #     return
    
    # 故事提示
    # prompt = "A mother duck rescues a small rabbit from water. The duck carries the rabbit on her back, swimming to shore safely."
    prompt = "车子在山路上行驶"
    
    # 创建工具
    tool = ZhipuClientTool()
    
    # 参数
    params = {
        "prompt": prompt,
        "first_frame_image": first_frame,
        "last_frame_image": last_frame,
        "model": "cogvideox-3"
    }
    
    tool_input = ToolInput(action="generate_video", parameters=params, timeout=300)  # 5分钟超时
    
    print("🚀 开始生成视频...")
    
    try:
        result = await tool.execute(tool_input)
        
        print(f"🔍 工具执行结果: {result}")
        
        if hasattr(result, 'success') and result.success:
            video_url = result.result.get("video_url", "")
            video_id = result.result.get("video_id", "")
            print(f"✅ 生成成功: {video_url}")
            print(f"📹 视频ID: {video_id}")
        else:
            print(f"❌ 生成失败: {getattr(result, 'error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ 执行失败: {e}")


if __name__ == "__main__":
    asyncio.run(test_video_generation())
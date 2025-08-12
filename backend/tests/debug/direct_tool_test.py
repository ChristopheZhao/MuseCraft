#!/usr/bin/env python3
"""
直接测试视频合成工具，不经过Agent
故事：鸭妈妈救援落水小兔子
"""
import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


async def test_direct_video_tool():
    """直接调用智谱AI视频工具"""
    
    print("🎬 直接测试视频合成工具")
    print("故事：鸭妈妈救援落水小兔子")
    print("=" * 50)
    
    # 图片路径
    first_frame = "./storage/generated/scene_3_first_frame.jpg"
    last_frame = "./storage/generated/scene_3_last_frame.jpg"
    
    # 检查文件
    if not os.path.exists(first_frame):
        print(f"❌ 首帧不存在: {first_frame}")
        return
    if not os.path.exists(last_frame):
        print(f"❌ 尾帧不存在: {last_frame}")
        return
        
    print(f"✅ 首帧存在")
    print(f"✅ 尾帧存在")
    
    # 简单明确的故事描述
    story = "A mother duck rescues a small rabbit from water. The mother duck carries the rabbit on her back and swims to safety."
    
    print(f"📝 故事描述: {story}")
    
    try:
        # 直接导入并使用工具
        from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
        from app.agents.tools.base_tool import ToolInput
        
        # 创建工具实例
        tool = ZhipuClientTool()
        
        # 工具参数
        params = {
            "prompt": story,
            "first_frame_image": first_frame,
            "last_frame_image": last_frame,
            "model": "cogvideox-3"
        }
        
        tool_input = ToolInput(action="generate_video", parameters=params)
        
        print(f"🚀 调用工具生成视频...")
        
        # 执行（这里可能会超时，但我们先看看能否调用）
        result = await tool.execute(tool_input)
        
        if hasattr(result, 'success') and result.success:
            video_url = result.result.get("video_url", "")
            print(f"✅ 工具调用成功!")
            print(f"📹 视频URL: {video_url}")
            return True
        else:
            error = getattr(result, 'error', 'Unknown error')
            print(f"❌ 工具调用失败: {error}")
            return False
            
    except Exception as e:
        print(f"❌ 直接工具测试失败: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(test_direct_video_tool())
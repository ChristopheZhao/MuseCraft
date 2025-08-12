#!/usr/bin/env python3
"""
测试CogVideoX-3首尾帧视频生成功能 - 使用工具系统
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput
from app.services.file_storage import FileStorageService


async def test_first_last_frame_video():
    """测试首尾帧视频生成 - 使用工具系统"""
    
    print("🎬 开始测试CogVideoX-3首尾帧视频生成（工具系统）...")
    
    # 初始化智谱AI工具和文件存储服务
    file_storage = FileStorageService()
    
    # 从环境变量获取API密钥 - 与multi-agent系统使用相同的环境变量
    import os
    config = {
        "api_key": os.getenv("GLM_API_KEY"),
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "timeout": 600
    }
    
    # 正确初始化智谱AI工具
    zhipu_tool = ZhipuClientTool(
        metadata=ZhipuClientTool.get_metadata(),
        config=config
    )
    
    # 测试参数
    first_frame_path = "./storage/generated/scene_3_first_frame.jpg"
    last_frame_path = "./storage/generated/scene_3_last_frame.jpg"
    
    # 检查文件是否存在
    if not os.path.exists(first_frame_path):
        print(f"❌ 首帧文件不存在: {first_frame_path}")
        return
    
    if not os.path.exists(last_frame_path):
        print(f"❌ 尾帧文件不存在: {last_frame_path}")
        return
    
    print(f"✅ 首帧文件: {first_frame_path}")
    print(f"✅ 尾帧文件: {last_frame_path}")
    
    # 从日志中获取Scene 3的实际首尾帧URL
    # 这些是从你的运行日志中提取的真实URL
    first_frame_public_url = "https://aigc-files.bigmodel.cn/api/cogview/202508051709309d4d3df9d19240ee_0.png"
    last_frame_public_url = "https://aigc-files.bigmodel.cn/api/cogview/20250805170940e1773bc5d16e4588_0.png"
    
    print(f"🔗 首帧URL: {first_frame_public_url}")
    print(f"🔗 尾帧URL: {last_frame_public_url}")
    print("ℹ️ 使用从运行日志中获取的实际URL")
    
    # 视频生成参数 - 使用与VideoGenerator相同的参数
    prompt = "A wide shot of people splashing water, laughing, and relaxing in the cool water. The scene should capture the essence of summer fun. People step off the boat and splash water at each other, their faces full of joy and relaxation."
    
    print(f"🎯 生成提示词: {prompt}")
    
    try:
        print("🚀 开始生成视频...")
        
        # 使用工具系统调用智谱AI - 与VideoGenerator使用相同的工具
        tool_input = ToolInput(
            action="generate_video",
            parameters={
                "prompt": prompt,
                "first_frame_image": first_frame_public_url,
                "last_frame_image": last_frame_public_url,
                "model": "cogvideox-3"
            }
        )
        
        tool_output = await zhipu_tool.execute(tool_input)
        
        if not tool_output.success:
            print(f"❌ 工具执行失败: {tool_output.error}")
            return
        
        result = tool_output.result
        print(f"✅ 视频生成成功!")
        print(f"📹 视频URL: {result.get('video_url')}")
        print(f"⏱️ 生成时长: {result.get('duration', 'N/A')}秒")
        print(f"📊 使用模型: {result.get('model', 'N/A')}")
        print(f"🎬 生成模式: {result.get('generation_mode', 'N/A')}")
        print(f"⏱️ 工具执行时间: {tool_output.execution_time:.2f}秒")
        
        # 下载并保存视频
        if result.get('video_url'):
            video_path = "./storage/generated/test_first_last_frame_video_tool.mp4"
            await file_storage.download_and_save_file(
                result['video_url'], 
                video_path
            )
            print(f"💾 视频已保存: {video_path}")
            
            # 检查文件大小
            if os.path.exists(video_path):
                file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
                print(f"📊 文件大小: {file_size:.2f} MB")
            
    except Exception as e:
        print(f"❌ 视频生成失败: {e}")
        import traceback
        print(f"详细错误: {traceback.format_exc()}")


async def main():
    """主函数"""
    print("=" * 60)
    print("🧪 CogVideoX-3首尾帧视频生成测试（工具系统）")
    print("=" * 60)
    
    await test_first_last_frame_video()
    
    print("=" * 60)
    print("🏁 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
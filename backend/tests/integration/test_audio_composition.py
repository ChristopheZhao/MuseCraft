#!/usr/bin/env python3
"""
测试 AudioGenerator 的音频合成功能
"""
import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.audio_generator import AudioGeneratorAgent
from app.models import Task


async def test_audio_composition():
    """测试音频合成功能"""
    
    # 检查输入视频文件是否存在
    video_path = "./storage/generated/final_video_346.mp4"
    if not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        return False
        
    print(f"✅ 找到视频文件: {video_path}")
    
    # 创建 AudioGenerator 实例
    agent = AudioGeneratorAgent()
    
    try:
        print("🎵 测试通过工具获取视频时长...")
        calls_probe = [{
            "function": {
                "name": "ffmpeg_tool.get_video_info",
                "arguments": {"file_path": video_path}
            }
        }]
        executed_probe = await agent.execute_tool_calls(calls_probe)
        probe_rec = executed_probe[0] if executed_probe else {}
        probe_out = probe_rec.get("result")
        probe_payload = getattr(probe_out, 'result', probe_out) if probe_out is not None else None
        duration = float(probe_payload.get("duration", 0.0)) if isinstance(probe_payload, dict) else 0.0
        print(f"📹 视频时长: {duration:.1f}秒")
        
        # 创建一个模拟的背景音乐文件路径（用于测试）
        # 注意：这里我们需要一个真实的音频文件来测试合成功能
        print("⚠️ 需要一个音频文件来测试合成功能")
        print("💡 建议：")
        print("1. 先运行完整的工作流生成一个音频文件")
        print("2. 或者手动下载一个测试音频文件放到 storage/generated/ 目录")
        
        # 检查是否有现有的音频文件
        audio_files = []
        generated_dir = "./storage/generated/"
        if os.path.exists(generated_dir):
            for file in os.listdir(generated_dir):
                if file.endswith(('.mp3', '.wav', '.aac')):
                    audio_files.append(os.path.join(generated_dir, file))
        
        if audio_files:
            audio_path = audio_files[0]
            print(f"✅ 找到音频文件: {audio_path}")
            
            print("🎬 测试视频音频合成...")
            
            # 创建模拟的 execution 对象
            class MockExecution:
                def __init__(self):
                    self.id = "test_execution_123"
            
            mock_execution = MockExecution()
            
            # 测试合成功能
            output_filename = f"final_video_with_audio_{mock_execution.id}.mp4"
            calls = [{
                "function": {
                    "name": "ffmpeg_tool.add_audio",
                    "arguments": {
                        "video_file": video_path,
                        "audio_file": audio_path,
                        "output_filename": output_filename
                    }
                }
            }]
            executed = await agent.execute_tool_calls(calls)
            rec = executed[0] if executed else {}
            tool_out = rec.get("result")
            payload = getattr(tool_out, 'result', tool_out) if tool_out is not None else None
            output_path = payload.get("output_path") if isinstance(payload, dict) else None
            
            if output_path and os.path.exists(output_path):
                print(f"✅ 音频合成成功!")
                print(f"📹 输出文件: {output_path}")
                
                # 检查输出文件大小
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                print(f"📁 文件大小: {file_size:.2f}MB")
                
                return True
            else:
                print(f"❌ 音频合成失败: {output_path}")
                return False
        else:
            print("❌ 没有找到音频文件进行测试")
            print("💡 可以从这里下载一个测试音频:")
            print("   wget -O ./storage/generated/test_music.mp3 'https://www.soundjay.com/misc/sounds/bell-ringing-05.mp3'")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_ffprobe():
    """测试 FFprobe 工具是否可用"""
    
    video_path = "./storage/generated/final_video_346.mp4"
    if not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        return False
    
    try:
        import subprocess
        
        print("🔍 测试 FFprobe...")
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        
        print(f"✅ FFprobe 工作正常")
        print(f"📹 检测到的视频时长: {duration:.1f}秒")
        return True
        
    except FileNotFoundError:
        print("❌ FFprobe 未安装或不在 PATH 中")
        print("💡 请安装: sudo apt install ffmpeg")
        return False
    except Exception as e:
        print(f"❌ FFprobe 测试失败: {str(e)}")
        return False


async def main():
    """主测试函数"""
    
    print("=" * 50)
    print("🎵 AudioGenerator 音频合成功能测试")
    print("=" * 50)
    
    # 测试 FFprobe
    if not await test_ffprobe():
        return
    
    # 测试音频合成
    success = await test_audio_composition()
    
    if success:
        print("\n✅ 所有测试通过!")
    else:
        print("\n❌ 测试失败，请检查上面的错误信息")


if __name__ == "__main__":
    asyncio.run(main())

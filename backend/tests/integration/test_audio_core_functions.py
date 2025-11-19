#!/usr/bin/env python3
"""
测试 AudioGenerator 的核心功能
"""
import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.audio_generator import AudioGeneratorAgent


async def test_video_duration():
    """测试视频时长检测"""
    print("1️⃣ 测试视频时长检测...")
    
    video_path = "./storage/generated/final_video_346.mp4"
    if not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        return False
    
    agent = AudioGeneratorAgent()
    try:
        # 通过统一执行器执行 FC 规划的工具调用
        calls = [{
            "function": {
                "name": "ffmpeg_tool.get_video_info",
                "arguments": {"file_path": video_path}
            }
        }]
        executed = await agent.execute_tool_calls(calls)
        if not executed:
            print("   ❌ 工具未执行")
            return False
        rec = executed[0]
        tool_out = rec.get("result")
        payload = getattr(tool_out, 'result', tool_out) if tool_out is not None else None
        duration = float(payload.get("duration", 0.0)) if isinstance(payload, dict) else 0.0
        print(f"   ✅ 视频时长: {duration:.1f}秒")
        return duration > 0
    except Exception as e:
        print(f"   ❌ 时长检测失败: {e}")
        return False


async def test_audio_composition():
    """测试音频合成功能"""
    print("2️⃣ 测试音频合成功能...")
    
    video_path = "./storage/generated/final_video_346.mp4"
    audio_files = []
    
    # 寻找音频文件
    generated_dir = "./storage/generated/"
    if os.path.exists(generated_dir):
        for file in os.listdir(generated_dir):
            if file.endswith(('.mp3', '.wav', '.aac')):
                audio_files.append(os.path.join(generated_dir, file))
    
    if not audio_files:
        print("   ❌ 没有找到音频文件")
        return False
    
    audio_path = audio_files[0]
    print(f"   🎵 使用音频文件: {os.path.basename(audio_path)}")
    
    agent = AudioGeneratorAgent()
    
    try:
        # 创建模拟的 execution 对象
        class MockExecution:
            def __init__(self):
                self.id = "test_core_123"
        
        mock_execution = MockExecution()
        
        # 通过统一执行器执行音频合成
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
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"   ✅ 合成成功: {os.path.basename(output_path)}")
            print(f"   📁 文件大小: {file_size:.2f}MB")
            
            # 验证文件比原视频大（说明音频已添加）
            original_size = os.path.getsize(video_path) / (1024 * 1024)
            if file_size > original_size:
                print(f"   ✅ 文件大小验证通过 ({file_size:.1f}MB > {original_size:.1f}MB)")
                return True
            else:
                print(f"   ⚠️ 文件大小没有增加，可能音频未正确添加")
                return False
        else:
            print(f"   ❌ 合成失败: {output_path}")
            return False
            
    except Exception as e:
        print(f"   ❌ 合成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_music_requirements_extraction():
    """测试音乐需求提取"""
    print("3️⃣ 测试音乐需求提取...")
    
    audio_generator = AudioGeneratorAgent()
    
    # 模拟概念计划
    concept_plan = {
        "overview": "一只小老虎遇险记",
        "visual_style_guidance": {
            "color_palette": ["warm orange", "cool blues", "soft yellows"]
        },
        "target_audience": "家庭观众",
        "key_messages": ["友谊", "帮助他人", "勇气"]
    }
    
    # 模拟场景数据
    scenes_data = [
        {"mood_and_atmosphere": "playful", "duration": 5.0},
        {"mood_and_atmosphere": "energetic", "duration": 8.0},
        {"mood_and_atmosphere": "tense", "duration": 4.0},
        {"mood_and_atmosphere": "heartwarming", "duration": 4.0}
    ]
    
    video_metadata = {"duration": 21.0}
    
    try:
        requirements = audio_generator._extract_music_requirements(
            concept_plan, scenes_data, video_metadata
        )
        
        print(f"   ✅ 音乐标题: {requirements['title']}")
        print(f"   🎨 音乐风格: {requirements['style']}")
        print(f"   😊 音乐情绪: {requirements['mood']}")
        print(f"   ⏱️ 音乐时长: {requirements['duration']}秒")
        print(f"   🎵 主导情绪: {requirements['dominant_mood']}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 需求提取失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    
    print("🎵 AudioGenerator 核心功能测试")
    print("=" * 50)
    
    tests = [
        ("视频时长检测", test_video_duration),
        ("音频合成功能", test_audio_composition), 
        ("音乐需求提取", test_music_requirements_extraction)
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{name}:")
        try:
            result = await test_func()
            results.append(result)
        except Exception as e:
            print(f"   ❌ 测试异常: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print("📊 测试结果:")
    
    for i, (name, _) in enumerate(tests):
        status = "✅ 通过" if results[i] else "❌ 失败"
        print(f"   {name}: {status}")
    
    success_count = sum(results)
    total_count = len(results)
    
    if success_count == total_count:
        print(f"\n🎉 所有测试通过! ({success_count}/{total_count})")
        print("✅ AudioGenerator 核心功能正常")
        print("🚀 可以进行完整工作流程测试")
        return True
    else:
        print(f"\n⚠️ 部分测试失败 ({success_count}/{total_count})")
        return False


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
测试音频时长控制功能
验证生成的背景音乐能否与视频时长精确匹配
"""

import asyncio
import time
import os
import sys

async def test_audio_duration_control():
    """测试不同视频时长的音频生成和调整"""
    print("🎵 音频时长控制测试")
    print("=" * 70)
    
    # 测试不同的视频时长场景
    test_scenarios = [
        {
            "name": "短视频",
            "video_duration": 15.0,
            "description": "Create uplifting background music for a 15-second social media video",
            "expected_suno_duration": "短时长音乐"
        },
        {
            "name": "标准视频", 
            "video_duration": 30.0,
            "description": "Create cinematic background music for a 30-second advertisement",
            "expected_suno_duration": "标准时长音乐"
        },
        {
            "name": "长视频",
            "video_duration": 90.0, 
            "description": "Create ambient background music for a 90-second tutorial video",
            "expected_suno_duration": "长时长音乐"
        }
    ]
    
    from app.agents.tools.ai_services.suno_client import SunoClientTool
    from app.agents.tools.base_tool import ToolInput
    
    # 创建Suno客户端
    tool = SunoClientTool(config={
        "use_callback": False,
        "polling_interval": 30,
        "max_polling_attempts": 15
    })
    
    if not tool._functional:
        print("❌ Suno API未配置，无法测试")
        return False
    
    print("🧪 开始时长控制测试...")
    
    results = []
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n📹 测试场景 {i}/3: {scenario['name']}")
        print(f"   🎯 目标时长: {scenario['video_duration']}秒")
        print(f"   📝 描述: {scenario['description']}")
        
        # 构建音乐参数
        music_params = {
            "description": scenario["description"],
            "mood": "uplifting",
            "style": "cinematic",
            "duration": scenario["video_duration"],  # 传递目标时长
            "instrumental": True,
            "title": f"Test Music - {scenario['name']}"
        }
        
        tool_input = ToolInput(
            action="generate_background_music",
            timeout=300,
            parameters=music_params
        )
        
        print(f"   🎶 开始生成音乐... ({time.strftime('%H:%M:%S')})")
        start_time = time.time()
        
        try:
            result = await tool.execute(tool_input)
            elapsed_time = time.time() - start_time
            
            if result.success:
                audio_data = result.result
                generated_duration = audio_data.get("duration", 0)
                audio_url = audio_data.get("audio_url", "")
                
                # 计算时长匹配度
                duration_diff = abs(generated_duration - scenario["video_duration"])
                duration_match = duration_diff <= 5.0  # 5秒误差内认为匹配
                
                print(f"   ✅ 生成成功！用时: {elapsed_time:.1f}秒")
                print(f"   📊 结果分析:")
                print(f"      目标时长: {scenario['video_duration']}秒")
                print(f"      生成时长: {generated_duration}秒") 
                print(f"      时长差异: {duration_diff:.1f}秒")
                print(f"      匹配状态: {'✅ 匹配' if duration_match else '❌ 不匹配'}")
                
                if audio_url:
                    print(f"      🔗 音频URL: {audio_url[:60]}...")
                
                # 记录结果
                scenario_result = {
                    "scenario": scenario["name"],
                    "target_duration": scenario["video_duration"],
                    "generated_duration": generated_duration,
                    "duration_diff": duration_diff,
                    "duration_match": duration_match,
                    "generation_time": elapsed_time,
                    "success": True,
                    "audio_url": audio_url
                }
                
                # 如果时长不匹配，测试音频后处理
                if not duration_match and audio_url:
                    print(f"   🔧 时长不匹配，测试音频调整功能...")
                    adjustment_result = await test_audio_adjustment(
                        audio_url, scenario["video_duration"], scenario["name"]
                    )
                    scenario_result.update(adjustment_result)
                
                results.append(scenario_result)
                
            else:
                print(f"   ❌ 生成失败！用时: {elapsed_time:.1f}秒")
                print(f"   错误: {result.error}")
                
                results.append({
                    "scenario": scenario["name"],
                    "target_duration": scenario["video_duration"], 
                    "success": False,
                    "error": result.error,
                    "generation_time": elapsed_time
                })
        
        except Exception as e:
            elapsed_time = time.time() - start_time
            print(f"   ❌ 测试异常！用时: {elapsed_time:.1f}秒")
            print(f"   异常: {str(e)}")
            
            results.append({
                "scenario": scenario["name"],
                "target_duration": scenario["video_duration"],
                "success": False,
                "error": str(e),
                "generation_time": elapsed_time
            })
        
        # 每个测试之间暂停一下，避免API限制
        if i < len(test_scenarios):
            print(f"   ⏳ 等待10秒后进行下一个测试...")
            await asyncio.sleep(10)
    
    return results


async def test_audio_adjustment(audio_url: str, target_duration: float, scenario_name: str):
    """测试音频时长调整功能"""
    
    try:
        from app.services.file_storage import FileStorageService
        
        # 下载音频文件用于调整测试
        file_storage = FileStorageService()
        filename = f"test_audio_{scenario_name.lower().replace(' ', '_')}.mp3"
        
        print(f"      📥 下载音频文件进行调整测试...")
        downloaded_path = await file_storage.download_and_save_audio(audio_url, filename)
        
        if not downloaded_path or not os.path.exists(downloaded_path):
            return {"adjustment_success": False, "adjustment_error": "Download failed"}
        
        # 检查FFmpeg是否可用
        import subprocess
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except:
            return {"adjustment_success": False, "adjustment_error": "FFmpeg not available"}
        
        # 获取原始音频时长
        duration_cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0", downloaded_path
        ]
        
        result = subprocess.run(duration_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {"adjustment_success": False, "adjustment_error": "Cannot get audio duration"}
        
        original_duration = float(result.stdout.strip())
        print(f"      📏 原始音频时长: {original_duration:.1f}秒")
        
        # 生成调整后的文件路径
        adjusted_path = downloaded_path.replace(".mp3", f"_adjusted_{int(target_duration)}s.mp3")
        
        # 选择调整方法
        if original_duration > target_duration:
            # 裁剪音频
            print(f"      ✂️ 裁剪音频: {original_duration:.1f}s → {target_duration:.1f}s")
            fade_out_start = max(0, target_duration - 1.0)
            
            cmd = [
                "ffmpeg", "-y",
                "-i", downloaded_path,
                "-t", str(target_duration),
                "-af", f"afade=t=out:st={fade_out_start}:d=1.0",
                "-c:a", "libmp3lame",
                adjusted_path
            ]
        
        else:
            # 循环音频
            print(f"      🔄 循环音频: {original_duration:.1f}s → {target_duration:.1f}s")
            loop_count = int(target_duration / original_duration) + 1
            
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", str(loop_count),
                "-i", downloaded_path, 
                "-t", str(target_duration),
                "-af", f"afade=t=in:ss=0:d=1.0,afade=t=out:st={target_duration-1.0}:d=1.0",
                "-c:a", "libmp3lame",
                adjusted_path
            ]
        
        # 执行音频调整
        process = subprocess.run(cmd, capture_output=True)
        
        if process.returncode != 0:
            error_msg = process.stderr.decode() if process.stderr else "Unknown FFmpeg error"
            return {"adjustment_success": False, "adjustment_error": error_msg}
        
        # 验证调整结果
        if os.path.exists(adjusted_path):
            # 获取调整后的时长
            result = subprocess.run(duration_cmd[:-1] + [adjusted_path], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                final_duration = float(result.stdout.strip())
                duration_diff = abs(final_duration - target_duration)
                
                print(f"      ✅ 音频调整成功!")
                print(f"         调整后时长: {final_duration:.1f}秒")
                print(f"         时长差异: {duration_diff:.1f}秒")
                print(f"         调整文件: {os.path.basename(adjusted_path)}")
                
                return {
                    "adjustment_success": True,
                    "original_duration": original_duration,
                    "adjusted_duration": final_duration,
                    "final_duration_diff": duration_diff,
                    "adjusted_path": adjusted_path,
                    "adjustment_method": "trim" if original_duration > target_duration else "loop"
                }
        
        return {"adjustment_success": False, "adjustment_error": "Adjusted file not created"}
        
    except Exception as e:
        return {"adjustment_success": False, "adjustment_error": str(e)}


async def main():
    """主函数"""
    print("🚀 启动音频时长控制完整测试")
    print(f"📅 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 检查API配置
    from app.core.config import settings
    if not settings.SUNO_API_KEY:
        print("❌ SUNO_API_KEY未配置")
        return
    
    # 运行测试
    results = await test_audio_duration_control()
    
    if not results:
        print("❌ 未获取到任何测试结果")
        return
    
    # 分析测试结果
    print("\n" + "=" * 70)
    print("📊 测试结果汇总")
    print("=" * 70)
    
    successful_tests = [r for r in results if r.get("success")]
    failed_tests = [r for r in results if not r.get("success")]
    matched_durations = [r for r in successful_tests if r.get("duration_match")]
    
    print(f"✅ 成功生成音乐: {len(successful_tests)}/{len(results)}")
    print(f"🎯 时长精确匹配: {len(matched_durations)}/{len(successful_tests)}")
    
    if successful_tests:
        avg_generation_time = sum(r["generation_time"] for r in successful_tests) / len(successful_tests)
        print(f"⏱️  平均生成时间: {avg_generation_time:.1f}秒")
    
    # 详细结果
    print(f"\n📝 详细结果:")
    for result in results:
        scenario = result["scenario"]
        if result["success"]:
            duration_status = "✅ 匹配" if result.get("duration_match") else "⚠️ 需调整"
            print(f"   {scenario}: {duration_status}")
            print(f"      目标: {result['target_duration']}s, 生成: {result.get('generated_duration', 0)}s")
            
            # 显示调整结果
            if result.get("adjustment_success"):
                adj_method = result.get("adjustment_method", "unknown")
                adj_duration = result.get("adjusted_duration", 0)
                print(f"      调整: {adj_method} → {adj_duration:.1f}s ✅")
            elif "adjustment_success" in result and not result["adjustment_success"]:
                print(f"      调整: 失败 - {result.get('adjustment_error', 'Unknown error')}")
        else:
            print(f"   {scenario}: ❌ 失败 - {result.get('error', 'Unknown error')}")
    
    # 结论和建议
    print(f"\n💡 测试结论:")
    if len(matched_durations) == len(successful_tests):
        print("   🎉 所有生成的音乐都精确匹配目标时长!")
    elif len(matched_durations) > len(successful_tests) // 2:
        print("   👍 大部分音乐匹配目标时长，音频调整功能可补足")
    else:
        print("   ⚠️  时长匹配率较低，建议:")
        print("       1. 🔧 优化Suno提示词中的时长控制")
        print("       2. 🎵 依赖音频后处理确保精确时长")
        print("       3. 🔄 考虑多次生成选择最佳匹配")
    
    print(f"\n🎬 视频制作建议:")
    print("   1. ✅ Suno可生成质量优秀的背景音乐")
    print("   2. 🎯 时长控制通过提示词 + FFmpeg后处理实现")
    print("   3. 🔄 对于重要项目，可生成多个版本选择最佳")
    print("   4. ⚡ 整个音频生成+调整流程约1-2分钟")


if __name__ == "__main__":
    asyncio.run(main())
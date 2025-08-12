#!/usr/bin/env python3
"""
独立测试视频合成功能
测试VideoComposer的核心FFmpeg合成逻辑
"""
import asyncio
import os
import glob
from pathlib import Path

# 添加项目路径
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.video_composer import VideoComposerAgent
from app.services.file_storage import FileStorageService

async def test_video_composition():
    """测试视频合成功能"""
    
    # 初始化
    composer = VideoComposerAgent()
    file_storage = FileStorageService()
    
    # 获取已生成的场景视频
    video_dir = "./storage/generated"
    scene_videos = []
    
    # 查找场景视频文件
    for i in range(1, 5):  # 假设有4个场景
        pattern = f"{video_dir}/scene_{i}_video.mp4"
        matches = glob.glob(pattern)
        if matches:
            scene_videos.append(matches[0])
            print(f"✅ Found scene {i} video: {matches[0]}")
        else:
            print(f"❌ Scene {i} video not found")
    
    if len(scene_videos) < 2:
        print("\n❌ Need at least 2 scene videos to test composition")
        return False
    
    print(f"\n🎬 Testing composition of {len(scene_videos)} videos...")
    
    # 测试输出路径
    output_path = f"{video_dir}/test_composed_video.mp4"
    
    try:
        # 调用FFmpeg合成方法
        success = await composer._ffmpeg_concat_videos(scene_videos, output_path)
        
        if success and os.path.exists(output_path):
            file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
            print(f"\n✅ Video composition successful!")
            print(f"📹 Output file: {output_path}")
            print(f"📊 File size: {file_size:.2f} MB")
            
            # 使用ffprobe获取视频信息（如果可用）
            try:
                process = await asyncio.create_subprocess_exec(
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    output_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await process.communicate()
                if process.returncode == 0:
                    duration = float(stdout.decode().strip())
                    print(f"⏱️ Duration: {duration:.2f} seconds")
            except:
                print("ℹ️ ffprobe not available for duration check")
                
            return True
        else:
            print("\n❌ Video composition failed")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during composition: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def test_simple_concat():
    """测试简单的FFmpeg concat命令"""
    
    video_dir = "./storage/generated"
    scene_videos = glob.glob(f"{video_dir}/scene_*_video.mp4")
    scene_videos.sort()  # 确保顺序
    
    if len(scene_videos) < 2:
        print("❌ Not enough videos for testing")
        return
    
    print(f"\n🔧 Testing simple FFmpeg concat with {len(scene_videos)} videos:")
    for v in scene_videos:
        print(f"  - {v}")
    
    # 创建concat文件
    concat_file = "/tmp/test_concat.txt"
    with open(concat_file, 'w') as f:
        for video in scene_videos:
            f.write(f"file '{os.path.abspath(video)}'\n")
    
    output_path = f"{video_dir}/test_simple_concat.mp4"
    
    # 执行FFmpeg命令
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        output_path
    ]
    
    print(f"\n📝 Running command: {' '.join(cmd)}")
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode == 0:
        print(f"\n✅ Simple concat successful!")
        print(f"📹 Output: {output_path}")
        if os.path.exists(output_path):
            size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"📊 Size: {size:.2f} MB")
    else:
        print(f"\n❌ Simple concat failed!")
        print(f"Error: {stderr.decode()}")
    
    # 清理
    if os.path.exists(concat_file):
        os.unlink(concat_file)

async def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 Video Composer Tool Test")
    print("=" * 60)
    
    # 检查FFmpeg
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        if process.returncode == 0:
            version_line = stdout.decode().split('\n')[0]
            print(f"✅ FFmpeg installed: {version_line}")
        else:
            print("❌ FFmpeg check failed")
            return
    except FileNotFoundError:
        print("❌ FFmpeg not found!")
        return
    
    # 测试1: VideoComposer的合成方法
    print("\n" + "=" * 60)
    print("📋 Test 1: VideoComposer _ffmpeg_concat_videos method")
    print("=" * 60)
    await test_video_composition()
    
    # 测试2: 简单的FFmpeg concat
    print("\n" + "=" * 60)
    print("📋 Test 2: Simple FFmpeg concat command")
    print("=" * 60)
    await test_simple_concat()
    
    print("\n" + "=" * 60)
    print("🏁 Test completed!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
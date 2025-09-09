#!/usr/bin/env python3
"""
视频尾帧提取工具
支持WSL环境下处理Windows路径的视频文件
"""

import os
import sys
import argparse
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any


class VideoFrameExtractor:
    """视频帧提取器"""
    
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
    
    def convert_windows_path_to_wsl(self, windows_path: str) -> str:
        """将Windows路径转换为WSL路径"""
        # 处理类似 C:\\Users\\... 的路径
        if windows_path[1:3] == ':\\\':
            drive = windows_path[0].lower()
            path = windows_path[3:].replace('\\\\', '/')
            return f"/mnt/{drive}/{path}"
        return windows_path
    
    async def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """获取视频信息"""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",
            "-show_streams", video_path
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            
            if process.returncode != 0:
                raise RuntimeError(f"ffprobe failed: {stderr.decode()}")
            
            import json
            info = json.loads(stdout.decode())
            
            # 提取视频流信息
            video_stream = None
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break
            
            if not video_stream:
                raise RuntimeError("No video stream found")
            
            duration = float(info.get("format", {}).get("duration", 0))
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            
            return {
                "duration": duration,
                "width": width,
                "height": height
            }
        except asyncio.TimeoutError:
            raise RuntimeError("Video info extraction timeout")
        except Exception as e:
            raise RuntimeError(f"Failed to get video info: {str(e)}")
    
    async def extract_last_frame(
        self, 
        video_path: str, 
        output_path: Optional[str] = None,
        output_format: str = "jpg",
        quality: int = 2,
        time_tolerance: float = 0.1
    ) -> str:
        """提取视频尾帧"""
        
        # 转换Windows路径到WSL路径
        wsl_video_path = self.convert_windows_path_to_wsl(video_path)
        
        # 检查文件是否存在
        if not os.path.exists(wsl_video_path):
            raise FileNotFoundError(f"Video file not found: {wsl_video_path}")
        
        # 获取视频信息
        print(f"获取视频信息: {wsl_video_path}")
        info = await self.get_video_info(wsl_video_path)
        duration = info["duration"]
        print(f"视频时长: {duration:.2f}秒")
        print(f"视频尺寸: {info['width']}x{info['height']}")
        
        # 计算提取时间点（接近尾部但不是最后一帧，避免黑帧）
        extract_time = max(duration - time_tolerance, 0.0)
        print(f"提取时间点: {extract_time:.2f}秒")
        
        # 确定输出路径
        if not output_path:
            video_name = Path(wsl_video_path).stem
            output_path = f"{video_name}_last_frame.{output_format}"
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path) or "."
        os.makedirs(output_dir, exist_ok=True)
        
        # 构建ffmpeg命令
        cmd = [
            "ffmpeg", "-y",  # 覆盖输出文件
            "-ss", f"{extract_time}",  # 跳转到指定时间
            "-i", wsl_video_path,  # 输入文件
            "-frames:v", "1",  # 只提取一帧
        ]
        
        # 添加质量参数（仅对JPEG有效）
        if output_format.lower() == "jpg":
            cmd += ["-q:v", str(quality)]
        
        cmd.append(output_path)
        
        print(f"执行命令: {' '.join(cmd)}")
        
        # 执行ffmpeg命令
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            
            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg extraction failed: {stderr.decode()}")
            
            # 检查输出文件是否生成
            if not os.path.exists(output_path):
                raise RuntimeError("Output frame file was not created")
            
            file_size = os.path.getsize(output_path)
            print(f"✅ 成功提取尾帧: {output_path}")
            print(f"文件大小: {file_size} bytes")
            
            return output_path
            
        except asyncio.TimeoutError:
            raise RuntimeError("Frame extraction timeout")
        except Exception as e:
            raise RuntimeError(f"Frame extraction failed: {str(e)}")


async def main():
    parser = argparse.ArgumentParser(description="提取视频尾帧工具")
    parser.add_argument("video_path", help="视频文件路径（支持Windows路径）")
    parser.add_argument("-o", "--output", help="输出文件路径")
    parser.add_argument("-f", "--format", default="jpg", choices=["jpg", "png"], help="输出格式")
    parser.add_argument("-q", "--quality", type=int, default=2, help="JPEG质量 (1-31, 数字越小质量越高)")
    parser.add_argument("-t", "--tolerance", type=float, default=0.1, help="距离视频结尾的时间容差（秒）")
    parser.add_argument("--timeout", type=int, default=60, help="操作超时时间（秒）")
    
    args = parser.parse_args()
    
    # 检查ffmpeg和ffprobe是否可用
    for tool in ["ffmpeg", "ffprobe"]:
        try:
            subprocess.run([tool, "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"❌ 错误: {tool} 未安装或不在PATH中")
            print("请安装ffmpeg: sudo apt update && sudo apt install ffmpeg")
            sys.exit(1)
    
    extractor = VideoFrameExtractor(timeout=args.timeout)
    
    try:
        output_path = await extractor.extract_last_frame(
            video_path=args.video_path,
            output_path=args.output,
            output_format=args.format,
            quality=args.quality,
            time_tolerance=args.tolerance
        )
        print(f"🎉 提取完成: {os.path.abspath(output_path)}")
        
    except Exception as e:
        print(f"❌ 提取失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


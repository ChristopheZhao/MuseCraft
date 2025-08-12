#!/usr/bin/env python3
"""
测试首帧图像解读功能
"""

import asyncio
import os
import sys
import base64
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.agents.video_generator import VideoGeneratorAgent

class MockSceneData:
    """模拟场景数据"""
    def __init__(self):
        self.scene_number = 5
        self.description = "切西瓜场景"
        self.visual_description = "银色厨师刀和西瓜的静态场景"

async def test_image_analysis():
    """测试图像分析功能"""
    
    # 创建VideoGenerator实例
    video_generator = VideoGeneratorAgent()
    
    # 初始化Agent（这会自动初始化工具）
    await video_generator._initialize_agent()
    
    # 图片文件路径（使用绝对路径）
    image_path = "/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/storage/generated/scene_5_first_frame.jpg"
    
    # 检查文件是否存在
    if not os.path.exists(image_path):
        print(f"❌ 图片文件不存在: {image_path}")
        return
    
    # 将本地图片转换为base64格式
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{image_base64}"
        print(f"🔍 开始分析图片: {image_path}")
        print(f"📁 图片大小: {len(image_data)} bytes")
    except Exception as e:
        print(f"❌ 读取图片文件失败: {str(e)}")
        return
    
    print("-" * 60)
    
    # 创建模拟场景数据
    scene_data = MockSceneData()
    
    try:
        # 调用图像分析方法（使用base64编码的图像）
        description = await video_generator._analyze_first_frame_image(image_url, scene_data)
        
        print("✅ 图像分析成功！")
        print()
        print("📋 分析结果：")
        print(description)
        print()
        print("-" * 60)
        
    except Exception as e:
        print(f"❌ 图像分析失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_image_analysis())
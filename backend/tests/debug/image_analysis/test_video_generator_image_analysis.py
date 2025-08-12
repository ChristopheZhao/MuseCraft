#!/usr/bin/env python3
"""
测试VideoGeneratorAgent的图像分析功能
"""

import asyncio
import os
import sys
import base64
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

class MockSceneData:
    """模拟场景数据"""
    def __init__(self, scene_number, description):
        self.scene_number = scene_number
        self.description = description

async def test_video_generator_analysis():
    """测试VideoGenerator的图像分析功能"""
    
    from app.agents.video_generator import VideoGeneratorAgent
    
    print("🎬 测试VideoGeneratorAgent图像分析功能")
    print("=" * 60)
    
    # 测试图片路径
    test_image = "./storage/generated/scene_5_first_frame.jpg"
    
    if not os.path.exists(test_image):
        print(f"❌ 测试图片不存在: {test_image}")
        return
    
    # 创建VideoGenerator实例
    video_generator = VideoGeneratorAgent()
    
    print(f"📋 分析图片: {test_image}")
    print("-" * 40)
    
    # 将图片转换为base64格式
    try:
        with open(test_image, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{image_base64}"
        print(f"✅ 图片读取成功，大小: {len(image_data)} bytes")
    except Exception as e:
        print(f"❌ 读取图片失败: {str(e)}")
        return
    
    # 创建场景数据
    scene_data = MockSceneData(5, "切西瓜的厨房场景")
    
    try:
        # 调用图像分析方法
        print("\n🔍 开始分析图像...")
        analysis_result = await video_generator._analyze_first_frame_image(image_url, scene_data)
        
        print("✅ 图像分析完成！")
        print("\n📋 分析结果：")
        print("-" * 40)
        print(analysis_result)
        print("-" * 40)
        
        # 测试视频提示词生成（模拟部分参数）
        print("\n🎥 测试视频提示词生成...")
        
        # 模拟场景数据
        mock_template_data = {
            "image_prompt": "西瓜和水果刀在大理石台面上的厨房场景",
            "title": "切西瓜场景",
            "description": "展示切西瓜的过程",
            "duration": 5,
            "user_prompt": "制作一个切西瓜的短视频",
            "overall_duration": 15,
            "video_style": "真实",
            "scene_physics_type": {"physics_constraints": "strict"},
            "first_frame_actual_content": analysis_result,
            "max_prompt_length": 500
        }
        
        # 渲染模板
        video_prompt = await video_generator.render_prompt("video_generator/enhanced_video_generation", mock_template_data)
        
        print("✅ 视频提示词生成完成！")
        print("\n📝 生成的视频提示词：")
        print("=" * 60)
        print(video_prompt)
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n🎯 测试完成")

if __name__ == "__main__":
    asyncio.run(test_video_generator_analysis())
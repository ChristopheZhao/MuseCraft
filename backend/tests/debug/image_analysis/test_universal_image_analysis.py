#!/usr/bin/env python3
"""
测试通用图像实体分析功能
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

async def test_universal_image_analysis():
    """测试通用图像实体分析"""
    
    from app.agents.video_generator import VideoGeneratorAgent
    
    print("🔍 测试通用图像实体分析功能")
    print("=" * 60)
    
    # 测试不同场景的图片
    test_cases = [
        {"file": "./storage/generated/scene_5_first_frame.jpg", "desc": "切西瓜场景"},
        {"file": "./storage/generated/scene_1_first_frame.jpg", "desc": "场景1"},
        {"file": "./storage/generated/scene_3_first_frame.jpg", "desc": "场景3"},
    ]
    
    # 创建VideoGenerator实例
    video_generator = VideoGeneratorAgent()
    
    for i, test_case in enumerate(test_cases, 1):
        image_path = test_case["file"]
        description = test_case["desc"]
        
        print(f"\n📋 测试 {i}/3: {description}")
        print("-" * 40)
        
        # 检查文件是否存在
        if not os.path.exists(image_path):
            print(f"❌ 图片不存在: {image_path}")
            continue
        
        # 将图片转换为base64格式
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                image_url = f"data:image/jpeg;base64,{image_base64}"
            print(f"✅ 图片读取成功，大小: {len(image_data)} bytes")
        except Exception as e:
            print(f"❌ 读取图片失败: {str(e)}")
            continue
        
        # 创建场景数据
        scene_data = MockSceneData(i, description)
        
        try:
            # 调用通用图像分析方法
            analysis_result = await video_generator._analyze_first_frame_image(image_url, scene_data)
            
            print("✅ 图像分析完成！")
            print()
            print("📋 实体分析结果：")
            print(analysis_result)
            print()
            
        except Exception as e:
            print(f"❌ 图像分析失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🎯 通用图像实体分析测试完成")

if __name__ == "__main__":
    asyncio.run(test_universal_image_analysis())
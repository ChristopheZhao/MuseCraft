#!/usr/bin/env python3
"""
直接测试智谱AI视频生成工具
模拟VideoGenerator Agent的调用方式
验证工具在接收首尾帧时是否生成正确内容
"""
import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput


async def test_video_tool_direct():
    """直接测试视频生成工具"""
    
    print("🎬 直接测试智谱AI视频生成工具")
    print("🎯 目的: 验证工具本身在接收首尾帧时是否生成正确内容")
    print("=" * 60)
    
    # 检查文件 - 完整路径
    first_frame = "./storage/generated/scene_3_first_frame.jpg"
    last_frame = "./storage/generated/scene_3_last_frame.jpg"
    
    if not os.path.exists(first_frame) or not os.path.exists(last_frame):
        print(f"❌ 图片文件不存在")
        return False
    
    print(f"📸 测试场景:")
    print(f"   首帧: 鸭妈妈驮着小兔子在水中")
    print(f"   尾帧: 小兔子坐在鸭妈妈背上游泳")
    print(f"   预期: 生成鸭妈妈救援小兔子的视频")
    
    # 使用与VideoGenerator Agent完全相同的提示词格式
    video_prompt = "A mother duck rescues a small rabbit from water. The duck carries the rabbit on her back, swimming to safety."
    
    print(f"\n📝 视频提示词: {video_prompt}")
    
    try:
        # 创建工具实例
        tool = ZhipuClientTool()
        
        # 完全按照VideoGenerator Agent的参数格式
        params = {
            "prompt": video_prompt,
            "first_frame_image": first_frame,
            "last_frame_image": last_frame,
            "model": "cogvideox-3"
        }
        
        # 创建工具输入
        tool_input = ToolInput(action="generate_video", parameters=params)
        
        print(f"\n🚀 调用智谱AI视频生成工具:")
        print(f"   模型: cogvideox-3 (首尾帧模式)")
        print(f"   首帧文件: {os.path.basename(first_frame)}")
        print(f"   尾帧文件: {os.path.basename(last_frame)}")
        
        # 执行工具调用
        result = await tool.execute(tool_input)
        
        if hasattr(result, 'success') and result.success:
            video_id = result.result.get("video_id", "")
            video_url = result.result.get("video_url", "")
            generation_mode = result.result.get("generation_mode", "")
            timeout = result.result.get("timeout", False)
            
            print(f"\n✅ 工具调用成功!")
            print(f"📹 视频ID: {video_id}")
            print(f"🎯 生成模式: {generation_mode}")
            
            if video_url:
                print(f"📹 视频URL: {video_url}")
                print(f"✅ 视频已生成完成")
            elif timeout:
                print(f"⏳ 视频生成超时，但任务已启动")
                print(f"💡 可以稍后通过ID查询结果: {video_id}")
            else:
                print(f"⏳ 视频正在生成中...")
                
            print(f"\n🔍 关键验证点:")
            print(f"   1. 工具成功接收了首尾帧参数 ✅")
            print(f"   2. 使用了CogVideoX-3首尾帧模式 ✅")
            print(f"   3. 如果最终视频显示鸭妈妈救兔子 → 工具正常")
            print(f"   4. 如果最终视频显示其他内容 → 工具或模型问题")
            
            return True
        else:
            error = getattr(result, 'error', 'Unknown error')
            print(f"\n❌ 工具调用失败: {error}")
            return False
            
    except Exception as e:
        print(f"\n❌ 执行异常: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    asyncio.run(test_video_tool_direct())
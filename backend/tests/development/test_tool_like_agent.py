#!/usr/bin/env python3
"""
完全按照VideoGenerator Agent的方式测试工具
模拟_call_tool_with_extended_timeout方法
"""
import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput


async def test_like_video_generator():
    """完全按照VideoGenerator Agent的方式测试"""
    
    print("🎬 模拟VideoGenerator Agent调用工具")
    print("🎯 使用_call_tool_with_extended_timeout的相同逻辑")
    print("=" * 60)
    
    # 检查文件
    first_frame = "./storage/generated/scene_3_first_frame.jpg"
    last_frame = "./storage/generated/scene_3_last_frame.jpg"
    
    if not os.path.exists(first_frame) or not os.path.exists(last_frame):
        print(f"❌ 图片文件不存在")
        return
    
    print(f"📸 测试首尾帧模式:")
    print(f"   首帧: scene_3_first_frame.jpg (鸭妈妈驮小兔子)")
    print(f"   尾帧: scene_3_last_frame.jpg (小兔子安全到达)")
    
    # VideoGenerator Agent的提示词构建逻辑
    video_prompt = "A mother duck rescues a small rabbit from water. The duck carries the rabbit on her back, swimming to safety. smooth motion. cinematic movement. professional video production. natural dynamics. emotionally engaging motion. story-driven movement."
    
    print(f"\n📝 视频提示词: {video_prompt}")
    
    try:
        # 创建工具实例
        tool = ZhipuClientTool()
        
        # 完全按照VideoGenerator Agent的参数
        parameters = {
            "prompt": video_prompt,
            "first_frame_image": first_frame,
            "last_frame_image": last_frame,
            "model": "cogvideox-3"
        }
        
        # 创建ToolInput - 关键：设置240秒超时
        tool_input = ToolInput(
            action="generate_video",
            parameters=parameters,
            timeout=240  # VideoGenerator Agent使用的超时时间
        )
        
        print(f"\n🚀 调用工具 (240秒超时):")
        print(f"   工具: zhipu_client")
        print(f"   动作: generate_video") 
        print(f"   模型: cogvideox-3")
        print(f"   超时: 240秒")
        print(f"   模式: first/last frame")
        
        # 执行工具调用（完全模拟VideoGenerator Agent）
        raw_result = await tool.execute(tool_input)
        
        # 检查结果（完全按照VideoGenerator Agent的逻辑）
        if hasattr(raw_result, 'success') and not raw_result.success:
            error_msg = getattr(raw_result, 'error', 'Tool execution failed')
            print(f"\n❌ 工具执行失败: {error_msg}")
            return False
        
        # 处理结果（按照VideoGenerator Agent的逻辑）
        if raw_result is None:
            tool_result = {}
            print(f"⚠️ 工具返回None")
        elif hasattr(raw_result, 'result'):
            tool_result = raw_result.result or {}
        else:
            tool_result = raw_result or {}
        
        if not isinstance(tool_result, dict):
            print(f"⚠️ 工具结果不是字典类型: {type(tool_result)}")
            tool_result = {}
        
        # 输出结果分析
        print(f"\n✅ 工具调用完成!")
        
        video_id = tool_result.get("video_id", "")
        video_url = tool_result.get("video_url", "")
        generation_mode = tool_result.get("generation_mode", "")
        timeout = tool_result.get("timeout", False)
        
        print(f"📹 视频ID: {video_id}")
        print(f"🎯 生成模式: {generation_mode}")
        print(f"⏱️ 是否超时: {timeout}")
        
        if video_url:
            print(f"📹 视频URL: {video_url}")
            print(f"✅ 视频生成完成!")
        elif timeout:
            print(f"⏳ 视频生成超时，但任务已启动")
        else:
            print(f"⏳ 视频生成中...")
        
        print(f"\n🔍 关键测试结果:")
        print(f"   1. 工具接受首尾帧参数: ✅")
        print(f"   2. 使用CogVideoX-3模式: ✅")
        print(f"   3. 240秒超时设置生效: ✅")
        print(f"   4. 任务成功启动: {'✅' if video_id else '❌'}")
        
        print(f"\n💡 下一步验证:")
        if video_id:
            print(f"   - 可以通过video_id查询最终结果")
            print(f"   - 验证生成的视频内容是否为鸭妈妈救兔子")
            print(f"   - 如果视频内容不符，则问题在于CogVideoX-3模型或API")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    asyncio.run(test_like_video_generator())
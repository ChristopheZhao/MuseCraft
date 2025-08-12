#!/usr/bin/env python3
"""
专门测试Suno音乐生成功能，避免其他工具初始化干扰
"""

import asyncio
import time
import os
import sys

# 设置最小化日志，减少干扰
import logging
logging.getLogger("tool.jimeng_image").setLevel(logging.ERROR)
logging.getLogger("tool.minimax_video").setLevel(logging.ERROR)  
logging.getLogger("tool.oss_storage").setLevel(logging.ERROR)

async def test_suno_pure_polling():
    """测试纯轮询方式，绕过回调机制"""
    print("🎵 Suno音乐生成测试 - 纯轮询模式")
    print("=" * 60)
    
    # 直接导入需要的类
    from app.agents.tools.ai_services.suno_client import SunoClientTool
    from app.agents.tools.base_tool import ToolInput
    
    # 创建工具实例（修改配置使用纯轮询）
    tool = SunoClientTool(config={
        "use_callback": False,  # 禁用回调
        "polling_interval": 10,  # 10秒轮询一次
        "max_polling_attempts": 30  # 最多轮询30次（5分钟）
    })
    
    print(f"✅ 工具已初始化")
    print(f"🔑 API Key: {tool.api_key[:20]}..." if tool.api_key else "❌ No API Key")
    
    if not tool._functional:
        print("❌ 工具不可用，请检查API Key配置")
        return False
    
    # 测试参数
    test_params = {
        "description": "轻松愉快的背景音乐，适合展示美好生活",
        "mood": "happy",
        "style": "acoustic", 
        "duration": 30,  # 30秒
        "instrumental": True,
        "title": "Happy Life Background"
    }
    
    print("\n📝 生成参数:")
    for key, value in test_params.items():
        print(f"   {key}: {value}")
    
    # 创建测试输入
    test_input = ToolInput(
        action="generate_background_music",
        timeout=300,  # 5分钟超时
        parameters=test_params
    )
    
    print(f"\n🎶 开始生成音乐...")
    print(f"⏰ 开始时间: {time.strftime('%H:%M:%S')}")
    print("⏳ 预计需要1-3分钟，请耐心等待...")
    
    start_time = time.time()
    
    try:
        # 执行音乐生成
        result = await tool.execute(test_input)
        
        elapsed_time = time.time() - start_time
        
        if result.success:
            print(f"\n🎉 音乐生成成功！用时: {elapsed_time:.1f}秒")
            print("=" * 60)
            
            audio_data = result.result
            print("📊 生成结果:")
            print(f"   📝 标题: {audio_data.get('title', 'Unknown')}")
            print(f"   🎨 风格: {audio_data.get('style', 'Unknown')}")
            print(f"   🎭 情绪: {audio_data.get('mood', 'Unknown')}")
            print(f"   ⏱️  时长: {audio_data.get('duration', 0)}秒")
            print(f"   🎵 纯音乐: {'是' if audio_data.get('instrumental') else '否'}")
            print(f"   🆔 任务ID: {audio_data.get('task_id', 'None')}")
            print(f"   🔗 音频URL: {audio_data.get('audio_url', 'None')}")
            
            if audio_data.get('audio_url'):
                print("\n✅ 背景音乐生成完全成功！")
                print("🎵 音频文件已准备就绪，可以用于视频合成")
            
            return True
            
        else:
            print(f"\n❌ 音乐生成失败！用时: {elapsed_time:.1f}秒")
            print(f"错误信息: {result.error}")
            return False
            
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"\n❌ 发生异常！用时: {elapsed_time:.1f}秒")
        print(f"异常类型: {type(e).__name__}")
        print(f"异常信息: {str(e)}")
        
        # 如果需要详细调试信息
        if "--debug" in sys.argv:
            import traceback
            traceback.print_exc()
        
        return False


async def main():
    """主函数"""
    print("🚀 启动Suno音乐生成专项测试")
    print(f"📅 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 检查环境
    from app.core.config import settings
    if settings.SUNO_API_KEY:
        print(f"✅ SUNO_API_KEY已配置: {settings.SUNO_API_KEY[:20]}...")
    else:
        print("❌ SUNO_API_KEY未配置")
        return
    
    # 运行测试
    success = await test_suno_pure_polling()
    
    print("\n" + "=" * 60)
    print(f"🎯 测试结果: {'✅ 成功' if success else '❌ 失败'}")
    
    if success:
        print("💡 提示: 背景音乐功能已完全就绪，可以集成到视频生成流程中")
    else:
        print("💡 提示: 请检查错误信息，可能需要:")
        print("   1. 确认Suno账户有足够的credits")
        print("   2. 检查网络连接")
        print("   3. 使用 --debug 参数查看详细错误")


if __name__ == "__main__":
    asyncio.run(main())
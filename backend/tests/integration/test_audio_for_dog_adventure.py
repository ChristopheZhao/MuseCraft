#!/usr/bin/env python3
"""
专门为小狗历险记视频测试背景音乐生成
基于实际工作流的概念计划和场景数据
"""

import asyncio
import time
import sys
import json

async def test_audio_generation_for_dog_adventure():
    """为小狗历险记生成背景音乐"""
    print("🎵 小狗历险记 - 背景音乐生成测试")
    print("=" * 60)
    
    # 导入需要的模块
    from app.agents.tools.ai_services.suno_client import SunoClientTool
    from app.agents.tools.base_tool import ToolInput
    
    # 基于实际视频的概念计划数据
    concept_data = {
        "overview": "This 30-second anime-style video tells the heartwarming story of a小狗 (little dog) who falls into a sewer and is rescued by a brave little mouse in a pumpkin boat.",
        "target_audience": "Children and families, particularly those who enjoy animated adventures and stories of friendship.",
        "key_messages": ["Resilience in adversity", "The power of friendship", "Hope and redemption"],
        "mood_progression": ["Fear (fall)", "Hope (rescue)", "Joy (escape)"],
        "visual_style": "Bright, colorful, and whimsical anime style",
        "total_duration": 30.0
    }
    
    scenes_data = [
        {
            "scene_number": 1,
            "title": "The Fall",
            "mood_target": "Tense and unsettling",
            "duration": 7.0,
            "description": "The小狗 accidentally falls into the sewer"
        },
        {
            "scene_number": 2, 
            "title": "The Rescue",
            "mood_target": "Hopeful and reassuring",
            "duration": 8.5,
            "description": "A little mouse in a pumpkin boat rescues the小狗"
        },
        {
            "scene_number": 3,
            "title": "The Escape", 
            "mood_target": "Exciting and triumphant",
            "duration": 8.0,
            "description": "Navigate the sewers and burst out into a waterfall"
        },
        {
            "scene_number": 4,
            "title": "Reunion",
            "mood_target": "Joyful and heartwarming", 
            "duration": 6.5,
            "description": "Reunited with the outside world"
        }
    ]
    
    print(f"📖 视频概念: {concept_data['overview'][:80]}...")
    print(f"🎯 目标受众: {concept_data['target_audience']}")
    print(f"⏱️  总时长: {concept_data['total_duration']}秒")
    print(f"🎭 场景数量: {len(scenes_data)}")
    
    # 分析整体情绪和风格需求
    # 基于场景的情绪变化：紧张 → 希望 → 兴奋 → 快乐
    overall_mood = "uplifting"  # 整体积极向上
    music_style = "cinematic"   # 电影感背景音乐，适合冒险故事
    
    print(f"\n🎨 推荐音乐风格: {music_style}")
    print(f"🎭 整体情绪: {overall_mood}")
    
    # 构建音乐生成参数
    music_description = (
        f"Create {music_style} background music for an anime-style adventure story "
        f"about a dog and mouse friendship. The music should support an emotional journey "
        f"from tension and fear to hope, excitement, and finally joy and triumph. "
        f"Suitable for children and families, with a {overall_mood} overall tone."
    )
    
    music_params = {
        "description": music_description,
        "mood": overall_mood,
        "style": music_style,
        "duration": 30,  # 匹配视频总长度
        "instrumental": True,
        "title": "Dog Adventure - Background Music"
    }
    
    print(f"\n📝 音乐生成参数:")
    for key, value in music_params.items():
        if key == "description":
            print(f"   {key}: {value[:60]}...")
        else:
            print(f"   {key}: {value}")
    
    # 创建Suno客户端工具
    tool = SunoClientTool(config={
        "use_callback": False,  # 开发环境使用轮询
        "polling_interval": 30,
        "max_polling_attempts": 15
    })
    
    print(f"\n🔑 API配置: {'✅ 已配置' if tool._functional else '❌ 未配置'}")
    
    if not tool._functional:
        print("❌ Suno API Key未配置，无法进行测试")
        return False
    
    # 创建工具输入
    tool_input = ToolInput(
        action="generate_background_music",
        timeout=300,  # 5分钟超时
        parameters=music_params
    )
    
    print(f"\n🎶 开始生成背景音乐...")
    print(f"⏰ 开始时间: {time.strftime('%H:%M:%S')}")
    print("📺 为视频场景分析:")
    for scene in scenes_data:
        print(f"   场景{scene['scene_number']}: {scene['title']} - {scene['mood_target']}")
    
    start_time = time.time()
    
    try:
        # 执行音乐生成
        result = await tool.execute(tool_input)
        elapsed_time = time.time() - start_time
        
        if result.success:
            print(f"\n🎉 背景音乐生成成功！用时: {elapsed_time:.1f}秒")
            print("=" * 60)
            
            audio_data = result.result
            print("📊 生成结果:")
            print(f"   📝 标题: {audio_data.get('title', 'Unknown')}")
            print(f"   🎨 风格: {audio_data.get('style', 'Unknown')}")
            print(f"   🎭 情绪: {audio_data.get('mood', 'Unknown')}")
            print(f"   ⏱️  时长: {audio_data.get('duration', 0)}秒")
            print(f"   🎵 纯音乐: {'是' if audio_data.get('instrumental') else '否'}")
            print(f"   🆔 任务ID: {audio_data.get('task_id', 'None')}")
            
            audio_url = audio_data.get('audio_url', '')
            if audio_url:
                print(f"   🔗 音频URL: {audio_url}")
                print(f"\n✅ 背景音乐已就绪，可以下载试听！")
                print(f"🎧 建议在浏览器中打开URL试听音效是否符合预期")
                
                # 分析生成的音乐是否适合各个场景
                print(f"\n📝 音乐适配性分析:")
                print(f"   🎬 场景1 (紧张): 音乐应该有轻微的紧张感开始")
                print(f"   🛟 场景2 (希望): 音乐转向温暖和希望") 
                print(f"   🏃 场景3 (兴奋): 音乐应该有动感和冒险感")
                print(f"   🎊 场景4 (快乐): 音乐达到欢快的高潮")
                
                return True
            else:
                print(f"   ❌ 未获取到音频URL")
                return False
        else:
            print(f"\n❌ 背景音乐生成失败！用时: {elapsed_time:.1f}秒")
            print(f"错误信息: {result.error}")
            return False
            
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"\n❌ 生成过程发生异常！用时: {elapsed_time:.1f}秒")
        print(f"异常类型: {type(e).__name__}")
        print(f"异常信息: {str(e)}")
        
        if "--debug" in sys.argv:
            import traceback
            traceback.print_exc()
        
        return False


async def main():
    """主函数"""
    print("🚀 启动小狗历险记背景音乐生成测试")
    print(f"📅 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 检查API Key
    from app.core.config import settings
    if settings.SUNO_API_KEY:
        print(f"✅ SUNO_API_KEY已配置")
    else:
        print("❌ SUNO_API_KEY未配置，请在.env文件中添加")
        return
    
    # 运行测试
    success = await test_audio_generation_for_dog_adventure()
    
    print("\n" + "=" * 60)
    print(f"🎯 测试结果: {'✅ 成功' if success else '❌ 失败'}")
    
    if success:
        print("💡 后续步骤:")
        print("   1. 🎧 试听生成的音乐，检查是否符合视频氛围")
        print("   2. 🎬 将音乐URL整合到VideoComposer进行合成")
        print("   3. 🎵 调整音量和淡入淡出效果")
        print("   4. 📹 生成最终带背景音乐的完整视频")
    else:
        print("💡 故障排除建议:")
        print("   1. 🔑 确认Suno API Key有效且有足够credits")
        print("   2. 🌐 检查网络连接") 
        print("   3. ⏱️  如果超时，等待更长时间再试")
        print("   4. 🐛 使用 --debug 参数查看详细错误信息")


if __name__ == "__main__":
    asyncio.run(main())
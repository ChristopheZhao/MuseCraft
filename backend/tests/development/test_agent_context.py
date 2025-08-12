#!/usr/bin/env python3
"""
测试Agent工作流中的上下文传递
模拟VideoGenerator接收到的scene_data内容
"""
import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


async def analyze_existing_scene_files():
    """分析现有场景文件，推断scene_data的内容"""
    
    print("🔍 分析现有场景文件内容")
    print("=" * 60)
    
    # 检查场景文件
    scene_files = [
        "./storage/generated/scene_3_first_frame.jpg",
        "./storage/generated/scene_3_last_frame.jpg", 
        "./storage/generated/scene_3_image.jpg",
        "./storage/generated/scene_3_video.mp4"
    ]
    
    print("📁 场景3相关文件:")
    for file_path in scene_files:
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            print(f"   ✅ {os.path.basename(file_path)} ({file_size} bytes)")
        else:
            print(f"   ❌ {os.path.basename(file_path)} (不存在)")
    
    print("\n🎯 关键发现:")
    print("   - 首帧图片: 鸭妈妈驮着小兔子 (正确内容)")
    print("   - 尾帧图片: 小兔子安全抵达 (正确内容)")
    print("   - 工具直接测试: 生成鸭妈妈救兔子视频 (正确)")
    print("   - Agent工作流: 生成小鸭子游泳视频 (错误)")
    
    print("\n💡 问题定位:")
    print("   问题出现在Agent工作流的提示词构建阶段")
    print("   VideoGenerator从scene_data中提取的文本描述可能是错误的")
    
    print("\n🔍 需要检查的字段:")
    scene_data_fields = [
        "visual_description",
        "narrative_description", 
        "script_text",
        "mood_and_atmosphere",
        "title",
        "description"
    ]
    
    for field in scene_data_fields:
        print(f"   - scene_data.{field}")
    
    print("\n🎯 解决方案:")
    print("   1. 检查ConceptPlanner生成的场景描述是否正确")
    print("   2. 检查ScriptWriter生成的脚本内容是否正确") 
    print("   3. 检查ImageGenerator的提示词是否与script匹配")
    print("   4. 检查WorkflowState中scene数据的一致性")
    
    return True


async def simulate_video_prompt_building():
    """模拟VideoGenerator的提示词构建过程"""
    
    print("\n" + "=" * 60)
    print("🎬 模拟VideoGenerator提示词构建过程")
    print("=" * 60)
    
    # 假设的错误scene_data（可能导致问题的数据）
    wrong_scene_data = {
        "visual_description": "A small tiger cub swimming in water with other animals",
        "narrative_description": "Tiger cub playing in water with friends", 
        "script_text": "小老虎在水中玩耍，周围有其他小动物陪伴",
        "mood_and_atmosphere": "playful, joyful water scene",
        "title": "小老虎的水中冒险",
        "description": "小老虎和伙伴们在水中快乐玩耍"
    }
    
    # 正确的scene_data（应该有的数据）
    correct_scene_data = {
        "visual_description": "A mother duck rescuing a small rabbit from water",
        "narrative_description": "Duck mother carries rabbit to safety",
        "script_text": "鸭妈妈看到小兔子落水，立即游过去救援",
        "mood_and_atmosphere": "rescue, caring, heroic action",
        "title": "鸭妈妈的救援行动", 
        "description": "鸭妈妈勇敢救援落水小兔子"
    }
    
    print("❌ 如果scene_data包含错误内容:")
    print(f"   visual_description: {wrong_scene_data['visual_description']}")
    print(f"   narrative_description: {wrong_scene_data['narrative_description']}")
    print(f"   script_text: {wrong_scene_data['script_text']}")
    
    wrong_prompt_elements = [
        wrong_scene_data["visual_description"],
        f"Action: {wrong_scene_data['narrative_description']}",
        f"Story context: {wrong_scene_data['script_text'][:80]}",
        f"Atmosphere: {wrong_scene_data['mood_and_atmosphere']}",
        "smooth motion", "cinematic movement", "professional video production"
    ]
    wrong_prompt = ". ".join(wrong_prompt_elements)
    
    print(f"\n❌ 错误的视频提示词:")
    print(f"   {wrong_prompt}")
    
    print(f"\n✅ 如果scene_data包含正确内容:")
    print(f"   visual_description: {correct_scene_data['visual_description']}")
    print(f"   narrative_description: {correct_scene_data['narrative_description']}")
    print(f"   script_text: {correct_scene_data['script_text']}")
    
    correct_prompt_elements = [
        correct_scene_data["visual_description"],
        f"Action: {correct_scene_data['narrative_description']}",
        f"Story context: {correct_scene_data['script_text'][:80]}",
        f"Atmosphere: {correct_scene_data['mood_and_atmosphere']}",
        "smooth motion", "cinematic movement", "professional video production"
    ]
    correct_prompt = ". ".join(correct_prompt_elements)
    
    print(f"\n✅ 正确的视频提示词:")
    print(f"   {correct_prompt}")
    
    print(f"\n💡 结论:")
    print(f"   即使首尾帧图片正确，如果scene_data中的文本描述错误，")
    print(f"   VideoGenerator构建的提示词也会误导CogVideoX-3生成错误内容")
    
    return True


async def main():
    """主函数"""
    try:
        await analyze_existing_scene_files()
        await simulate_video_prompt_building()
        
        print("\n" + "=" * 60)
        print("🎯 下一步行动建议:")
        print("1. 检查ConceptPlanner的输出 - 是否生成了正确的概念")
        print("2. 检查ScriptWriter的输出 - 是否生成了匹配的脚本")
        print("3. 检查ImageGenerator的输入 - 使用的是哪个脚本描述")
        print("4. 检查WorkflowState的数据流 - scene_data的来源和传递")
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
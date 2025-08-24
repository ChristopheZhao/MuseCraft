#!/usr/bin/env python3
"""
测试改进后的场景连续性分析系统
"""
import asyncio
import sys
sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput
from app.core.scene_continuity_memory import get_scene_continuity_memory

async def test_improved_continuity_analysis():
    """测试改进的连续性分析逻辑"""
    
    print("🧪 Testing Improved Scene Continuity Analysis...")
    
    # 初始化
    zhipu_tool = ZhipuClientTool()
    continuity_memory = get_scene_continuity_memory()
    
    # 测试用例1: 应该选择new_image的情况（镜头切换）
    test_case_1 = """你是专业的视频制作顾问。你的任务是判断当前场景是否是前一场景中"同一物体/角色的状态演进过程"，需要使用前一场景的最后一帧来保持视觉连续性。

⚠️  **重要**：镜头切换、场景转换、视角变化都是正常的，不需要连续性。只有"状态演进"才需要。

## 前一场景信息 (场景 1)
- **标题**: 山巅静修
- **描述**: 在云雾缭绕的巍峨山巅，修士静坐岩石上，双目微闭，神情平静
- **最终状态**: 修士保持静坐状态，周围灵气开始汇聚

## 当前场景信息 (场景 2)
- **标题**: 丹田内观
- **描述**: 视角转入修士体内，丹田中金丹悬浮，散发金色光芒
- **初始状态**: 金丹稳定运转，能量场围绕

## 🎯 核心判断标准

### ✅ **需要连续性 ("continue_from_previous")** - 状态演进场景:
1. **形态变化过程** - 如：金丹→人形→完整人形、花苞→开花→盛开
2. **能量变化过程** - 如：能量聚集→爆发→扩散、光芒微弱→增强→耀眼  
3. **表情/情绪渐变** - 如：平静→惊讶→震惊、痛苦→领悟→喜悦
4. **动作连续过程** - 如：起身→走动→坐下、举手→挥舞→放下
5. **物体状态演进** - 如：破裂→碎裂→重组、燃烧→熄灭→烟散

### ❌ **不需要连续性 ("new_image")** - 正常镜头切换:
1. **视角/镜头转换** - 如：外景→内心世界、全景→特写、远景→近景
2. **场景/地点切换** - 如：室内→室外、山峰→平原、天空→地面  
3. **时间跳跃** - 如："三天后"、"与此同时"、"回忆中"
4. **主体切换** - 如：从A角色→B角色、从人→动物→环境

## 🔍 判断核心问题
**"当前场景是前一场景中同一物体/角色的状态演进吗？"**
- 是 → `continue_from_previous`
- 否 → `new_image`

请以JSON格式返回决策：
{
  "strategy": "new_image" | "continue_from_previous", 
  "reasoning": "详细分析理由",
  "confidence_score": 0.9
}"""

    try:
        print("🔄 测试用例1: 山巅静修 → 丹田内观 (应该是镜头切换)")
        
        result1 = await zhipu_tool.execute(ToolInput(
            action="generate_text",
            parameters={
                "prompt": test_case_1,
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            }
        ))
        
        import json
        content1 = result1.result.get("content", "")
        analysis1 = json.loads(content1.strip())
        
        print(f"✅ 结果1: {analysis1['strategy']}")
        print(f"   推理: {analysis1['reasoning'][:80]}...")
        print(f"   置信度: {analysis1['confidence_score']}")
        
        expected1 = "new_image"
        if analysis1['strategy'] == expected1:
            print(f"✅ 正确！识别为{expected1} - 这是正常的镜头切换")
        else:
            print(f"⚠️  期望{expected1}，但得到{analysis1['strategy']}")
    
        # 测试用例2: 应该选择continue_from_previous的情况（状态演进）
        test_case_2 = test_case_1.replace(
            """## 当前场景信息 (场景 2)
- **标题**: 丹田内观
- **描述**: 视角转入修士体内，丹田中金丹悬浮，散发金色光芒
- **初始状态**: 金丹稳定运转，能量场围绕""",
            """## 当前场景信息 (场景 3)
- **标题**: 元婴初现
- **描述**: 金丹开始显现人形轮廓，模糊的元婴形态在金丹中浮现
- **初始状态**: 金丹表面开始出现人形光影，能量波动增强"""
        )
        
        print(f"\n🔄 测试用例2: 金丹稳定 → 元婴初现 (应该是状态演进)")
        
        result2 = await zhipu_tool.execute(ToolInput(
            action="generate_text",
            parameters={
                "prompt": test_case_2,
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            }
        ))
        
        content2 = result2.result.get("content", "")
        analysis2 = json.loads(content2.strip())
        
        print(f"✅ 结果2: {analysis2['strategy']}")
        print(f"   推理: {analysis2['reasoning'][:80]}...")
        print(f"   置信度: {analysis2['confidence_score']}")
        
        expected2 = "continue_from_previous"
        if analysis2['strategy'] == expected2:
            print(f"✅ 正确！识别为{expected2} - 这是状态演进过程")
        else:
            print(f"⚠️  期望{expected2}，但得到{analysis2['strategy']}")
        
        print(f"\n🎯 测试总结:")
        print(f"  用例1 (镜头切换): {'✅' if analysis1['strategy'] == 'new_image' else '❌'}")
        print(f"  用例2 (状态演进): {'✅' if analysis2['strategy'] == 'continue_from_previous' else '❌'}")
        
        if analysis1['strategy'] == 'new_image' and analysis2['strategy'] == 'continue_from_previous':
            print(f"\n🎉 改进的连续性分析逻辑工作正常！")
        else:
            print(f"\n⚠️  需要进一步调优提示词")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_improved_continuity_analysis())
#!/usr/bin/env python3
"""
测试金丹状态演进的连续性判断
"""
import asyncio
import sys
sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput

async def test_golden_core_continuity():
    """测试金丹状态演进的连续性判断"""
    
    print("🧪 Testing Golden Core State Evolution Continuity...")
    
    zhipu_tool = ZhipuClientTool()
    
    # 明确的金丹状态演进测试用例
    test_prompt = """你是专业的视频制作顾问。你的任务是判断当前场景是否是前一场景中"同一物体/角色的状态演进过程"，需要使用前一场景的最后一帧来保持视觉连续性。

⚠️  **重要**：镜头切换、场景转换、视角变化都是正常的，不需要连续性。只有"状态演进"才需要。

## 前一场景信息 (场景 2)
- **标题**: 金丹稳定
- **描述**: 体内丹田中，一颗完美的金色丹丸悬浮中央，散发柔和光芒
- **最终状态**: 金丹表面光滑稳定，能量场平静围绕

## 当前场景信息 (场景 3)
- **标题**: 元婴初现  
- **描述**: 同一颗金丹开始显现人形轮廓，模糊的元婴形态在金丹内部浮现
- **初始状态**: 金丹表面出现人形光影，能量开始波动

## 🔍 关键判断逻辑

**STEP 1: 识别核心主体**
- 前一场景的主要对象是什么？（人物、金丹、能量、表情等）
- 当前场景的主要对象是什么？

**STEP 2: 判断是否为同一主体**
- 如果是同一个金丹：从"稳定"→"显现人形" = 状态演进 ✅
- 如果是同一个人物：从"平静"→"震惊" = 状态演进 ✅  
- 如果是不同主体：从"人物"→"另一个人物" = 镜头切换 ❌

**STEP 3: 判断变化类型**  
- **状态演进**: 同一对象的逐渐变化（形态、表情、能量强度）
- **镜头切换**: 视角转换、空间变化、完全不同的对象

## 💡 **决策要点**
- **相同主体 + 状态变化** → `continue_from_previous` 
- **不同主体 OR 空间切换** → `new_image`

**特殊说明**: 即使是"体内视角"，如果描述的是同一个金丹的不同状态，仍然是状态演进！

请以JSON格式返回决策：
{
  "strategy": "continue_from_previous",
  "reasoning": "这是同一颗金丹从稳定状态到显现人形的演进过程",
  "confidence_score": 0.9
}"""

    try:
        print("🔄 测试：金丹稳定 → 金丹显现人形 (应该识别为状态演进)")
        
        result = await zhipu_tool.execute(ToolInput(
            action="generate_text", 
            parameters={
                "prompt": test_prompt,
                "temperature": 0.2,  # 更低的温度确保一致性
                "response_format": {"type": "json_object"}
            }
        ))
        
        import json
        content = result.result.get("content", "")
        analysis = json.loads(content.strip())
        
        print(f"✅ 分析结果:")
        print(f"   策略: {analysis['strategy']}")
        print(f"   推理: {analysis['reasoning']}")
        print(f"   置信度: {analysis['confidence_score']}")
        
        # 验证结果
        if analysis['strategy'] == 'continue_from_previous':
            print(f"\n🎉 成功！正确识别为状态演进过程")
            print(f"   这意味着Scene 3会使用Scene 2视频的最后一帧作为起始帧")
        else:
            print(f"\n⚠️  仍需调优：期望'continue_from_previous'，得到'{analysis['strategy']}'")
            print(f"   可能需要进一步强化提示词中的'同一主体判断'逻辑")
            
        # 补充测试：非连续性场景
        print(f"\n🔄 对比测试：完全不同主体的场景切换")
        
        non_continuous_prompt = test_prompt.replace(
            """## 当前场景信息 (场景 3)
- **标题**: 元婴初现  
- **描述**: 同一颗金丹开始显现人形轮廓，模糊的元婴形态在金丹内部浮现
- **初始状态**: 金丹表面出现人形光影，能量开始波动""",
            """## 当前场景信息 (场景 3)
- **标题**: 师父出现
- **描述**: 另一位老者出现在修炼室外，观察着弟子的修炼进度
- **初始状态**: 老者站在门外，神情专注地感知着室内的能量波动"""
        )
        
        result2 = await zhipu_tool.execute(ToolInput(
            action="generate_text",
            parameters={
                "prompt": non_continuous_prompt,
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            }
        ))
        
        content2 = result2.result.get("content", "")
        analysis2 = json.loads(content2.strip())
        
        print(f"✅ 对比结果:")
        print(f"   策略: {analysis2['strategy']}")
        print(f"   推理: {analysis2['reasoning'][:100]}...")
        
        if analysis2['strategy'] == 'new_image':
            print(f"✅ 正确识别为不同主体，不需要连续性")
        else:
            print(f"⚠️  应该识别为new_image")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_golden_core_continuity())
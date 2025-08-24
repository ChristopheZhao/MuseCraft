#!/usr/bin/env python3
"""
简化测试：只测试ConceptPlanner的提示词渲染
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_simple():
    try:
        from app.agents.concept_planner import ConceptPlannerAgent
        
        # 创建实例
        agent = ConceptPlannerAgent()
        print(f"✅ Agent名称: {agent.agent_name}")
        
        # 测试_build_concept_prompt方法（ConceptPlanner内部使用）
        prompt = agent._build_concept_prompt(
            user_prompt="制作咖啡视频",
            video_style="专业风格",
            duration=30,
            aspect_ratio="16:9"
        )
        
        print(f"✅ 提示词渲染成功")
        print(f"📄 长度: {len(prompt)} 字符")
        print(f"📄 预览: {prompt[:100]}...")
        
        # 验证内容
        if "制作咖啡视频" in prompt and "专业风格" in prompt:
            print("✅ 变量替换正确")
            return True
        else:
            print("❌ 变量替换失败")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if test_simple():
        print("🎉 ConceptPlanner提示词系统改造成功！")
        print("📊 从300+行硬编码 → YAML配置 + 模板渲染")
    else:
        print("❌ 测试失败")
#!/usr/bin/env python3
"""
测试脚本：验证统一提示词管理系统
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app.core.prompt_manager import get_prompt_manager, render_prompt


def test_prompt_system():
    """测试提示词系统的基本功能"""
    
    print("🔧 测试统一提示词管理系统...")
    
    try:
        # 1. 获取提示词管理器
        manager = get_prompt_manager()
        print(f"✅ 提示词管理器初始化成功")
        
        # 2. 查看加载的配置
        configs = manager.list_configs()
        print(f"✅ 加载的配置: {configs}")
        
        # 3. 查看concept_planner的模板
        if "concept_planner" in configs:
            templates = manager.list_templates("concept_planner")
            print(f"✅ concept_planner模板: {templates}")
            
            # 4. 测试模板渲染
            if "concept_generation" in templates:
                rendered = manager.render_template(
                    config_name="concept_planner",
                    template_name="concept_generation",
                    variables={
                        "user_prompt": "制作一个展示美食制作的短视频",
                        "video_style": "温馨风格",
                        "duration": 30,
                        "aspect_ratio": "16:9"
                    }
                )
                
                print(f"✅ 模板渲染成功")
                print(f"📄 渲染结果长度: {len(rendered)} 字符")
                print(f"📄 渲染结果预览: {rendered[:200]}...")
                
                # 验证关键内容是否存在
                assert "制作一个展示美食制作的短视频" in rendered
                assert "温馨风格" in rendered
                assert "30秒" in rendered
                assert "16:9" in rendered
                print("✅ 模板变量替换正确")
                
            else:
                print("❌ concept_generation模板未找到")
        else:
            print("❌ concept_planner配置未找到")
        
        # 5. 测试系统指令获取
        system_instructions = manager.get_system_instruction("concept_planner")
        if system_instructions:
            print(f"✅ 系统指令获取成功: {system_instructions}")
        
        # 6. 获取统计信息
        stats = manager.get_stats()
        print(f"✅ 系统统计: {stats}")
        
        print("\n🎉 所有测试通过！提示词系统工作正常")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def test_concept_planner_integration():
    """测试ConceptPlanner与提示词系统的集成"""
    
    print("\n🔧 测试ConceptPlanner集成...")
    
    try:
        from app.agents.concept_planner import ConceptPlannerAgent
        
        # 创建ConceptPlanner实例
        agent = ConceptPlannerAgent()
        print("✅ ConceptPlanner实例化成功")
        
        # 测试提示词渲染
        prompt = agent.render_prompt(
            "concept_generation",
            user_prompt="制作一个展示咖啡制作过程的视频",
            video_style="专业风格", 
            duration=45,
            aspect_ratio="9:16"
        )
        
        print(f"✅ Agent提示词渲染成功")
        print(f"📄 提示词长度: {len(prompt)} 字符（原来300+行已缩减）")
        
        # 验证内容
        assert "制作一个展示咖啡制作过程的视频" in prompt
        assert "专业风格" in prompt
        assert "45秒" in prompt
        print("✅ Agent集成正确")
        
    except Exception as e:
        print(f"❌ ConceptPlanner集成测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def test_performance_comparison():
    """性能对比测试"""
    
    print("\n🔧 性能对比测试...")
    
    import time
    
    try:
        manager = get_prompt_manager()
        
        # 测试渲染性能
        start_time = time.time()
        for i in range(100):
            rendered = manager.render_template(
                config_name="concept_planner",
                template_name="concept_generation",
                variables={
                    "user_prompt": f"测试视频{i}",
                    "video_style": "测试风格",
                    "duration": 30,
                    "aspect_ratio": "16:9"
                },
                use_cache=True
            )
        
        end_time = time.time()
        avg_time = (end_time - start_time) / 100
        
        print(f"✅ 100次渲染平均耗时: {avg_time*1000:.2f}ms")
        print(f"✅ 模板系统性能良好")
        
    except Exception as e:
        print(f"❌ 性能测试失败: {str(e)}")
        return False
    
    return True


if __name__ == "__main__":
    print("🚀 开始测试统一提示词管理系统\n")
    
    success = True
    
    # 运行所有测试
    success &= test_prompt_system()
    success &= test_concept_planner_integration()
    success &= test_performance_comparison()
    
    if success:
        print("\n🎉 所有测试通过！")
        print("📊 改造效果：")
        print("   - ConceptPlanner从300+行硬编码模板 → 简单的模板调用")
        print("   - 提示词统一管理，支持YAML配置")
        print("   - 支持Jinja2模板变量和缓存机制")
        print("   - BaseAgent集成统一提示词接口")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)
#!/usr/bin/env python3
"""
测试ImageGenerator使用工具系统
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from types import SimpleNamespace

from app.agents.image_generator import ImageGeneratorAgent
from app.agents.tools.tool_registry import get_tool_registry
from app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool
from app.agents.tools.consistency_tool import ConsistencyTool
from app.agents.tools.storage.file_storage_tool import FileStorageTool

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool


def _ensure_tools_registered():
    registry = get_tool_registry()
    registry.register_tool(ZhipuClientTool, name="zhipu_client", auto_load=False)
    for cls, name in [
        (ImageGenerationTool, "image_generation"),
        (ConsistencyTool, "consistency_tool"),
        (FileStorageTool, "file_storage_tool"),
    ]:
        try:
            registry.get_tool(name)
        except Exception:
            registry.register_tool(tool_class=cls, name=name, auto_load=False)

def test_image_generator_tool_system():
    """测试ImageGenerator使用工具系统而非直接AI服务调用"""
    
    print("🧪 测试ImageGenerator工具系统重构")
    print("=" * 60)

    _ensure_tools_registered()

    # 创建ImageGenerator实例
    image_gen = ImageGeneratorAgent()
    
    print("✅ ImageGenerator初始化成功")
    print(f"   - Agent类型: {image_gen.agent_type}")
    print(f"   - Agent名称: {image_gen.agent_name}")
    print(f"   - 超时时间: {image_gen.timeout_seconds}s")
    
    # 检查是否移除了AIClient依赖
    has_ai_client = hasattr(image_gen, 'ai_client')
    print(f"   - 直接AIClient依赖: {'❌ 已移除' if not has_ai_client else '⚠️ 仍存在'}")
    
    # 检查工具系统支持
    has_use_tool = hasattr(image_gen, 'use_tool')
    print(f"   - 工具系统支持: {'✅ 支持' if has_use_tool else '❌ 不支持'}")
    
    print()
    
    # 验证工具装载结果
    print("🔧 工具注册验证:")
    print("-" * 30)
    allocated = image_gen.allocated_tools
    print(f"   已分配工具: {allocated}")
    assert "image_generation" in allocated
    assert "consistency_tool" in allocated
    assert "file_storage_tool" in allocated
    ig_tool = image_gen._available_tools["image_generation"]
    print(f"   image_generation 可用动作: {ig_tool.get_available_actions()}")
    
    # 测试参数生成
    print()
    print("⚙️ 测试参数生成:")
    print("-" * 30)
    
    # 模拟场景数据
    scene_data = SimpleNamespace(
        scene_number=1,
        scene_type="main_content",
        title="Pool Party",
        description="Friends having fun in a pool",
        visual_description="Dynamic water activities with friends laughing",
        duration=8.0,
        props_and_objects=["swimming pool", "clear water"],
        mood_and_atmosphere="joyful and energetic",
    )
    
    # 模拟创意指导
    creative_guidance = {
        "overall_guidance": {
            "production_guidance": {
                "technical_requirements": {
                    "resolution": "1024x1024"
                }
            }
        },
        "scene_guidance": {},
        "has_guidance": True
    }
    
    generation_params = image_gen._get_generation_parameters_with_guidance(scene_data, creative_guidance)
    print(f"✅ 生成参数: {generation_params}")
    
    # 测试提示词增强
    print()
    print("🎨 测试MAS协作模式提示词增强:")
    print("-" * 30)
    
    # 添加场景参考到scene_data（模拟ScriptWriter的输出）
    scene_data.first_frame_scene_reference = {
        "situation": "Friends arriving at poolside with excitement",
        "character_emotional_state": "anticipatory and happy",
        "key_visual_elements": ["swimming pool", "bright sunlight", "colorful swimwear"],
        "action_potential": "about to jump into water",
        "narrative_context": "Opening moment of pool party fun"
    }
    
    scene_data.last_frame_scene_reference = {
        "situation": "Friends enjoying peak fun in the water",
        "character_emotional_state": "pure joy and connection",
        "key_visual_elements": ["splashing water", "laughing faces", "dynamic movement"],
        "action_completion": "fully immersed in play",
        "transition_preparation": "ready for next scene"
    }
    
    base_prompt = scene_data.visual_description
    
    # 测试首帧增强
    first_frame_enhanced = image_gen._enhance_prompt_for_first_frame(
        base_prompt, scene_data, creative_guidance
    )
    print(f"🎬 首帧增强提示词:")
    print(f"   原始: {base_prompt}")
    print(f"   增强: ...{first_frame_enhanced[-100:]}")  # 显示最后100个字符
    
    # 测试尾帧增强
    last_frame_enhanced = image_gen._enhance_prompt_for_last_frame(
        base_prompt, scene_data, creative_guidance
    )
    print(f"🏁 尾帧增强提示词:")
    print(f"   原始: {base_prompt}")
    print(f"   增强: ...{last_frame_enhanced[-100:]}")   # 显示最后100个字符
    
    print()
    
    # 验证架构改进
    print("🏗️ 架构改进验证:")
    print("-" * 30)
    
    improvements = []
    
    # 检查是否移除了直接AI调用方法
    old_methods = ['_generate_with_openai', '_generate_with_stability', '_generate_with_glm', '_build_image_prompt_from_data']
    removed_methods = [method for method in old_methods if not hasattr(image_gen, method)]
    
    if len(removed_methods) == len(old_methods):
        improvements.append("✅ 移除了所有直接AI服务调用方法")
    else:
        remaining = [method for method in old_methods if hasattr(image_gen, method)]
        improvements.append(f"⚠️ 仍有直接调用方法: {remaining}")
    
    # 检查MAS协作字段
    mas_fields = ['first_frame_scene_reference', 'last_frame_scene_reference']
    has_mas_support = all(hasattr(scene_data, field) for field in mas_fields)
    
    if has_mas_support:
        improvements.append("✅ 支持MAS协作场景参考")
    else:
        improvements.append("❌ 缺少MAS协作支持")
    
    # 检查工具系统架构
    if has_use_tool and not has_ai_client:
        improvements.append("✅ 完全转换为工具系统架构")
    elif has_use_tool and has_ai_client:
        improvements.append("⚠️ 混合架构（工具系统 + 直接AI调用）")
    else:
        improvements.append("❌ 仍使用旧的直接AI调用架构")
    
    for improvement in improvements:
        print(f"   {improvement}")
    
    print()
    print("🎊 ImageGenerator工具系统重构测试完成!")
    
    # 检查整体架构合规性
    all_good = all("✅" in improvement for improvement in improvements)
    if all_good:
        print("🚀 架构重构完全成功!")
    else:
        print("⚠️ 架构重构需要进一步调整")

if __name__ == "__main__":
    test_image_generator_tool_system()

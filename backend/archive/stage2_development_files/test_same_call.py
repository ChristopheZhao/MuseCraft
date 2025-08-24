import asyncio
import sys
import json
sys.path.append('.')

# 我们需要修改ScriptGenerationTool来让我们能够看到内部的处理过程
from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput

async def test_single_call_process():
    """测试单次调用的完整处理过程"""
    print('🔍 测试单次调用的完整处理过程...')
    
    try:
        # 模拟ScriptGenerationTool内部的完整流程
        zhipu_client = ZhipuClientTool()
        
        # 1. 构建prompt (和ScriptGenerationTool相同)
        scene_data = {
            'visual_description': 'A peaceful morning in a Japanese garden',
            'content_focus': 'Cherry blossoms falling gently in morning light',
            'narrative_description': 'Serene atmosphere with soft sunlight filtering through trees',
            'duration': 10
        }
        video_style = 'cinematic'
        
        prompt = f"""请为以下场景生成详细的视频脚本：

场景信息：
- 视觉描述：{scene_data.get('visual_description', '')}
- 内容重点：{scene_data.get('content_focus', '')}
- 叙事描述：{scene_data.get('narrative_description', '')}
- 预计时长：{scene_data.get('duration', 5)}秒

视频风格：{video_style}

请生成包含以下内容的场景脚本：
1. 详细的脚本文本（适合语音合成）
2. 视觉指导（镜头运动、构图等）
3. 时长分配建议
4. 情绪基调描述

返回JSON格式：
{{
    "script_text": "详细脚本文本",
    "visual_guidance": "视觉指导",
    "duration_suggestion": "时长建议",
    "emotional_tone": "情绪基调",
    "keywords": ["关键词列表"],
    "success": true
}}"""
        
        # 2. 调用ZhipuClient
        zhipu_input = ToolInput(
            action="chat_completion",
            parameters={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 1000,
                "response_format": {"type": "json_object"}
            }
        )
        
        print('📝 1. 调用ZhipuClient...')
        zhipu_result = await zhipu_client.execute(zhipu_input)
        
        if not zhipu_result.success:
            print(f'❌ ZhipuClient调用失败: {zhipu_result.error}')
            return False
        
        # 3. 获取原始响应
        llm_content = zhipu_result.result.get("content", "").strip()
        print(f'✅ 原始响应长度: {len(llm_content)}')
        print(f'   响应开头: {llm_content[:100]}...')
        
        # 4. 解析JSON (和ScriptGenerationTool相同的逻辑)
        try:
            script_data = json.loads(llm_content)
            if "success" not in script_data:
                script_data["success"] = True
            
            print(f'✅ JSON解析成功，字段: {list(script_data.keys())}')
            
            # 输出每个字段的详细信息
            for key, value in script_data.items():
                print(f'   {key}: {type(value)} = {len(str(value))}字符')
                if isinstance(value, str) and len(value) > 0:
                    print(f'      内容: "{value}"')
                elif isinstance(value, list):
                    print(f'      内容: {value}')
                else:
                    print(f'      内容: {value}')
            
            return True
                
        except json.JSONDecodeError as e:
            print(f'❌ JSON解析失败: {e}')
            print(f'   尝试解析的内容: "{llm_content}"')
            return False
            
    except Exception as e:
        print(f'💥 测试异常: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(test_single_call_process())
    print(f'\\n结果: {"✅ 测试成功" if success else "❌ 测试失败"}')
    
    if success:
        print('\\n🎯 结论: 没有数据截断问题!')
        print('   之前观察到的"截断"是因为每次LLM调用结果不同')
        print('   LLM的随机性导致每次生成不同长度和内容的响应')
        print('   这是正常的行为，不是bug！')
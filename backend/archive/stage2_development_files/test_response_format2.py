import asyncio
import sys
import json
import re
sys.path.append('.')

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput

async def test_detailed():
    print('详细测试ZhipuClient输出格式...')
    
    try:
        zhipu_client = ZhipuClientTool()
        
        prompt = '''请生成一个日本花园场景的脚本，返回JSON格式：
{
    "script_text": "脚本内容",
    "visual_guidance": "视觉指导",
    "duration_suggestion": "时长建议",
    "success": true
}'''
        
        # 测试默认格式
        print('\n测试默认text格式的完整输出:')
        input1 = ToolInput(
            action='chat_completion',
            parameters={
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.7,
                'max_tokens': 800
            }
        )
        
        result1 = await zhipu_client.execute(input1)
        if result1.success:
            content = result1.result.get('content', '')
            print(f'完整内容长度: {len(content)}')
            print('\n--- 完整内容 ---')
            print(content)
            print('\n--- 内容结束 ---')
            
            # 尝试提取JSON
            print('\n尝试提取JSON:')
            
            # 方法1：查找```json代码块
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                print(f'找到JSON代码块: {len(json_str)}字符')
                try:
                    parsed = json.loads(json_str)
                    print(f'解析成功，字段: {list(parsed.keys())}')
                    print(f'script_text: {parsed.get("script_text", "")[:100]}...')
                    return True
                except Exception as e:
                    print(f'JSON解析失败: {e}')
            else:
                print('未找到```json代码块')
                
                # 方法2：查找大括号内容
                brace_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
                if brace_match:
                    json_str = brace_match.group(0)
                    print(f'找到大括号内容: {len(json_str)}字符')
                    try:
                        parsed = json.loads(json_str)
                        print(f'解析成功，字段: {list(parsed.keys())}')
                        return True
                    except Exception as e:
                        print(f'JSON解析失败: {e}')
                        print(f'尝试解析的内容: {json_str[:200]}...')
                        
        return False
        
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    result = asyncio.run(test_detailed())
    print(f'\n最终结果: {"✅ 成功" if result else "❌ 失败"}')
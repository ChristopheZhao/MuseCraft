import asyncio
import sys
import json
sys.path.append('.')

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput

async def test_zhipu_formats():
    print('测试ZhipuClient的输出格式...')
    
    try:
        zhipu_client = ZhipuClientTool()
        
        prompt = '''Please generate a JSON response for a Japanese garden scene with these fields:
{
    "script_text": "detailed script text",
    "visual_guidance": "visual guidance",
    "duration_suggestion": "duration info",
    "emotional_tone": "emotional tone",
    "success": true
}'''
        
        # 测试1：默认text格式
        print('\n1. 默认text格式:')
        input1 = ToolInput(
            action='chat_completion',
            parameters={
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.7,
                'max_tokens': 500
            }
        )
        
        result1 = await zhipu_client.execute(input1)
        if result1.success:
            content1 = result1.result.get('content', '')
            print(f'长度: {len(content1)}')
            print(f'开头100字符: {content1[:100]}')
            print(f'包含代码块: {"```" in content1}')
            
            # 尝试JSON解析
            try:
                parsed1 = json.loads(content1)
                print('直接JSON解析成功')
            except:
                print('直接JSON解析失败')
        
        # 测试2：json_object格式
        print('\n2. json_object格式:')
        input2 = ToolInput(
            action='chat_completion',
            parameters={
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.7,
                'max_tokens': 500,
                'response_format': {'type': 'json_object'}
            }
        )
        
        result2 = await zhipu_client.execute(input2)
        if result2.success:
            content2 = result2.result.get('content', '')
            print(f'长度: {len(content2)}')
            print(f'开头100字符: {content2[:100]}')
            print(f'以大括号开始: {content2.strip().startswith("{")}')
            
            try:
                parsed2 = json.loads(content2)
                print(f'JSON解析成功，字段: {list(parsed2.keys())}')
                if 'script_text' in parsed2:
                    print(f'script_text内容: {parsed2["script_text"][:50]}...')
                return True
            except Exception as e:
                print(f'JSON解析失败: {e}')
                return False
        else:
            print(f'失败: {result2.error}')
            return False
            
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    result = asyncio.run(test_zhipu_formats())
    print(f'\n结果: {"✅ 成功" if result else "❌ 失败"}')
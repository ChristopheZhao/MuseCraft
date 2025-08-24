import asyncio
import sys
import json
sys.path.append('.')

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput

async def test_response_format_debug():
    print('调试response_format参数...')
    
    try:
        zhipu_client = ZhipuClientTool()
        
        # 更明确的JSON prompt
        prompt = '''请生成一个日本花园场景的脚本。必须返回有效的JSON格式，包含以下字段：script_text, visual_guidance, success。'''
        
        # 测试response_format参数
        print('\n测试json_object格式:')
        input_json = ToolInput(
            action='chat_completion',
            parameters={
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.7,
                'max_tokens': 800,
                'response_format': {'type': 'json_object'}
            }
        )
        
        print('调用ZhipuClient...')
        result = await zhipu_client.execute(input_json)
        
        print(f'调用成功: {result.success}')
        if result.success:
            print(f'结果类型: {type(result.result)}')
            print(f'结果内容: {result.result}')
            
            content = result.result.get('content', '')
            print(f'content长度: {len(content)}')
            print(f'content内容: "{content}"')
            
            if content:
                try:
                    parsed = json.loads(content)
                    print(f'JSON解析成功: {parsed}')
                    return True
                except Exception as e:
                    print(f'JSON解析失败: {e}')
            else:
                print('content为空')
        else:
            print(f'调用失败: {result.error}')
            print(f'错误详情: {result.metadata}')
            
        return False
        
    except Exception as e:
        print(f'测试异常: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    result = asyncio.run(test_response_format_debug())
    print(f'\n测试结果: {"✅ 成功" if result else "❌ 失败"}')
#!/usr/bin/env python3
"""
Test GLM integration with uv and environment loading
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app.services.ai_client import AIClient
from app.core.config import settings

async def test_glm():
    print("Testing GLM integration with uv...")
    print(f"GLM_API_KEY configured: {'Yes' if settings.GLM_API_KEY else 'No'}")
    print(f"GLM_API_KEY length: {len(settings.GLM_API_KEY) if settings.GLM_API_KEY else 0}")
    
    if not settings.GLM_API_KEY:
        print("\n❌ GLM_API_KEY not found in environment variables")
        print("Please uncomment and set GLM_API_KEY in your .env file:")
        print("GLM_API_KEY=your-glm-api-key-here")
        return
    
    print("\n✅ GLM_API_KEY is configured")
    client = AIClient()
    
    try:
        print("\nSending test request to GLM...")
        response = await client.generate_text(
            prompt="请用中文回复：'GLM正在工作！'",
            model="glm-4-plus",
            max_tokens=50,
            temperature=0.3
        )
        
        print("\n✅ GLM Response received:")
        print(f"Content: {response['content']}")
        print(f"Model: {response['model']}")
        print(f"Provider: {response.get('provider', 'unknown')}")
        print(f"Token usage: {response.get('usage', {})}")
        print("\n🎉 GLM integration successful!")
        
    except Exception as e:
        print(f"\n❌ GLM integration failed: {str(e)}")
        print("\nPossible causes:")
        print("1. Invalid API key")
        print("2. Network connectivity issues")
        print("3. GLM API service issues")
        print("4. Missing zhipuai package (install with: uv pip install zhipuai)")
        
        # Check if zhipuai is installed
        try:
            import zhipuai
            print("✅ zhipuai package is installed")
        except ImportError:
            print("❌ zhipuai package is NOT installed")
            print("Run: uv pip install zhipuai")

if __name__ == "__main__":
    asyncio.run(test_glm())
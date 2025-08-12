#!/usr/bin/env python3
"""
Test GLM integration
"""
import asyncio
import os
import sys
sys.path.append('.')

from app.services.ai_client import AIClient
from app.core.config import settings

async def test_glm():
    print("Testing GLM integration...")
    print(f"GLM_API_KEY configured: {'Yes' if settings.GLM_API_KEY else 'No'}")
    
    if not settings.GLM_API_KEY:
        print("GLM_API_KEY not found in environment variables")
        print("Please set GLM_API_KEY in your .env file")
        return
    
    client = AIClient()
    
    try:
        response = await client.generate_text(
            prompt="Hello, please respond with 'GLM is working!' in Chinese.",
            model="glm-4-plus",
            max_tokens=50,
            temperature=0.3
        )
        
        print("GLM Response:")
        print(f"Content: {response['content']}")
        print(f"Model: {response['model']}")
        print(f"Provider: {response.get('provider', 'unknown')}")
        print("GLM integration successful!")
        
    except Exception as e:
        print(f"GLM integration failed: {str(e)}")
        print("This may be due to:")
        print("1. Invalid API key")
        print("2. Network connectivity issues")
        print("3. GLM API service issues")
        print("4. Missing zhipuai package")

if __name__ == "__main__":
    asyncio.run(test_glm())
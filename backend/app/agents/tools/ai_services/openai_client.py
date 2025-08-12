"""
OpenAI Client Tool - Integrated OpenAI API access for agents
"""

import openai
import json
import base64
from typing import Dict, Any, List, Optional, Union
from PIL import Image
import io

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError


class OpenAIClientTool(AsyncTool):
    """
    OpenAI API client tool providing text generation, vision, and embeddings
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="openai_client",
            version="1.0.0",
            description="OpenAI API client for text generation, vision analysis, and embeddings",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["llm", "ai", "text-generation", "vision", "embeddings"],
            capabilities=[
                "text_generation",
                "chat_completion", 
                "vision_analysis",
                "text_embeddings",
                "function_calling",
                "json_mode"
            ],
            limitations=[
                "requires_api_key",
                "rate_limited",
                "token_limits",
                "cost_per_usage"
            ]
        )
    
    def _initialize(self):
        """Initialize OpenAI client"""
        # 尝试从配置获取API key，如果没有则从环境变量获取
        api_key = self.config.get("api_key")
        if not api_key:
            import os
            api_key = os.getenv("OPENAI_API_KEY")
        
        # 工具可以在没有API key时创建，但在使用时会检查
        self._functional = bool(api_key)
        if api_key:
            self.client = openai.AsyncOpenAI(api_key=api_key)
            self.logger.info(f"Initialized OpenAI client")
        else:
            self.client = None
            self.logger.warning(f"OpenAIClientTool initialized without API key - tool will not be functional")
        
        self.default_model = self.config.get("default_model", "gpt-4")
        self.default_max_tokens = self.config.get("default_max_tokens", 2000)
        self.default_temperature = self.config.get("default_temperature", 0.7)
    
    def get_available_actions(self) -> List[str]:
        return [
            "generate_text",
            "chat_completion",
            "analyze_image",
            "generate_embeddings",
            "function_call",
            "json_completion"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
            "generate_text": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Text prompt"},
                    "model": {"type": "string", "description": "Model to use"},
                    "max_tokens": {"type": "integer", "description": "Maximum tokens"},
                    "temperature": {"type": "number", "description": "Temperature (0-2)"},
                    "top_p": {"type": "number", "description": "Top-p sampling"},
                    "frequency_penalty": {"type": "number", "description": "Frequency penalty"},
                    "presence_penalty": {"type": "number", "description": "Presence penalty"}
                },
                "required": ["prompt"]
            },
            "chat_completion": {
                "type": "object", 
                "properties": {
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                "content": {"type": "string"}
                            },
                            "required": ["role", "content"]
                        }
                    },
                    "model": {"type": "string"},
                    "max_tokens": {"type": "integer"},
                    "temperature": {"type": "number"},
                    "stream": {"type": "boolean"}
                },
                "required": ["messages"]
            },
            "analyze_image": {
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "Image URL or base64 data"},
                    "prompt": {"type": "string", "description": "Analysis prompt"},
                    "model": {"type": "string", "description": "Vision model"},
                    "max_tokens": {"type": "integer"}
                },
                "required": ["image_url", "prompt"]
            },
            "generate_embeddings": {
                "type": "object",
                "properties": {
                    "input": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}}
                        ]
                    },
                    "model": {"type": "string", "description": "Embedding model"}
                },
                "required": ["input"]
            },
            "function_call": {
                "type": "object", 
                "properties": {
                    "messages": {"type": "array"},
                    "functions": {"type": "array"},
                    "function_call": {"type": "string"},
                    "model": {"type": "string"}
                },
                "required": ["messages", "functions"]
            },
            "json_completion": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "schema": {"type": "object", "description": "Expected JSON schema"},
                    "model": {"type": "string"}
                },
                "required": ["prompt"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """Execute OpenAI API calls"""
        # 检查工具是否功能可用
        if not self._functional:
            raise ToolError("OpenAIClientTool not functional - API key required", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "generate_text":
            return await self._generate_text(params)
        elif action == "chat_completion":
            return await self._chat_completion(params)
        elif action == "analyze_image":
            return await self._analyze_image(params)
        elif action == "generate_embeddings":
            return await self._generate_embeddings(params)
        elif action == "function_call":
            return await self._function_call(params)
        elif action == "json_completion":
            return await self._json_completion(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _generate_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate text using OpenAI completion"""
        try:
            response = await self.client.completions.create(
                model=params.get("model", self.default_model),
                prompt=params["prompt"],
                max_tokens=params.get("max_tokens", self.default_max_tokens),
                temperature=params.get("temperature", self.default_temperature),
                top_p=params.get("top_p", 1.0),
                frequency_penalty=params.get("frequency_penalty", 0.0),
                presence_penalty=params.get("presence_penalty", 0.0)
            )
            
            return {
                "content": response.choices[0].text.strip(),
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                "finish_reason": response.choices[0].finish_reason
            }
            
        except Exception as e:
            raise ToolError(f"Text generation failed: {str(e)}", self.metadata.name)
    
    async def _chat_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Chat completion with OpenAI"""
        try:
            response = await self.client.chat.completions.create(
                model=params.get("model", self.default_model),
                messages=params["messages"],
                max_tokens=params.get("max_tokens", self.default_max_tokens),
                temperature=params.get("temperature", self.default_temperature),
                stream=params.get("stream", False)
            )
            
            if params.get("stream", False):
                # Handle streaming response
                content_chunks = []
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        content_chunks.append(chunk.choices[0].delta.content)
                
                return {
                    "content": "".join(content_chunks),
                    "model": params.get("model", self.default_model),
                    "stream": True
                }
            else:
                return {
                    "content": response.choices[0].message.content,
                    "model": response.model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    },
                    "finish_reason": response.choices[0].finish_reason
                }
                
        except Exception as e:
            raise ToolError(f"Chat completion failed: {str(e)}", self.metadata.name)
    
    async def _analyze_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze image using OpenAI Vision"""
        try:
            image_url = params["image_url"]
            prompt = params["prompt"]
            
            # Handle base64 images
            if image_url.startswith("data:image"):
                image_data = image_url
            else:
                image_data = image_url
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data}}
                    ]
                }
            ]
            
            response = await self.client.chat.completions.create(
                model=params.get("model", "gpt-4-vision-preview"),
                messages=messages,
                max_tokens=params.get("max_tokens", 1000)
            )
            
            return {
                "analysis": response.choices[0].message.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
            
        except Exception as e:
            raise ToolError(f"Image analysis failed: {str(e)}", self.metadata.name)
    
    async def _generate_embeddings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate embeddings using OpenAI"""
        try:
            response = await self.client.embeddings.create(
                model=params.get("model", "text-embedding-ada-002"),
                input=params["input"]
            )
            
            embeddings = [data.embedding for data in response.data]
            
            return {
                "embeddings": embeddings,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
            
        except Exception as e:
            raise ToolError(f"Embedding generation failed: {str(e)}", self.metadata.name)
    
    async def _function_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute function calling"""
        try:
            response = await self.client.chat.completions.create(
                model=params.get("model", self.default_model),
                messages=params["messages"],
                functions=params["functions"],
                function_call=params.get("function_call", "auto")
            )
            
            message = response.choices[0].message
            
            result = {
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
            
            if message.function_call:
                result["function_call"] = {
                    "name": message.function_call.name,
                    "arguments": json.loads(message.function_call.arguments)
                }
            else:
                result["content"] = message.content
            
            return result
            
        except Exception as e:
            raise ToolError(f"Function call failed: {str(e)}", self.metadata.name)
    
    async def _json_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate JSON response"""
        try:
            prompt = params["prompt"]
            schema = params.get("schema")
            
            if schema:
                prompt += f"\n\nPlease respond with JSON that matches this schema:\n{json.dumps(schema, indent=2)}"
            
            prompt += "\n\nReturn only valid JSON, no additional text."
            
            response = await self.client.chat.completions.create(
                model=params.get("model", self.default_model),
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            
            try:
                parsed_json = json.loads(content)
            except json.JSONDecodeError:
                # Fallback: try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    parsed_json = json.loads(json_match.group())
                else:
                    raise ToolError("Failed to parse JSON response", self.metadata.name)
            
            return {
                "json_result": parsed_json,
                "raw_content": content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
            
        except Exception as e:
            raise ToolError(f"JSON completion failed: {str(e)}", self.metadata.name)
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """Validate action-specific parameters"""
        if action == "generate_text":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for generate_text")
        
        elif action == "chat_completion":
            messages = parameters.get("messages", [])
            if not messages:
                raise ToolValidationError("messages are required for chat_completion")
            
            for msg in messages:
                if "role" not in msg or "content" not in msg:
                    raise ToolValidationError("Each message must have 'role' and 'content'")
        
        elif action == "analyze_image":
            if not parameters.get("image_url"):
                raise ToolValidationError("image_url is required for analyze_image")
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for analyze_image")
        
        elif action == "generate_embeddings":
            if not parameters.get("input"):
                raise ToolValidationError("input is required for generate_embeddings")
        
        elif action == "function_call":
            if not parameters.get("messages"):
                raise ToolValidationError("messages are required for function_call")
            if not parameters.get("functions"):
                raise ToolValidationError("functions are required for function_call")
        
        elif action == "json_completion":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for json_completion")
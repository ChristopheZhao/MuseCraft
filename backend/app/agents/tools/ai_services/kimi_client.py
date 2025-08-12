"""
Kimi (Moonshot AI) Client Tool - 月之暗面API集成
"""

import json
import httpx
from typing import Dict, Any, List, Optional, Union

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError


class KimiClientTool(AsyncTool):
    """
    Kimi (Moonshot AI) API客户端工具
    
    支持功能：
    - 文本生成和对话
    - 长文本处理（最大200万字符）
    - 中文优化
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="kimi_client",
            version="1.0.0", 
            description="Kimi (月之暗面) API客户端，专为中文优化的大语言模型",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["llm", "ai", "kimi", "moonshot", "chinese", "text-generation"],
            capabilities=[
                "text_generation",
                "chat_completion",
                "long_context",
                "chinese_optimization",
                "json_mode"
            ],
            limitations=[
                "requires_api_key",
                "rate_limited",
                "context_length_limits",
                "cost_per_usage"
            ]
        )
    
    def _initialize(self):
        """初始化Kimi客户端"""
        # 尝试从配置获取API key，如果没有则从环境变量获取
        api_key = self.config.get("api_key")
        if not api_key:
            import os
            api_key = os.getenv("KIMI_API_KEY")
        
        # 工具可以在没有API key时创建，但在使用时会检查
        self._functional = bool(api_key)
        self.api_key = api_key
        
        self.base_url = self.config.get("base_url", "https://api.moonshot.cn/v1")
        self.default_model = self.config.get("default_model", "kimi-k2")  # 使用最新的K2模型
        self.default_max_tokens = self.config.get("default_max_tokens", 2000)
        self.default_temperature = self.config.get("default_temperature", 0.7)
        self.timeout = self.config.get("timeout", 120)
        
        if not self._functional:
            self.logger.warning("KimiClientTool initialized without API key - tool will not be functional")
        
        # 支持的模型列表
        self.supported_models = [
            # Kimi K2 系列 (2025年7月发布)
            "kimi-k2",             # Kimi K2 主模型（推荐）
            "kimi-k2-0711-preview", # Kimi K2 预览版
            
            # 传统 moonshot-v1 系列
            "moonshot-v1-8k",      # 8K上下文
            "moonshot-v1-32k",     # 32K上下文  
            "moonshot-v1-128k",    # 128K上下文
        ]
        
        self.logger.info(f"Initialized Kimi client with model: {self.default_model}")
    
    def get_available_actions(self) -> List[str]:
        return [
            "chat_completion",
            "generate_text",
            "analyze_long_text",
            "json_completion",
            "chinese_writing",
            "translation"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
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
                    "model": {"type": "string", "enum": self.supported_models},
                    "max_tokens": {"type": "integer", "minimum": 1, "maximum": 4096},
                    "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                    "top_p": {"type": "number", "minimum": 0, "maximum": 1},
                    "stream": {"type": "boolean"}
                },
                "required": ["messages"]
            },
            "generate_text": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "文本生成提示"},
                    "model": {"type": "string", "enum": self.supported_models},
                    "max_tokens": {"type": "integer"},
                    "temperature": {"type": "number"},
                    "style": {"type": "string", "enum": ["formal", "casual", "creative", "professional"]}
                },
                "required": ["prompt"]
            },
            "analyze_long_text": {
                "type": "object", 
                "properties": {
                    "text": {"type": "string", "description": "要分析的长文本"},
                    "analysis_type": {
                        "type": "string",
                        "enum": ["summary", "key_points", "sentiment", "topics", "structure"]
                    },
                    "model": {"type": "string", "enum": ["moonshot-v1-32k", "moonshot-v1-128k"]}
                },
                "required": ["text", "analysis_type"]
            },
            "json_completion": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "schema": {"type": "object", "description": "期望的JSON结构"},
                    "model": {"type": "string"}
                },
                "required": ["prompt"]
            },
            "chinese_writing": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "写作主题"},
                    "style": {
                        "type": "string", 
                        "enum": ["narrative", "expository", "persuasive", "creative", "technical"]
                    },
                    "length": {"type": "string", "enum": ["short", "medium", "long"]},
                    "tone": {"type": "string", "enum": ["formal", "casual", "humorous", "serious"]}
                },
                "required": ["topic"]
            },
            "translation": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要翻译的文本"},
                    "source_lang": {"type": "string", "description": "源语言"},
                    "target_lang": {"type": "string", "description": "目标语言"},
                    "style": {"type": "string", "enum": ["literal", "free", "professional"]}
                },
                "required": ["text", "target_lang"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行Kimi API调用"""
        # 检查工具是否功能可用
        if not self._functional:
            raise ToolError("KimiClientTool not functional - API key required", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "chat_completion":
            return await self._chat_completion(params)
        elif action == "generate_text":
            return await self._generate_text(params)
        elif action == "analyze_long_text":
            return await self._analyze_long_text(params)
        elif action == "json_completion":
            return await self._json_completion(params)
        elif action == "chinese_writing":
            return await self._chinese_writing(params)
        elif action == "translation":
            return await self._translation(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _chat_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """对话完成"""
        try:
            payload = {
                "model": params.get("model", self.default_model),
                "messages": params["messages"],
                "max_tokens": params.get("max_tokens", self.default_max_tokens),
                "temperature": params.get("temperature", self.default_temperature),
                "top_p": params.get("top_p", 1.0),
                "stream": params.get("stream", False)
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Kimi API error: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                return {
                    "content": result["choices"][0]["message"]["content"],
                    "model": result["model"],
                    "usage": result.get("usage", {}),
                    "finish_reason": result["choices"][0]["finish_reason"]
                }
                
        except httpx.TimeoutException:
            raise ToolError("Kimi API request timeout", self.metadata.name)
        except Exception as e:
            raise ToolError(f"Chat completion failed: {str(e)}", self.metadata.name)
    
    async def _generate_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """文本生成"""
        try:
            # 构建系统提示
            system_prompt = "你是一个专业的文本生成助手，擅长根据用户需求创作高质量的中文内容。"
            
            style = params.get("style", "professional")
            style_prompts = {
                "formal": "请使用正式、严谨的语言风格。",
                "casual": "请使用轻松、自然的语言风格。", 
                "creative": "请发挥创意，使用生动、有趣的表达方式。",
                "professional": "请使用专业、准确的表达方式。"
            }
            
            if style in style_prompts:
                system_prompt += style_prompts[style]
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": params["prompt"]}
            ]
            
            chat_params = {
                "messages": messages,
                "model": params.get("model", self.default_model),
                "max_tokens": params.get("max_tokens", self.default_max_tokens),
                "temperature": params.get("temperature", self.default_temperature)
            }
            
            return await self._chat_completion(chat_params)
            
        except Exception as e:
            raise ToolError(f"Text generation failed: {str(e)}", self.metadata.name)
    
    async def _analyze_long_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """长文本分析"""
        try:
            text = params["text"]
            analysis_type = params["analysis_type"]
            
            # 选择合适的模型处理长文本
            model = params.get("model")
            if not model:
                text_length = len(text)
                if text_length > 100000:  # 超过10万字符使用128k模型
                    model = "moonshot-v1-128k"
                elif text_length > 30000:  # 超过3万字符使用32k模型
                    model = "moonshot-v1-32k"
                else:
                    model = "moonshot-v1-8k"
            
            # 构建分析提示
            analysis_prompts = {
                "summary": "请对以下文本进行详细摘要，提取核心观点和重要信息：",
                "key_points": "请提取以下文本的关键要点，以清单形式列出：",
                "sentiment": "请分析以下文本的情感倾向和态度：",
                "topics": "请识别以下文本涉及的主要话题和主题：",
                "structure": "请分析以下文本的结构和组织方式："
            }
            
            system_prompt = f"{analysis_prompts.get(analysis_type, '请分析以下文本：')}\n\n{text}"
            
            messages = [
                {"role": "user", "content": system_prompt}
            ]
            
            chat_params = {
                "messages": messages,
                "model": model,
                "max_tokens": 2000,
                "temperature": 0.3  # 分析任务使用较低的温度
            }
            
            result = await self._chat_completion(chat_params)
            result["analysis_type"] = analysis_type
            result["text_length"] = len(text)
            result["model_used"] = model
            
            return result
            
        except Exception as e:
            raise ToolError(f"Long text analysis failed: {str(e)}", self.metadata.name)
    
    async def _json_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:  
        """JSON格式完成"""
        try:
            prompt = params["prompt"]
            schema = params.get("schema")
            
            system_prompt = "你是一个专业的JSON数据生成助手。请根据用户需求生成符合要求的JSON数据。"
            
            if schema:
                system_prompt += f"\n\n请确保返回的JSON符合以下结构：\n{json.dumps(schema, indent=2, ensure_ascii=False)}"
            
            system_prompt += "\n\n请只返回有效的JSON格式，不要包含其他文本。"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            chat_params = {
                "messages": messages,
                "model": params.get("model", self.default_model),
                "temperature": 0.3
            }
            
            result = await self._chat_completion(chat_params)
            
            # 尝试解析JSON
            try:
                json_result = json.loads(result["content"])
                result["json_result"] = json_result
                result["valid_json"] = True
            except json.JSONDecodeError:
                # 尝试提取JSON
                import re
                json_match = re.search(r'\{.*\}', result["content"], re.DOTALL)
                if json_match:
                    try:
                        json_result = json.loads(json_match.group())
                        result["json_result"] = json_result
                        result["valid_json"] = True
                    except:
                        result["valid_json"] = False
                        result["error"] = "Failed to parse JSON from response"
                else:
                    result["valid_json"] = False
                    result["error"] = "No JSON found in response"
            
            return result
            
        except Exception as e:
            raise ToolError(f"JSON completion failed: {str(e)}", self.metadata.name)
    
    async def _chinese_writing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """中文写作"""
        try:
            topic = params["topic"]
            style = params.get("style", "expository")
            length = params.get("length", "medium")
            tone = params.get("tone", "formal")
            
            # 构建写作指导
            style_guides = {
                "narrative": "请以叙述的方式展开，注重情节和细节描述",
                "expository": "请以说明文的方式展开，逻辑清晰，条理分明",
                "persuasive": "请以议论文的方式展开，论证有力，观点鲜明",
                "creative": "请发挥创意，使用生动的语言和独特的表达方式",
                "technical": "请使用专业、准确的技术语言"
            }
            
            length_guides = {
                "short": "请控制在500字以内",
                "medium": "请控制在500-1500字",
                "long": "请写1500字以上的详细内容"
            }
            
            tone_guides = {
                "formal": "使用正式、严谨的语言",
                "casual": "使用轻松、自然的语言",
                "humorous": "适当使用幽默的表达方式",
                "serious": "使用严肃、认真的语调"
            }
            
            system_prompt = f"""你是一位专业的中文写作助手。请根据以下要求创作内容：

主题：{topic}
文体风格：{style_guides.get(style, '')}
长度要求：{length_guides.get(length, '')}
语言风格：{tone_guides.get(tone, '')}

请创作高质量的中文内容，注意语言的准确性和表达的生动性。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请以'{topic}'为主题进行创作。"}
            ]
            
            chat_params = {
                "messages": messages,
                "model": params.get("model", self.default_model),
                "temperature": 0.8  # 创作任务使用较高的温度
            }
            
            result = await self._chat_completion(chat_params)
            result["writing_params"] = {
                "topic": topic,
                "style": style,
                "length": length,
                "tone": tone
            }
            
            return result
            
        except Exception as e:
            raise ToolError(f"Chinese writing failed: {str(e)}", self.metadata.name)
    
    async def _translation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """翻译功能"""
        try:
            text = params["text"]
            source_lang = params.get("source_lang", "auto")
            target_lang = params["target_lang"]
            style = params.get("style", "free")
            
            style_guides = {
                "literal": "请进行直译，保持原文的结构和表达方式",
                "free": "请进行意译，使译文自然流畅",
                "professional": "请使用专业的翻译标准，准确传达原意"
            }
            
            system_prompt = f"""你是一位专业的翻译助手。请将以下文本翻译成{target_lang}。

翻译风格：{style_guides.get(style, '')}
注意保持原文的语气和风格，确保翻译准确、自然。"""
            
            if source_lang != "auto":
                system_prompt += f"\n原文语言：{source_lang}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]
            
            chat_params = {
                "messages": messages,
                "model": params.get("model", self.default_model),
                "temperature": 0.3  # 翻译任务使用较低的温度
            }
            
            result = await self._chat_completion(chat_params)
            result["translation_params"] = {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "style": style
            }
            
            return result
            
        except Exception as e:
            raise ToolError(f"Translation failed: {str(e)}", self.metadata.name)
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "chat_completion":
            messages = parameters.get("messages", [])
            if not messages:
                raise ToolValidationError("messages are required for chat_completion")
            
            for msg in messages:
                if "role" not in msg or "content" not in msg:
                    raise ToolValidationError("Each message must have 'role' and 'content'")
        
        elif action == "generate_text":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for generate_text")
        
        elif action == "analyze_long_text":
            if not parameters.get("text"):
                raise ToolValidationError("text is required for analyze_long_text")
            if not parameters.get("analysis_type"):
                raise ToolValidationError("analysis_type is required for analyze_long_text")
        
        elif action == "chinese_writing":
            if not parameters.get("topic"):
                raise ToolValidationError("topic is required for chinese_writing")
        
        elif action == "translation":
            if not parameters.get("text"):
                raise ToolValidationError("text is required for translation")
            if not parameters.get("target_lang"):
                raise ToolValidationError("target_lang is required for translation")
    
    def get_available_models(self) -> List[str]:
        """获取可用的Kimi模型列表"""
        return self.supported_models.copy()
    
    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str = "kimi-k2") -> Dict[str, float]:
        """
        估算API调用成本（美元）
        
        Args:
            input_tokens: 输入token数量
            output_tokens: 输出token数量
            model: 模型名称
            
        Returns:
            成本估算字典
        """
        # Kimi定价（2025年7月更新）
        pricing = {
            # Kimi K2 系列定价
            "kimi-k2": {
                "input": 0.15,   # $0.15 per 1M input tokens
                "output": 2.50   # $2.50 per 1M output tokens
            },
            "kimi-k2-0711-preview": {
                "input": 0.15,
                "output": 2.50
            },
            
            # 传统 moonshot-v1 系列定价
            "moonshot-v1-8k": {
                "input": 0.012,   # 历史定价，人民币转美元估算
                "output": 0.012
            },
            "moonshot-v1-32k": {
                "input": 0.024,
                "output": 0.024
            },
            "moonshot-v1-128k": {
                "input": 0.060,
                "output": 0.060
            }
        }
        
        if model not in pricing:
            model = "kimi-k2"  # 默认使用K2模型
        
        model_pricing = pricing[model]
        input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
        total_cost = input_cost + output_cost
        
        return {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
            "currency": "USD"
        }
    
    def get_model_capabilities(self, model: str = "kimi-k2") -> Dict[str, Any]:
        """
        获取指定模型的能力信息
        
        Args:
            model: 模型名称
            
        Returns:
            模型能力信息
        """
        capabilities = {
            "kimi-k2": {
                "context_length": 128000,  # 128K上下文
                "supports_tool_calling": True,
                "supports_chinese": True,
                "supports_multimodal": False,
                "architecture": "MoE",  # Mixture of Experts
                "total_parameters": "1T",
                "active_parameters": "32B",
                "recommended_temperature": 0.6,
                "release_date": "2025-07",
                "capabilities": [
                    "智能体能力",
                    "工具调用",
                    "长文本处理",
                    "中文优化",
                    "推理增强"
                ]
            },
            "kimi-k2-0711-preview": {
                "context_length": 128000,
                "supports_tool_calling": True,
                "supports_chinese": True,
                "supports_multimodal": False,
                "architecture": "MoE",
                "total_parameters": "1T",
                "active_parameters": "32B",
                "recommended_temperature": 0.6,
                "release_date": "2025-07",
                "capabilities": [
                    "智能体能力",
                    "工具调用",
                    "长文本处理",
                    "中文优化",
                    "推理增强"
                ],
                "note": "预览版本"
            },
            "moonshot-v1-128k": {
                "context_length": 128000,
                "supports_tool_calling": True,
                "supports_chinese": True,
                "supports_multimodal": False,
                "architecture": "Transformer",
                "recommended_temperature": 0.7,
                "capabilities": [
                    "长文本处理",
                    "中文优化"
                ]
            },
            "moonshot-v1-32k": {
                "context_length": 32000,
                "supports_tool_calling": True,
                "supports_chinese": True,
                "supports_multimodal": False,
                "architecture": "Transformer",
                "recommended_temperature": 0.7,
                "capabilities": [
                    "中等长度文本处理",
                    "中文优化"
                ]
            },
            "moonshot-v1-8k": {
                "context_length": 8000,
                "supports_tool_calling": True,
                "supports_chinese": True,
                "supports_multimodal": False,
                "architecture": "Transformer",
                "recommended_temperature": 0.7,
                "capabilities": [
                    "短文本处理",
                    "中文优化"
                ]
            }
        }
        
        return capabilities.get(model, capabilities["kimi-k2"])
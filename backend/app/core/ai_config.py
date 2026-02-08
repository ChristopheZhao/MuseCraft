"""
AI服务统一配置管理
提供统一的AI模型和服务配置接口
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import json
import logging
from .config import settings


@dataclass
class ModelConfig:
    """单个AI模型配置"""
    name: str
    provider: str  # openai, zhipu, kimi, etc.
    max_tokens: int = 2000
    temperature: float = 0.7
    timeout: int = 60
    cost_per_token: float = 0.0
    capabilities: list = field(default_factory=list)
    fallback_model: Optional[str] = None
    
    enabled: bool = True


@dataclass
class ProviderConfig:
    """AI服务提供商配置"""
    name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: str = ""
    timeout: int = 60
    rate_limit: int = 100
    enabled: bool = True
    models: Dict[str, ModelConfig] = field(default_factory=dict)


class AIConfigManager:
    """AI配置管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.providers: Dict[str, ProviderConfig] = {}
        self.models: Dict[str, ModelConfig] = {}
        self.agent_model_mapping: Dict[str, str] = {}
        self.tool_model_mapping: Dict[str, str] = {}  # 新增：tool -> model 映射
        self.tool_provider_mapping: Dict[str, str] = {}  # 新增：tool -> provider 映射（如 zhipu/doubao）
        self.agent_fallback_model_mapping: Dict[str, str] = {}  # 新增：agent -> fallback_model 映射
        self.agent_thinking_mode: Dict[str, str] = {}  # agent -> "thinking" | "standard"
        self._load_default_config()
        self._load_user_config()
        self._log_resolved_mappings()

    def _log_resolved_mappings(self) -> None:
        try:
            resolved_agents = {
                name: self._resolve_model_alias(model)
                for name, model in (self.agent_model_mapping or {}).items()
            }
            resolved_tools = {
                name: self._resolve_model_alias(model)
                for name, model in (self.tool_model_mapping or {}).items()
            }
            resolved_fallbacks = {
                name: self._resolve_model_alias(model)
                for name, model in (self.agent_fallback_model_mapping or {}).items()
            }
            resolved_providers = {}
            for name, cfg in (self.providers or {}).items():
                default_model = getattr(cfg, "default_model", "")
                resolved_providers[name] = self._resolve_model_alias(default_model) if default_model else default_model
            self.logger.info(
                "AI models resolved: env=%s default=%s light=%s agents=%s tools=%s providers=%s fallbacks=%s",
                getattr(settings, "ENVIRONMENT", "development"),
                settings.GLM_DEFAULT_MODEL,
                settings.GLM_LIGHT_MODEL,
                resolved_agents,
                resolved_tools,
                resolved_providers,
                resolved_fallbacks,
            )
        except Exception as exc:
            self.logger.warning("Failed to log resolved AI model mappings: %s", exc)
    
    def _load_default_config(self):
        """加载默认配置"""
        
        # OpenAI配置
        if settings.OPENAI_API_KEY:
            openai_config = ProviderConfig(
                name="openai",
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
                default_model="gpt-4",
                enabled=bool(settings.OPENAI_API_KEY)
            )
            
            # OpenAI模型配置
            openai_models = {
                "gpt-4": ModelConfig(
                    name="gpt-4",
                    provider="openai",
                    max_tokens=4000,
                    temperature=0.7,
                    cost_per_token=0.03,
                    capabilities=["text_generation", "chat", "reasoning"],
                    fallback_model="gpt-3.5-turbo"
                ),
                "gpt-3.5-turbo": ModelConfig(
                    name="gpt-3.5-turbo",
                    provider="openai",
                    max_tokens=2000,
                    temperature=0.7,
                    cost_per_token=0.002,
                    capabilities=["text_generation", "chat"]
                ),
                "gpt-4-vision-preview": ModelConfig(
                    name="gpt-4-vision-preview",
                    provider="openai",
                    max_tokens=2000,
                    capabilities=["text_generation", "image_analysis"]
                )
            }
            
            openai_config.models = openai_models
            self.providers["openai"] = openai_config
            self.models.update(openai_models)
        
        # 智谱AI配置
        if settings.GLM_API_KEY:
            zhipu_config = ProviderConfig(
                name="zhipu",
                api_key=settings.GLM_API_KEY,
                base_url=settings.GLM_BASE_URL,
                default_model=getattr(settings, "GLM_DEFAULT_MODEL", "glm-4-plus"),
                enabled=bool(settings.GLM_API_KEY)
            )
            
            # GLM模型配置
            glm_models = {
                # GLM-4.5 系列 (最新一代)
                "glm-4.7": ModelConfig(
                    name="glm-4.7",
                    provider="zhipu",
                    max_tokens=settings.LLM_MAX_TOKENS_THINKING,
                    temperature=0.7,
                    capabilities=["text_generation", "chat", "chinese", "reasoning", "long_context", "latest"],
                    fallback_model="glm-4.5-air"
                ),
                "glm-4.5": ModelConfig(
                    name="glm-4.5",
                    provider="zhipu",
                    max_tokens=settings.LLM_MAX_TOKENS_THINKING,
                    temperature=0.7,
                    capabilities=["text_generation", "chat", "chinese", "reasoning", "long_context", "latest"],
                    fallback_model="glm-4.5-air"
                ),
                "glm-4.5-air": ModelConfig(
                    name="glm-4.5-air", 
                    provider="zhipu",
                    max_tokens=settings.LLM_MAX_TOKENS_STANDARD,
                    temperature=0.7,
                    capabilities=["text_generation", "chat", "chinese", "fast", "latest"],
                    fallback_model="glm-4-plus"
                ),
                # GLM-4 系列 (保留兼容性)
                "glm-4": ModelConfig(
                    name="glm-4",
                    provider="zhipu",
                    max_tokens=2000,
                    temperature=0.7,
                    capabilities=["text_generation", "chat", "chinese"],
                    fallback_model="glm-4-plus"
                ),
                "glm-4-plus": ModelConfig(
                    name="glm-4-plus", 
                    provider="zhipu",
                    max_tokens=4000,
                    temperature=0.7,
                    capabilities=["text_generation", "chat", "chinese", "reasoning"],
                    fallback_model="glm-4"
                ),
                "glm-4-0520": ModelConfig(
                    name="glm-4-0520",
                    provider="zhipu", 
                    max_tokens=4000,
                    temperature=0.7,
                    capabilities=["text_generation", "chat", "chinese", "latest"]
                ),
                "glm-4-long": ModelConfig(
                    name="glm-4-long",
                    provider="zhipu",
                    max_tokens=8000,
                    temperature=0.7,
                    capabilities=["text_generation", "long_context", "chinese"]
                ),
                "glm-4-flashx": ModelConfig(
                    name="glm-4-flashx",
                    provider="zhipu",
                    max_tokens=2000,
                    temperature=0.7,
                    capabilities=["text_generation", "fast", "chinese"]
                ),
                "glm-4v": ModelConfig(
                    name="glm-4v",
                    provider="zhipu",
                    max_tokens=2000,
                    capabilities=["text_generation", "image_analysis", "chinese"]
                ),
                "cogview-3": ModelConfig(
                    name="cogview-3",
                    provider="zhipu",
                    capabilities=["image_generation", "chinese"]
                ),
                "cogview-3-plus": ModelConfig(
                    name="cogview-3-plus",
                    provider="zhipu",
                    capabilities=["image_generation", "chinese", "high_quality"]
                ),
                "cogview-4": ModelConfig(
                    name="cogview-4",
                    provider="zhipu",
                    capabilities=["image_generation", "chinese", "high_quality", "latest"]
                ),
                "cogvideox-3": ModelConfig(
                    name="cogvideox-3",
                    provider="zhipu",
                    capabilities=["video_generation", "chinese"]
                )
            }
            
            zhipu_config.models = glm_models
            self.providers["zhipu"] = zhipu_config
            self.models.update(glm_models)
        
        # Kimi配置
        if settings.KIMI_API_KEY:
            kimi_config = ProviderConfig(
                name="kimi",
                api_key=settings.KIMI_API_KEY,
                base_url=settings.KIMI_BASE_URL,
                default_model="kimi-k2",
                enabled=bool(settings.KIMI_API_KEY)
            )
            
            kimi_models = {
                "kimi-k2": ModelConfig(
                    name="kimi-k2",
                    provider="kimi",
                    max_tokens=8000,
                    capabilities=["text_generation", "long_context", "chinese", "agents"]
                )
            }
            
            kimi_config.models = kimi_models
            self.providers["kimi"] = kimi_config
            self.models.update(kimi_models)
        
        # 默认Agent模型映射
        self._set_default_agent_mapping()
    
    def _set_default_agent_mapping(self):
        """设置默认的Agent模型映射"""
        
        # 根据可用的模型智能选择 - 优先使用GLM-4.5
        if "glm-4.5" in self.models:
            concept_model = "glm-4.5"
            script_model = "glm-4.5" 
            quality_model = "glm-4.5-air"
        elif "glm-4-plus" in self.models:
            concept_model = "glm-4-plus"
            script_model = "glm-4-plus" 
            quality_model = "glm-4"
        elif "gpt-4" in self.models:
            concept_model = "gpt-4"
            script_model = "gpt-4"
            quality_model = "gpt-3.5-turbo"
        elif "kimi-k2" in self.models:
            concept_model = "kimi-k2"
            script_model = "kimi-k2"
            quality_model = "kimi-k2"
        else:
            # 如果没有任何模型可用，使用第一个可用模型
            available_models = list(self.models.keys())
            if available_models:
                default_model = available_models[0]
                concept_model = script_model = quality_model = default_model
            else:
                concept_model = script_model = quality_model = "gpt-3.5-turbo"
        
        self.agent_model_mapping = {
            "concept_planner": concept_model,
            "script_writer": script_model,
            "quality_checker": quality_model,
            "audio_generator": concept_model,  # 音频生成也需要理解内容
            "default": concept_model
        }

        # 默认的Agent备用模型映射（用于兜底，不是强制回退链）
        # - 优先选择同系列的轻量模型
        if concept_model == "glm-4.5" and "glm-4.5-air" in self.models:
            self.agent_fallback_model_mapping["concept_planner"] = "glm-4.5-air"
        elif concept_model == "gpt-4" and "gpt-3.5-turbo" in self.models:
            self.agent_fallback_model_mapping["concept_planner"] = "gpt-3.5-turbo"
        else:
            # 若无轻量同系，则回落到默认（不会生效为同名）
            self.agent_fallback_model_mapping["concept_planner"] = self.agent_model_mapping.get("default", concept_model)

        # 设置默认的Agent思维链模式（先验：规划开、执行关）
        self.agent_thinking_mode = {
            # 规划类：开启
            "concept_planner": "thinking",
            "script_writer": "thinking",
            # 执行类：关闭
            "image_generator": "standard",
            "video_generator": "standard",
            "video_composer": "standard",
            "quality_checker": "standard",
            "audio_generator": "standard",
            # 默认：关闭
            "default": "standard",
        }
    
    def _load_user_config(self):
        """加载用户自定义配置"""
        # 构建候选路径，兼容多种仓库布局
        here = Path(__file__).resolve()
        backend_dir = here.parents[2]  # backend/
        repo_root = backend_dir.parent  # project root
        candidates = [
            Path("ai_config.yaml"),
            Path("config/ai_config.yaml"),
            Path("app/config/ai_config.yaml"),
            Path("backend/ai_config.yaml"),
            Path("backend/config/ai_config.yaml"),
            backend_dir / "ai_config.yaml",
            backend_dir / "config/ai_config.yaml",
            repo_root / "backend" / "config" / "ai_config.yaml",
        ]
        # 去重并按出现顺序尝试
        seen = set()
        config_paths = []
        for p in candidates:
            if p not in seen:
                seen.add(p)
                config_paths.append(p)
        
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        user_config = yaml.safe_load(f)
                    
                    self._merge_user_config(user_config)
                    break
                except Exception as e:
                    print(f"Warning: Failed to load user config {config_path}: {e}")
    
    def _merge_user_config(self, user_config: Dict[str, Any]):
        """合并用户配置"""
        
        # 检查环境特定配置
        environment = getattr(settings, 'ENVIRONMENT', 'development')
        if "environments" in user_config and environment in user_config["environments"]:
            env_config = user_config["environments"][environment]
            # 环境配置覆盖通用配置
            if "agent_model_mapping" in env_config:
                self.agent_model_mapping.update(env_config["agent_model_mapping"])
            if "tool_model_mapping" in env_config:
                self.tool_model_mapping.update(env_config["tool_model_mapping"])
            if "tool_provider_mapping" in env_config:
                self.tool_provider_mapping.update(env_config["tool_provider_mapping"])
            if "agent_fallback_model_mapping" in env_config:
                self.agent_fallback_model_mapping.update(env_config["agent_fallback_model_mapping"])
        
        # 更新Agent模型映射
        if "agent_model_mapping" in user_config:
            self.agent_model_mapping.update(user_config["agent_model_mapping"])

        # 更新Tool模型映射（可选）
        if "tool_model_mapping" in user_config:
            self.tool_model_mapping.update(user_config["tool_model_mapping"])

        # 更新Tool提供商映射（可选）
        if "tool_provider_mapping" in user_config:
            self.tool_provider_mapping.update(user_config["tool_provider_mapping"])

        # 更新Agent备用模型映射（可选）
        if "agent_fallback_model_mapping" in user_config:
            self.agent_fallback_model_mapping.update(user_config["agent_fallback_model_mapping"])

        # 更新Agent思维链默认模式
        if "agent_thinking_mode" in user_config:
            self.agent_thinking_mode.update(user_config["agent_thinking_mode"])
        
        # 更新提供商配置（若默认未加载该provider，也允许从用户配置创建占位项，便于注入timeout/default_model）
        if "providers" in user_config:
            for provider_name, provider_config in user_config["providers"].items():
                existing = self.providers.get(provider_name)
                if existing is None:
                    # 创建占位ProviderConfig（api_key由各自service从环境变量读取）
                    existing = ProviderConfig(name=provider_name)
                    self.providers[provider_name] = existing
                # 合入用户配置字段
                if "default_model" in provider_config:
                    existing.default_model = self._resolve_model_alias(provider_config["default_model"])
                if "enabled" in provider_config:
                    existing.enabled = provider_config["enabled"]
                if "timeout" in provider_config:
                    existing.timeout = provider_config["timeout"]
                if "rate_limit" in provider_config:
                    existing.rate_limit = provider_config["rate_limit"]
        
        # 更新模型配置
        if "models" in user_config:
            for model_name, model_config in user_config["models"].items():
                if model_name in self.models:
                    existing = self.models[model_name]
                    if "temperature" in model_config:
                        existing.temperature = model_config["temperature"]
                    if "max_tokens" in model_config:
                        existing.max_tokens = model_config["max_tokens"]
                    if "enabled" in model_config:
                        existing.enabled = model_config["enabled"]
                    if "timeout" in model_config:
                        existing.timeout = model_config["timeout"]
                    if "fallback_model" in model_config:
                        existing.fallback_model = model_config["fallback_model"]

    def _resolve_model_alias(self, model_name: Optional[str]) -> Optional[str]:
        if not model_name:
            return model_name
        if model_name == "glm-default":
            return settings.GLM_DEFAULT_MODEL
        if model_name == "glm-light":
            return settings.GLM_LIGHT_MODEL
        return model_name
    
    def get_model_for_agent(self, agent_name: str) -> str:
        """获取Agent应该使用的模型"""
        model = self.agent_model_mapping.get(agent_name, self.agent_model_mapping["default"])
        return self._resolve_model_alias(model)
    
    def get_model_for_tool(self, tool_name: str) -> Optional[str]:
        """获取工具应该使用的模型（如果配置了）"""
        model = self.tool_model_mapping.get(tool_name)
        return self._resolve_model_alias(model)

    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        resolved = self._resolve_model_alias(model_name)
        return self.models.get(resolved)

    def get_thinking_mode_for_agent(self, agent_name: str) -> str:
        """获取Agent的默认思维链模式: "thinking" | "standard""" 
        return self.agent_thinking_mode.get(agent_name, self.agent_thinking_mode.get("default", "standard"))
    
    def get_provider_config(self, provider_name: str) -> Optional[ProviderConfig]:
        """获取提供商配置"""
        return self.providers.get(provider_name)
    
    def get_model_provider(self, model_name: str) -> Optional[str]:
        """获取模型的提供商"""
        model_config = self.get_model_config(model_name)
        return model_config.provider if model_config else None

    def get_tool_provider(self, tool_name: str) -> Optional[str]:
        """获取工具建议使用的提供商（如 zhipu/doubao）"""
        return self.tool_provider_mapping.get(tool_name)

    def get_fallback_model_for_agent(self, agent_name: str) -> Optional[str]:
        """获取Agent的备用模型：优先显式 agent_fallback_model_mapping，其次当前主模型的 ModelConfig.fallback_model。"""
        if agent_name in self.agent_fallback_model_mapping:
            return self._resolve_model_alias(self.agent_fallback_model_mapping[agent_name])
        primary = self.get_model_for_agent(agent_name)
        mc = self.get_model_config(primary) if primary else None
        fallback = getattr(mc, 'fallback_model', None) if mc else None
        return self._resolve_model_alias(fallback) if fallback else None
    
    def list_available_models(self, capability: Optional[str] = None) -> list:
        """列出可用模型"""
        available = []
        for model_name, model_config in self.models.items():
            if not model_config.enabled:
                continue
            if capability and capability not in model_config.capabilities:
                continue
            
            provider_config = self.get_provider_config(model_config.provider)
            if provider_config and provider_config.enabled:
                available.append(model_name)
        
        return available
    
    def export_config_template(self, output_path: str = "ai_config_template.yaml"):
        """导出配置模板"""
        template = {
            "# AI服务配置模板": "复制此文件为 ai_config.yaml 并修改配置",
            "agent_model_mapping": {
                "concept_planner": "glm-4-plus",
                "script_writer": "glm-4-plus", 
                "quality_checker": "glm-4",
                "audio_generator": "glm-4-plus",
                "default": "glm-4-plus"
            },
            "providers": {
                "zhipu": {
                    "default_model": "glm-4-plus",
                    "enabled": True
                },
                "openai": {
                    "default_model": "gpt-4",
                    "enabled": True
                }
            },
            "models": {
                "glm-4-plus": {
                    "temperature": 0.7,
                    "max_tokens": 4000,
                    "enabled": True
                },
                "glm-4-0520": {
                    "temperature": 0.7, 
                    "max_tokens": 4000,
                    "enabled": True
                },
                "gpt-4": {
                    "temperature": 0.7,
                    "max_tokens": 4000,
                    "enabled": True
                }
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(template, f, default_flow_style=False, allow_unicode=True)
        
        return output_path


# 全局配置管理器实例（延迟初始化）
_ai_config = None


def get_ai_config() -> AIConfigManager:
    """获取AI配置管理器实例（单例模式，延迟初始化）"""
    global _ai_config
    if _ai_config is None:
        _ai_config = AIConfigManager()
    return _ai_config

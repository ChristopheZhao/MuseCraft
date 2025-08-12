"""
依赖注入配置管理 - Python最佳实践实现
通过构造函数注入，杜绝硬编码和隐式依赖
"""

from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass
from abc import ABC, abstractmethod


# 定义配置接口（遵循接口隔离原则）
class ModelConfigProvider(Protocol):
    """模型配置提供者接口"""
    def get_model_name(self) -> str: ...
    def get_max_tokens(self) -> int: ...
    def get_temperature(self) -> float: ...
    def get_timeout(self) -> int: ...


class AgentConfigProvider(Protocol):
    """Agent配置提供者接口"""
    def get_model_for_agent(self, agent_name: str) -> str: ...


@dataclass
class ModelConfig:
    """模型配置数据类 - 不可变配置"""
    name: str
    max_tokens: int = 2000
    temperature: float = 0.7
    timeout: int = 60
    provider: str = "zhipu"
    enabled: bool = True
    
    def __post_init__(self):
        """验证配置有效性"""
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")


@dataclass 
class AgentConfig:
    """Agent配置数据类"""
    agent_name: str
    model_config: ModelConfig
    timeout_seconds: int = 300
    max_retries: int = 2
    
    def __post_init__(self):
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")


class ConfigurationFactory:
    """配置工厂 - 负责创建配置对象"""
    
    def __init__(self, config_data: Dict[str, Any]):
        """
        通过构造函数注入配置数据
        
        Args:
            config_data: 配置字典，来自YAML、JSON或环境变量
        """
        self._config_data = config_data.copy()  # 防御性复制
    
    def create_model_config(self, model_name: str) -> ModelConfig:
        """创建模型配置"""
        model_data = self._config_data.get("models", {}).get(model_name, {})
        
        return ModelConfig(
            name=model_name,
            max_tokens=model_data.get("max_tokens", 2000),
            temperature=model_data.get("temperature", 0.7),
            timeout=model_data.get("timeout", 60),
            provider=model_data.get("provider", "zhipu"),
            enabled=model_data.get("enabled", True)
        )
    
    def create_agent_config(self, agent_name: str) -> AgentConfig:
        """创建Agent配置"""
        # 获取该Agent应使用的模型
        agent_model_mapping = self._config_data.get("agent_model_mapping", {})
        model_name = agent_model_mapping.get(agent_name, agent_model_mapping.get("default", "glm-4-plus"))
        
        # 创建模型配置
        model_config = self.create_model_config(model_name)
        
        # 获取Agent特定配置
        agent_data = self._config_data.get("agents", {}).get(agent_name, {})
        
        return AgentConfig(
            agent_name=agent_name,
            model_config=model_config,
            timeout_seconds=agent_data.get("timeout_seconds", 300),
            max_retries=agent_data.get("max_retries", 2)
        )
    
    def get_model_name_for_agent(self, agent_name: str) -> str:
        """获取Agent应使用的模型名"""
        agent_model_mapping = self._config_data.get("agent_model_mapping", {})
        return agent_model_mapping.get(agent_name, agent_model_mapping.get("default", "glm-4-plus"))


class DependencyContainer:
    """依赖容器 - 管理对象的创建和生命周期"""
    
    def __init__(self, config_factory: ConfigurationFactory):
        """
        通过构造函数注入配置工厂
        
        Args:
            config_factory: 配置工厂实例
        """
        self._config_factory = config_factory
        self._singletons: Dict[str, Any] = {}
    
    def get_agent_config(self, agent_name: str) -> AgentConfig:
        """获取Agent配置（每次创建新实例）"""
        return self._config_factory.create_agent_config(agent_name)
    
    def get_model_config(self, model_name: str) -> ModelConfig:
        """获取模型配置（缓存单例）"""
        cache_key = f"model_config:{model_name}"
        if cache_key not in self._singletons:
            self._singletons[cache_key] = self._config_factory.create_model_config(model_name)
        return self._singletons[cache_key]
    
    def create_tool_with_config(self, tool_class, agent_name: str, **kwargs):
        """
        创建工具实例，注入适当的配置
        
        Args:
            tool_class: 工具类
            agent_name: Agent名称，用于确定模型配置
            **kwargs: 其他工具参数
        """
        agent_config = self.get_agent_config(agent_name)
        
        # 构建工具配置
        tool_config = {
            "default_model": agent_config.model_config.name,
            "default_max_tokens": agent_config.model_config.max_tokens,
            "default_temperature": agent_config.model_config.temperature,
            "timeout": agent_config.model_config.timeout,
            **kwargs  # 允许覆盖默认配置
        }
        
        return tool_class(config=tool_config)


# 配置加载器 - 从不同来源加载配置
class ConfigurationLoader:
    """配置加载器 - 职责单一，只负责加载配置数据"""
    
    @staticmethod
    def load_from_yaml(file_path: str) -> Dict[str, Any]:
        """从YAML文件加载配置"""
        import yaml
        from pathlib import Path
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    @staticmethod
    def load_from_env() -> Dict[str, Any]:
        """从环境变量加载配置"""
        from ..core.config import settings
        
        return {
            "agent_model_mapping": {
                "default": getattr(settings, "GLM_DEFAULT_MODEL", "glm-4-plus")
            },
            "models": {
                getattr(settings, "GLM_DEFAULT_MODEL", "glm-4-plus"): {
                    "max_tokens": 2000,
                    "temperature": 0.7,
                    "timeout": 60,
                    "provider": "zhipu",
                    "enabled": True
                }
            }
        }
    
    @staticmethod
    def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
        """合并多个配置，后面的配置覆盖前面的"""
        result = {}
        for config in configs:
            _deep_merge(result, config)
        return result


def _deep_merge(base_dict: dict, update_dict: dict) -> None:
    """深度合并字典"""
    for key, value in update_dict.items():
        if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
            _deep_merge(base_dict[key], value)
        else:
            base_dict[key] = value


# 工厂函数 - 创建完整的依赖容器
def create_dependency_container(config_file: Optional[str] = None) -> DependencyContainer:
    """
    工厂函数：创建依赖容器
    
    Args:
        config_file: 配置文件路径，为None时使用默认配置
    
    Returns:
        配置好的依赖容器
    """
    loader = ConfigurationLoader()
    
    # 加载基础配置（环境变量）
    base_config = loader.load_from_env()
    
    # 如果提供了配置文件，则合并配置
    if config_file:
        try:
            file_config = loader.load_from_yaml(config_file)
            merged_config = loader.merge_configs(base_config, file_config)
        except FileNotFoundError:
            print(f"Warning: Configuration file {config_file} not found, using base config")
            merged_config = base_config
    else:
        merged_config = base_config
    
    # 创建配置工厂和依赖容器
    config_factory = ConfigurationFactory(merged_config)
    return DependencyContainer(config_factory)


# 全局依赖容器实例（延迟初始化）
_container: Optional[DependencyContainer] = None


def get_container() -> DependencyContainer:
    """获取全局依赖容器（单例模式）"""
    global _container
    if _container is None:
        _container = create_dependency_container("ai_config.yaml")
    return _container


def set_container(container: DependencyContainer) -> None:
    """设置全局依赖容器（用于测试）"""
    global _container
    _container = container
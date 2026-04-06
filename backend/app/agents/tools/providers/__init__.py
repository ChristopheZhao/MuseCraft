"""Provider interfaces for tool dependencies.

工具依赖提供者接口，用于解耦工具实现和具体服务。
工具通过依赖注入获取数据，而不是直接依赖全局单例。

设计原则：
- Protocol 定义契约，不强制继承
- 通用接口方法，保持简洁
- 异步方法，保持接口一致性
- 异常上抛，工具层决定降级策略
"""

from .memory_provider import MemoryProvider, DefaultMemoryProvider

__all__ = [
    "MemoryProvider",
    "DefaultMemoryProvider",
]

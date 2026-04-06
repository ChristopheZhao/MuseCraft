"""
Agent service 层：提供可复用的中立逻辑，避免在 Agent 中堆积业务细节。

命名约定：
- 按领域划分子包，例如 video_generation、image_generation 等。
- 模块内使用中文注释解释用途，保持最小耦合（仅依赖 Python 原生或 utils）。
"""

__all__ = [
    "video_generation",
]

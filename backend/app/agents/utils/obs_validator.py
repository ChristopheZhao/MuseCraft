"""结构化观察校验工具

提供对 LLM 返回的结构化 JSON 文本进行统一的解析与契约（schema）校验：
- 统一使用 safe_json_loads（容错围栏 ```json/``` 与多余空行等）
- 支持严格/非严格两种模式：严格模式抛 AgentError，非严格返回 None
- 可选场景：当 schema.properties 声明了 'scenes' 时，校验其为数组
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .json_utils import safe_json_loads
from ..base import AgentError


def parse_and_validate_structured(
    *,
    content: str,
    schema: Dict[str, Any],
    strict: bool = True,
    logger: Optional[Any] = None,
    context: str = "structured_observation",
    require_scenes_if_declared: bool = True,
) -> Optional[Dict[str, Any]]:
    """解析并校验结构化 JSON 文本。

    Args:
        content: LLM 返回的 content 文本
        schema: JSON Schema（dict）
        strict: 严格模式：任意解析/校验失败均抛 AgentError；否则返回 None
        logger: 可选日志句柄
        context: 日志上下文标签
        require_scenes_if_declared: 若 schema 的 properties 含 'scenes'，则要求 payload.scenes 为数组

    Returns:
        Dict | None：严格模式返回合法对象；非严格模式失败则返回 None
    """
    try:
        data = safe_json_loads(content, logger=logger, context=context, allow_fallback=False)
    except Exception as exc:
        if strict:
            raise AgentError(f"JSON 解析失败：{exc}")
        return None

    if not isinstance(data, dict):
        if strict:
            raise AgentError("结构化结果不是对象（JSON Object）")
        return None

    if not isinstance(schema, dict):
        if strict:
            raise AgentError("无效的 schema（非对象）")
        return None

    if require_scenes_if_declared and isinstance(schema.get("properties"), dict):
        if "scenes" in schema["properties"]:
            if not isinstance(data.get("scenes"), list):
                if strict:
                    raise AgentError("缺少必须字段 'scenes' 或其类型不是数组")
                return None

    # 若可用则进行 jsonschema 校验
    try:
        import jsonschema  # type: ignore
        jsonschema.validate(instance=data, schema=schema)
    except Exception as ve:
        if strict:
            raise AgentError(f"结构化结果未通过 schema 校验：{ve}")
        return None

    return data


__all__ = [
    "parse_and_validate_structured",
]


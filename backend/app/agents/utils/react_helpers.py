from typing import Any, Dict


def resolve_action_label(function_name: Any) -> str:
    """将函数名映射为更友好的事件标签（用于日志）。

    - 由配置项 settings.REACT_ACTION_LABEL_MAP 驱动（前缀 → 标签）
    - 未匹配到时回退为 'act_generic'
    - 仅用于日志，不得用于控制流程判断
    """
    try:
        fn = str(function_name)
    except Exception:
        return "act_generic"
    try:
        from ...core.config import settings as _cfg  # defer import
        mapping = getattr(_cfg, 'REACT_ACTION_LABEL_MAP', {}) or {}
        if isinstance(mapping, dict) and mapping:
            for prefix, label in mapping.items():
                try:
                    if fn.startswith(str(prefix)):
                        return str(label)
                except Exception:
                    continue
    except Exception:
        pass
    return "act_generic"

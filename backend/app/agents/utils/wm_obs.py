"""
WorkingMemory OBS 写入/读取工具（应用层）。

- OBS 仅记录当前轮的执行动作与结果（已精简），统一写入 Agent WM。
- 不做裁剪/决策；如需窗口控制由上层 context manager 处理。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .memory_helpers import get_agent_working_memory

if TYPE_CHECKING:
    from ..memory.short_term.service import WorkingMemoryService

OBS_KEY = "obs_records"

def append_obs_to_wm(
    workflow_id: str,
    agent_name: str,
    obs_record: Dict[str, Any],
    *,
    service: "WorkingMemoryService",
    max_token_budget: int = 3000,
) -> None:
    """将结构化 OBS 记录追加到 Agent WM。

    约束：
    - WM 内存储应为可序列化的 primitives（dict/list/str/int/bool/None），避免运行时对象泄漏；
    - 当超出预算时，不再“整条跳过”，而是做通用截断后写入（避免轨迹断裂）。
    """
    if not workflow_id or not agent_name or not obs_record:
        return
    wm = get_agent_working_memory(str(workflow_id), agent_name, service=service)
    try:
        records = wm.get(OBS_KEY, [])
        if not isinstance(records, list):
            records = []
        # 简易 token 控制：超出阈值时截断写入，后续可替换为精细化摘要/压缩策略
        try:
            from app.agents.utils.json_utils import estimate_tokens, to_jsonable, shrink_jsonable  # type: ignore
            jsonable = to_jsonable(obs_record)
            tokens = estimate_tokens(jsonable)
        except Exception:
            jsonable = obs_record
            tokens = 0
        if max_token_budget and max_token_budget > 0 and tokens > max_token_budget:
            original_tokens = tokens
            # First-pass shrink (keep more detail).
            truncated = shrink_jsonable(jsonable, max_string_chars=600, max_list_items=60, max_dict_items=80, max_depth=7)
            tokens2 = estimate_tokens(truncated)
            # Second-pass shrink (more aggressive).
            if tokens2 > max_token_budget:
                truncated = shrink_jsonable(truncated, max_string_chars=200, max_list_items=20, max_dict_items=40, max_depth=5)
                tokens2 = estimate_tokens(truncated)
            # Last resort: minimal stub, keep iteration index if present.
            if tokens2 > max_token_budget:
                truncated = {
                    "iteration": (jsonable.get("iteration") if isinstance(jsonable, dict) else None),
                    "obs_meta": {
                        "truncated": True,
                        "reason": "over_token_budget",
                        "original_tokens": int(original_tokens),
                        "budget": int(max_token_budget),
                    },
                }
            if isinstance(truncated, dict):
                meta = dict(truncated.get("obs_meta") or {})
                meta.update(
                    {
                        "truncated": True,
                        "reason": "over_token_budget",
                        "original_tokens": int(original_tokens),
                        "budget": int(max_token_budget),
                    }
                )
                truncated["obs_meta"] = meta
            records.append(truncated)
            wm.put(OBS_KEY, records)
            return
        records.append(jsonable)
        wm.put(OBS_KEY, records)
    except Exception:
        return


def get_obs_records_from_wm(
    workflow_id: str,
    agent_name: str,
    *,
    service: "WorkingMemoryService",
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """读取 Agent WM 中的 OBS 记录；limit 为 None 时返回全部。"""
    if not workflow_id or not agent_name:
        return []
    wm = get_agent_working_memory(str(workflow_id), agent_name, service=service)
    try:
        records = wm.get(OBS_KEY, [])
        if not isinstance(records, list):
            return []
        if limit and limit > 0:
            return records[-int(limit):]
        return records
    except Exception:
        return []


__all__ = ["append_obs_to_wm", "get_obs_records_from_wm", "OBS_KEY"]

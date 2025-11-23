"""
WorkingMemory OBS 写入/读取工具（应用层）。

- OBS 仅记录当前轮的执行动作与结果（已精简），统一写入 Agent WM。
- 不做裁剪/决策；如需窗口控制由上层 context manager 处理。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .memory_helpers import get_agent_working_memory

OBS_KEY = "obs_records"


def append_obs_to_wm(
    workflow_id: str,
    agent_name: str,
    obs_record: Dict[str, Any],
    *,
    max_token_budget: int = 3000,
) -> None:
    """将结构化 OBS 记录追加到 Agent WM（不裁剪）。"""
    if not workflow_id or not agent_name or not obs_record:
        return
    wm = get_agent_working_memory(str(workflow_id), agent_name)
    try:
        records = wm.get(OBS_KEY, [])
        if not isinstance(records, list):
            records = []
        # 简易 token 控制：超出阈值时跳过写入，后续可替换为精细化摘要
        try:
            from app.agents.utils.json_utils import estimate_tokens  # type: ignore
            tokens = estimate_tokens(obs_record)
        except Exception:
            tokens = 0
        if max_token_budget and max_token_budget > 0 and tokens > max_token_budget:
            return
        records.append(obs_record)
        wm.put(OBS_KEY, records)
    except Exception:
        return


def get_obs_records_from_wm(
    workflow_id: str,
    agent_name: str,
    *,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """读取 Agent WM 中的 OBS 记录；limit 为 None 时返回全部。"""
    if not workflow_id or not agent_name:
        return []
    wm = get_agent_working_memory(str(workflow_id), agent_name)
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

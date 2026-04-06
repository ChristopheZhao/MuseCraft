from __future__ import annotations

import json
from typing import Any, Dict, List


def build_neutral_act_messages(agent_name: str, observation: Dict[str, Any]) -> List[Dict[str, str]]:
    """构造中立的 FC 消息（用于单轮 PLAN 直接产出调用清单）。

    准则（Prompt Neutrality）：
    - 不出现工具名、参数名或数值范围；仅描述角色与行为约束。
    - 只提供事实 JSON 给模型；由 FC schema 暴露的函数决定可用动作。
    - 有待办时优先行动；确实无法行动时仅返回严格 JSON 合同（observe/replan/halt）。
    - 不嵌入领域/代理特定先验（如“先准备后生成”）；此类先验应体现在每个 agent 的系统模板中。
    """
    try:
        obs_json = json.dumps(observation or {}, ensure_ascii=False)
    except Exception:
        obs_json = str(observation or {})

    system_text = (
        "你是当前任务的执行代理。基于提供的观察事实，优先通过函数调用完成必要步骤；"
        "若确实无法行动，请在 content 返回严格 JSON 的合同（observe/replan/halt）。"
    )

    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": obs_json},
    ]


def inject_after_system(base_messages: List[Dict[str, Any]], inject_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Insert messages right after the leading system messages.

    - Pure helper; does not depend on Agent state
    - Idempotent: if a user message already starts with '进度摘要：', skip injection
    """
    msgs = list(base_messages or [])
    if not inject_messages:
        return msgs
    for m in msgs:
        if isinstance(m, dict) and m.get('role') == 'user' and isinstance(m.get('content'), str):
            if m['content'].strip().startswith('进度摘要：'):
                return msgs
    idx = 0
    while idx < len(msgs) and isinstance(msgs[idx], dict) and msgs[idx].get('role') == 'system':
        idx += 1
    return msgs[:idx] + inject_messages + msgs[idx:]

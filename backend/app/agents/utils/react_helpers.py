from typing import Dict, Any


def merge_react_state_into_working_state(working_state: Dict[str, Any], react_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    将上一轮反思写回的标准化事实（react_state）合并到各 Agent 的本地 working_state。
    - 统一合并 available_prompts（若存在）
    - 统一合并 completed_scenes / failed_scenes（兼容 list 与 dict 映射两种形态）
    - 不做去 IO 操作，不改变其它领域字段
    """
    if not isinstance(working_state, dict):
        return working_state
    if not isinstance(react_state, dict) or not react_state:
        return working_state

    ws = dict(working_state)

    # 1) available_prompts 合并（若存在）
    try:
        ap = dict(ws.get("available_prompts", {}) or {})
        for k, v in (react_state.get("available_prompts", {}) or {}).items():
            ap[str(k)] = v
        if ap:
            ws["available_prompts"] = ap
    except Exception:
        pass

    # 2) completed_scenes 合并
    try:
        comp_ws = ws.get("completed_scenes")
        comp_react = react_state.get("completed_scenes") or []
        # 兼容两种形态：list[dict] 或 dict[scene_number]->dict
        if isinstance(comp_react, dict):
            react_items = list(comp_react.values())
        else:
            react_items = list(comp_react)
        # working_state 可能是 list 或 dict（视频常用 dict，图像常用 list）
        if isinstance(comp_ws, dict):
            comp_map = dict(comp_ws)
            for r in react_items:
                sn = r.get('scene_number') if isinstance(r, dict) else None
                if sn is not None and sn not in comp_map:
                    comp_map[sn] = r
            ws["completed_scenes"] = comp_map
        else:
            comp_list = list(comp_ws or [])
            seen = {(x.get('scene_number') if isinstance(x, dict) else None) for x in comp_list}
            for r in react_items:
                sn = r.get('scene_number') if isinstance(r, dict) else None
                if sn is None or sn not in seen:
                    comp_list.append(r)
                    if sn is not None:
                        seen.add(sn)
            ws["completed_scenes"] = comp_list
    except Exception:
        pass

    # 3) failed_scenes 合并（按 list 处理）
    try:
        fail_ws = list(ws.get("failed_scenes", []) or [])
        seen = {(x.get('scene_number') if isinstance(x, dict) else None) for x in fail_ws}
        for r in (react_state.get("failed_scenes") or []):
            sn = r.get('scene_number') if isinstance(r, dict) else None
            if sn is None or sn not in seen:
                fail_ws.append(r)
                if sn is not None:
                    seen.add(sn)
        ws["failed_scenes"] = fail_ws
    except Exception:
        pass

    return ws

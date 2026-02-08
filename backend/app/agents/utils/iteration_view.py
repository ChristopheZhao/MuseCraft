from __future__ import annotations

"""Agent-level iteration/state view builder.

提供只读的统计/汇总视图（checklist），用于辅助推理/诊断：
- 完成/失败：基于 Agent WM 的 obs_records 派生（本次执行轨迹）
- 失败：以本 Agent 迭代中“生成类工具调用失败”统计补齐（仅统计，不做决策）

不承载产物明细、不引入第二套事实源。
"""

from typing import Any, Dict, Optional, Set, List

from ..memory.short_term.service import WorkingMemoryService, MemoryNotInitializedError
from ..utils.memory_helpers import agent_scope

# 注意：
# - AgentIterationView 是“清单/统计视图”，不承载产物明细（明细仍在 WM）。
# - 不把中间步骤（如一致性资产准备、取尾帧等）计入完成；只统计“最终产物 kind”。


def build_agent_iteration_view(
    workflow_id: str,
    agent_name: str,
    *,
    service: WorkingMemoryService,
    create_if_absent: bool = False,
) -> Dict[str, Any]:
    """
    从 agent-scope WorkingMemory 构建迭代状态视图（统计/汇总）。

    - 只包含计数/汇总，不重复 action/obs/事件明细。
    - 若 create_if_absent=True，则在缺失时创建空 WM（不带 shared_view）。
    """
    scope = agent_scope(workflow_id, agent_name)
    try:
        wm = service.get(workflow_id, scope)
    except MemoryNotInitializedError:
        if not create_if_absent:
            raise
        wm = service.create_or_get(workflow_id, scope, owner_agent=agent_name)

    target_kind = _resolve_target_kind(agent_name)

    completed_scene_numbers: Set[int] = set()
    failed_scene_numbers: Set[int] = set()

    # 完成/失败场景：以“本 Agent 的 obs_records/action_result”作为事实源（本次执行轨迹），不读取 MAS/shared。
    try:
        gen_prefixes = _resolve_generation_tool_prefixes(agent_name)
        obs_records = wm.get("obs_records", []) or []
        if isinstance(obs_records, list):
            for rec in obs_records:
                if not isinstance(rec, dict):
                    continue
                ar = rec.get("action_result")
                if not isinstance(ar, dict):
                    continue

                # 1) generation_results：若结果里显式携带 scene_number + success，则优先使用
                gen_results = ar.get("generation_results")
                if isinstance(gen_results, list):
                    for item in gen_results:
                        if not isinstance(item, dict):
                            continue
                        sn = item.get("scene_number")
                        if sn is None:
                            continue
                        try:
                            sn_int = int(sn)
                        except Exception:
                            continue
                        if item.get("success") is True:
                            completed_scene_numbers.add(sn_int)
                        elif item.get("success") is False:
                            failed_scene_numbers.add(sn_int)

                # 2) act_log / executed_calls：仅统计“生成类工具”的成功/失败（避免把中间工具计入完成）
                candidates: List[Dict[str, Any]] = []
                if isinstance(ar.get("act_log"), list):
                    candidates = [x for x in (ar.get("act_log") or []) if isinstance(x, dict)]
                elif isinstance(ar.get("executed_calls"), list):
                    candidates = [x for x in (ar.get("executed_calls") or []) if isinstance(x, dict)]
                for item in candidates:
                    tool_name = item.get("tool")
                    if not isinstance(tool_name, str):
                        continue
                    if gen_prefixes and not any(tool_name.startswith(pfx) for pfx in gen_prefixes):
                        continue
                    sn = item.get("scene_number")
                    if sn is None:
                        continue
                    try:
                        sn_int = int(sn)
                    except Exception:
                        continue
                    if item.get("success") is True:
                        completed_scene_numbers.add(sn_int)
                    elif item.get("success") is False:
                        failed_scene_numbers.add(sn_int)
        # 若同一场景本次执行最终成功，则不再视为失败
        failed_scene_numbers.difference_update(completed_scene_numbers)
    except Exception:
        pass

    return {
        "workflow_id": str(workflow_id),
        "agent": str(agent_name),
        "target_kind": target_kind,
        "completed_scene_numbers": sorted(completed_scene_numbers),
        "failed_scene_numbers": sorted(failed_scene_numbers),
    }


def _resolve_target_kind(agent_name: str) -> Optional[str]:
    """Resolve agent's final artifact kind (for `scene_outputs.<kind>`)."""
    name = str(agent_name or "")
    if name == "image_generator":
        return "image"
    if name == "video_generator":
        return "video"
    if name == "voice_synthesizer":
        return "voice"
    if name == "audio_generator":
        return "audio"
    return None


def _resolve_generation_tool_prefixes(agent_name: str) -> Set[str]:
    """Resolve which tool namespaces count as "generation tools" for failure statistics."""
    name = str(agent_name or "")
    if name == "image_generator":
        return {"image_generation.", "image_prompt_composer."}
    if name == "video_generator":
        return {"video_generation."}
    if name == "voice_synthesizer":
        return {"voice_synth_tool."}
    if name == "audio_generator":
        return {"suno_client."}
    return set()


__all__ = ["build_agent_iteration_view"]

from __future__ import annotations

"""观察压缩策略辅助工具（用于 ReAct Agent）。"""

import json
from typing import Any, Dict, List


class ObservationCompressor:
    """用于判定与执行观察载荷压缩的工具类。"""

    def __init__(self, scene_threshold: int, size_threshold: int):
        self.scene_threshold = scene_threshold
        self.size_threshold = size_threshold

    def should_compress(self, observation: Dict[str, Any]) -> bool:
        try:
            scenes = observation.get("scenes") or []
            scene_count = len(scenes) if isinstance(scenes, list) else 0
        except Exception:
            scene_count = 0
        try:
            payload_len = len(json.dumps(observation, ensure_ascii=False))
        except Exception:
            payload_len = 0
        return scene_count > self.scene_threshold or payload_len > self.size_threshold

    @staticmethod
    def build_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "overview": {"type": "string"},
                "recent_action": {"type": "string"},
                "observation_summary": {"type": "string"},
                "notes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["overview", "recent_action", "observation_summary"],
        }

    @staticmethod
    def build_messages(prompt_manager, inject_agent: str, observation: Dict[str, Any]) -> List[Dict[str, str]]:
        obs_json = json.dumps(observation, ensure_ascii=False)
        system = prompt_manager.render_template(
            "observation_compression",
            "system",
            variables={},
            use_cache=True,
            auto_reload=False,
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": obs_json},
        ]


async def maybe_compress_observation(
    *,
    prompt_manager,
    agent_name: str,
    observation: Dict[str, Any],
    llm_structured_observation,
    enabled: bool,
    scene_threshold: int,
    size_threshold: int,
) -> Dict[str, Any]:
    """集中处理“是否压缩 OBS”的逻辑。

    - 受全局 enabled 开关控制。
    - 使用阈值（场景数量/载荷大小）判定是否压缩。
    - 通过注入的 `llm_structured_observation(messages, schema)` 获取结构化概览。
    - 将结果以 `aug`/`aug_meta` 写回 observation；任何错误原因写入 `aug_meta`。
    """
    if not isinstance(observation, dict):
        return observation
    if not enabled:
        observation["aug_meta"] = {"used": False, "reason": "disabled"}
        return observation
    compressor = ObservationCompressor(scene_threshold, size_threshold)
    try:
        if not compressor.should_compress(observation):
            observation["aug_meta"] = {"used": False, "reason": "threshold_not_met"}
            return observation
    except Exception as exc:
        observation["aug_meta"] = {"used": False, "reason": f"threshold_error:{exc.__class__.__name__}"}
        return observation

    try:
        schema = compressor.build_schema()
        messages = compressor.build_messages(prompt_manager, agent_name, observation)
        try:
            aug = await llm_structured_observation(messages, schema)
        except Exception as exc:
            observation["aug_meta"] = {"used": False, "reason": f"error:{exc.__class__.__name__}"}
            return observation
        if isinstance(aug, dict) and aug:
            observation["aug"] = aug
            observation["aug_meta"] = {"used": True, "reason": "threshold"}
        else:
            observation["aug_meta"] = {"used": False, "reason": "empty"}
        return observation
    except Exception as exc:
        observation["aug_meta"] = {"used": False, "reason": f"error:{exc.__class__.__name__}"}
        return observation

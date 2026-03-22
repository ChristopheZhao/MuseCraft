#!/usr/bin/env python3
"""Shared latency probe for Zhipu chat completion under proxy/direct modes."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from typing import Any, Dict, Iterable, List

import httpx

for key in list(os.environ):
    if key.startswith("NEXT_PUBLIC_"):
        os.environ.pop(key, None)

from app.core.config import settings
from app.core.prompt_manager import get_prompt_manager


CONCEPT_PROMPT = """
凡人修仙传预告

生成一个凡人修仙传的预告动漫视频，重点突出韩立从凡人到修仙者的成长、秘境争斗与法宝异象。
整体要求东方玄幻、节奏紧凑、画面宏大，适合做 60 秒左右的预告片。
""".strip()

SKELETON_PAYLOAD: Dict[str, Any] = {
    "overview": "韩立从凡人踏入修仙世界，历经秘境与斗法，最终走向更大天道之争。",
    "genre_and_theme": {
        "genre": "东方玄幻",
        "theme": "凡人逆天改命、谨慎求生、机缘与危机并存",
    },
    "target_audience": "玄幻、国漫、热血成长向观众",
    "key_messages": [
        "凡人也可问鼎大道",
        "机缘背后伴随更高代价",
        "修仙世界危机四伏",
    ],
    "scene_blueprint": [
        {
            "scene_number": 1,
            "title": "山村少年",
            "duration_hint": 8,
            "scene_type": "opening",
            "story_beat": "韩立在凡俗山村仰望修仙者，埋下求道念头",
        },
        {
            "scene_number": 2,
            "title": "初入宗门",
            "duration_hint": 10,
            "scene_type": "setup",
            "story_beat": "进入宗门后见识修仙界残酷规则",
        },
        {
            "scene_number": 3,
            "title": "秘境厮杀",
            "duration_hint": 10,
            "scene_type": "conflict",
            "story_beat": "秘境中争夺资源，法器与阵法齐出",
        },
        {
            "scene_number": 4,
            "title": "掌天瓶异动",
            "duration_hint": 10,
            "scene_type": "reveal",
            "story_beat": "小瓶释放神秘灵光，改变韩立命运",
        },
        {
            "scene_number": 5,
            "title": "雷霆斗法",
            "duration_hint": 12,
            "scene_type": "climax",
            "story_beat": "雷法与飞剑碰撞，韩立险中求胜",
        },
    ],
}

STYLE_PAYLOAD: Dict[str, Any] = {
    "intelligent_style_design": {
        "style_name": "东方玄幻史诗风",
        "style_description": "结合写实角色、恢弘仙侠场景与高强度法术特效。",
        "visual_approach": "高质量 3D 国风动画",
        "narrative_style": "电影预告式快节奏叙事",
        "production_taste": "精致、克制、压迫感强",
        "emotional_tone": "神秘、危险、热血、苍凉",
    },
    "content_elements": {
        "characters": [
            {
                "name": "韩立",
                "role": "主角",
                "appearance": "青衣、清瘦、眼神谨慎但坚毅",
            }
        ],
        "key_props": ["掌天瓶", "飞剑", "符箓"],
    },
    "consistency_hints": {
        "visual": "韩立服饰与掌天瓶形态保持一致",
        "narrative": "由凡俗到修仙高压世界逐步升级",
        "color_palette": ["青灰", "幽绿", "金色雷光"],
    },
}

VOICE_PLAN: Dict[str, Any] = {
    "enabled": True,
    "mode": "narration",
    "persona": "冷静、克制、带一点宿命感的男声旁白",
    "tone_keywords": ["克制", "危险", "史诗感"],
    "style_notes": "句式短促，配合预告剪辑节奏，强化危机与成长感",
    "scene_guidance": [
        {
            "scene_number": 3,
            "should_narrate": True,
            "objective": "强化秘境争斗与资源残酷性",
            "emotion": "紧张",
            "key_points": ["秘境", "争夺", "杀机"],
            "pace_tag": "fast",
            "target_char_count": 45,
        },
        {
            "scene_number": 5,
            "should_narrate": True,
            "objective": "强化巅峰斗法与命运转折",
            "emotion": "热血",
            "key_points": ["雷法", "生死", "逆转"],
            "pace_tag": "fast",
            "target_char_count": 48,
        },
    ],
}

SCENE_BATCH: List[Dict[str, Any]] = [
    {
        "scene_number": 4,
        "title": "掌天瓶异动",
        "duration_hint": 10,
        "scene_type": "reveal",
        "story_beat": "小瓶释放神秘灵光，改变韩立命运",
    },
    {
        "scene_number": 5,
        "title": "雷霆斗法",
        "duration_hint": 12,
        "scene_type": "climax",
        "story_beat": "雷法与飞剑碰撞，韩立险中求胜",
    },
]


def _compact_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _build_system_prompt() -> str:
    prompt_manager = get_prompt_manager()
    mas_system = (
        prompt_manager.render_template("mas_system", "system", variables={}, use_cache=True, auto_reload=False)
        or ""
    ).strip()
    agent_system = (
        prompt_manager.render_template("concept_planner", "system", variables={}, use_cache=True, auto_reload=False)
        or ""
    ).strip()
    parts = [part for part in (mas_system, agent_system) if part]
    return "\n\n".join(parts).strip()


def _build_user_prompt(stage: str) -> str:
    prompt_manager = get_prompt_manager()
    if stage == "skeleton":
        return prompt_manager.render_template(
            "concept_planner",
            "skeleton_generation",
            variables={
                "user_prompt": CONCEPT_PROMPT,
                "duration": 60,
                "aspect_ratio": "16:9",
                "duration_capabilities": [5, 10],
                "scene_count_min": 3,
                "scene_count_max": 10,
                "optimal_scene_count": 5,
            },
            use_cache=True,
            auto_reload=False,
        )

    return prompt_manager.render_template(
        "concept_planner",
        "scene_detail_batch_generation",
        variables={
            "user_prompt": CONCEPT_PROMPT,
            "user_prompt_brief": CONCEPT_PROMPT[:600],
            "skeleton_json": _compact_json(SKELETON_PAYLOAD),
            "style_guidance_json": _compact_json(STYLE_PAYLOAD),
            "voice_plan_json": _compact_json({"voice_plan": VOICE_PLAN}),
            "scene_batch_json": _compact_json(SCENE_BATCH),
            "duration_capabilities": [5, 10],
        },
        use_cache=True,
        auto_reload=False,
    )


def _build_messages(stage: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": _build_user_prompt(stage)},
    ]


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure Zhipu latency under proxy or direct mode")
    parser.add_argument("--mode", choices=["proxy", "direct"], required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--stage", choices=["scene", "skeleton"], default="scene")
    parser.add_argument("--model", default="")
    parser.add_argument("--max-tokens", type=int, default=12800)
    parser.add_argument("--temperature", type=float, default=0.7)
    return parser.parse_args(list(argv))


async def _single_call(
    *,
    trust_env: bool,
    timeout_seconds: float,
    model: str,
    stage: str,
    max_tokens: int,
    temperature: float,
) -> Dict[str, Any]:
    messages = _build_messages(stage)
    payload = {
        "model": model or settings.GLM_DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.7,
        "stream": False,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }
    headers = {
        "Authorization": f"Bearer {settings.GLM_API_KEY}",
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=trust_env) as client:
            response = await client.post(
                f"{settings.GLM_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
        elapsed = time.perf_counter() - started
        if response.status_code != 200:
            return {
                "ok": False,
                "elapsed": elapsed,
                "status_code": response.status_code,
                "error": response.text,
            }
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) or {}
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        return {
            "ok": True,
            "elapsed": elapsed,
            "status_code": response.status_code,
            "finish_reason": choice.get("finish_reason"),
            "content_len": len(content) if isinstance(content, str) else 0,
            "reasoning_len": len(reasoning) if isinstance(reasoning, str) else 0,
        }
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        return {
            "ok": False,
            "elapsed": elapsed,
            "status_code": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def run_probe(args: argparse.Namespace) -> int:
    if not settings.GLM_API_KEY:
        print("GLM_API_KEY missing")
        return 2

    trust_env = args.mode == "proxy"
    print(
        json.dumps(
            {
                "mode": args.mode,
                "trust_env": trust_env,
                "stage": args.stage,
                "runs": args.runs,
                "timeout": args.timeout,
                "model": args.model or settings.GLM_DEFAULT_MODEL,
                "base_url": settings.GLM_BASE_URL,
                "http_proxy": os.getenv("http_proxy") or os.getenv("HTTP_PROXY"),
                "https_proxy": os.getenv("https_proxy") or os.getenv("HTTPS_PROXY"),
                "no_proxy": os.getenv("NO_PROXY") or os.getenv("no_proxy"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    results: List[Dict[str, Any]] = []
    for idx in range(args.runs):
        result = await _single_call(
            trust_env=trust_env,
            timeout_seconds=args.timeout,
            model=args.model,
            stage=args.stage,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        result["run"] = idx + 1
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))

    ok_latencies = [item["elapsed"] for item in results if item.get("ok")]
    summary = {
        "mode": args.mode,
        "stage": args.stage,
        "runs": len(results),
        "successes": len(ok_latencies),
        "failures": len(results) - len(ok_latencies),
        "min_elapsed": min(ok_latencies) if ok_latencies else None,
        "avg_elapsed": statistics.mean(ok_latencies) if ok_latencies else None,
        "max_elapsed": max(ok_latencies) if ok_latencies else None,
    }
    print("--- summary ---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok_latencies else 1


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or [])
    return asyncio.run(run_probe(args))


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))

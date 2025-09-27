"""Diagnostic script for multi-stage ConceptPlanner pipeline."""

import argparse
import asyncio
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from textwrap import dedent
from typing import Dict, Iterable, List, Any
from types import SimpleNamespace

import httpx

os.environ.pop("NEXT_PUBLIC_HERO_VIDEO_URL", None)

try:
    from app.core.config import settings  # type: ignore
    SETTINGS_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # noqa: BLE001
    SETTINGS_IMPORT_ERROR = exc
    settings = SimpleNamespace(  # type: ignore
        AVAILABLE_SCENE_DURATIONS=[5, 10],
        SCENE_COUNT_RANGE_MIN=3,
        SCENE_COUNT_RANGE_MAX=10,
        CONCEPT_PLANNER_TIMEOUT_SECONDS=200,
        LLM_PRIMARY_TIMEOUT_RATIO=0.5,
    )

from app.core.prompt_manager import get_prompt_manager

try:
    from app.core.ai_config import get_ai_config  # type: ignore
    AI_CONFIG_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # noqa: BLE001
    get_ai_config = None  # type: ignore
    AI_CONFIG_IMPORT_ERROR = exc

try:
    from app.agents.tools.ai_services.zhipu_services import ZhipuLLMService  # type: ignore
    ZHIPU_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # noqa: BLE001
    ZhipuLLMService = None  # type: ignore
    ZHIPU_IMPORT_ERROR = exc


@dataclass
class TestCase:
    key: str
    title: str
    prompt: str
    duration: int = 60
    aspect_ratio: str = "16:9"
    prompt_profile: str = "concept_planner"
    system_prompt_override: str | None = None


SIMPLE_SYSTEM_PROMPT = dedent(
    """你是一名短视频概念助手。请仅输出 JSON 对象，字段包括：
- idea: 简短概念总结
- key_actions: 一个包含 3 项的数组，每项描述一个具体动作或画面
- duration_seconds: 推荐的总时长（整数）
除 JSON 外不要输出任何额外文字。"""
).strip()


TEST_CASES: Dict[str, TestCase] = {
    "morning_run": TestCase(
        key="morning_run",
        title="城市晨跑（常规测试）",
        prompt=dedent(
            """
            城市晨跑

            制作一个时长约60秒的都市清晨运动短片。内容聚焦一位年轻人在黎明时分沿着河畔慢跑，展现城市苏醒、阳光洒落、晨练人群和活力音乐带来的积极氛围。
            画面风格需要清新、真实，突出都市建筑与自然景观的对比。请安排3-5个场景，包括：起跑准备、穿越城市地标、沿河跑步、与其他晨练者互动、冲过临时终点的轻松瞬间等。
            配乐建议使用轻快电子与原声乐器结合，旁白（如需要）只做简短激励。整体基调积极、励志，适合社交媒体传播。
            """
        ).strip(),
    ),
    "micro": TestCase(
        key="micro",
        title="极简健康提示（对照测试）",
        prompt=dedent(
            """
            健康觉醒：制作一段 60 秒以内的极简健康提醒短片，强调晨起饮水、伸展、深呼吸三个步骤。
            场景可以是抽象插画或轻实拍镜头，语气要亲切友好，让观众快速明白每日健康仪式。
            """
        ).strip(),
        prompt_profile="simple",
        system_prompt_override=SIMPLE_SYSTEM_PROMPT,
    ),
    "concept": TestCase(
        key="concept",
        title="万法归尘（概念规划场景）",
        prompt=dedent(
            """
            万法归尘

            生成一个唯美史诗风格的仙侠预告片，画面充满 幻想色彩，强调自然灵性流失与凋零的悲怆美感。
            故事以一个正在凋零的仙境世界为背景，展现灵气枯竭带来的"寂灭"灾难。画面从极致唯美的仙境开始——灵鹿在发光森林中奔跑，浮空山峦间瀑布如银河倒挂，但这些美好逐渐转化为悲剧：灵鹿在奔跑中石化成栩栩如生的玉雕，瀑布凝固为巨大水晶，展现万物失去生机的过程。
            主角是一位身着素衣、气质空灵的少女，拥有神农血脉，能以指尖微弱绿光暂时延缓灵花凋零。她在古老观星台研究星光古图，寻找传说中的"心源"——灵气根源。预告片展现她背起药篓踏上征途，穿越水晶化的瀚海沙漠，与因寂灭而狂暴的上古凶兽战斗，并遇见神秘的亦正亦邪白发青年并肩作战。
            幽暗深渊神殿中，模糊黑影端坐王座，无数生机流光被其吸入体内，暗示着幕后黑手的存在。当主角历经千辛万苦找到"心源"——一颗正在碎裂的巨大水晶心脏时，白发青年突然出现，神情复杂地阻止她，暗示着更深的真相。
            整个预告片的视觉风格融合水墨画的留白意境与仙侠的瑰丽想象，色调从开始的绚烂逐渐过渡到苍白凋零，最后在悬念中达到高潮。片名"万法归尘"以带有裂纹、逐渐化为尘埃的特效字体呈现，强化凋零主题。配乐应结合古筝、箫等传统乐器与史诗管弦乐，营造悲壮唯美的氛围。预告片的配音要体现关键点和未完待续的悬念
            """
        ).strip(),
        duration=60,
    ),
}


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="概念规划 LLM 联调/对比测试辅助脚本"
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=["zhipu", "kimi"],
        help="指定要测试的模型供应商，可重复传入以测试多个供应商",
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=sorted(TEST_CASES.keys()),
        help="要运行的测试用例 key，可重复传入以一次性跑多个用例",
    )
    parser.add_argument(
        "--model",
        help="覆盖默认模型：格式为 provider:model，或直接传入模型名作为通用覆盖",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="覆盖单次请求超时时长（秒）",
    )
    parser.add_argument(
        "--style",
        help="可选：额外注入的风格偏好提示",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="仅列出可用用例并退出",
    )
    return parser.parse_args(argv)


def list_available_cases() -> None:
    print("可用测试用例如下：")
    for case in TEST_CASES.values():
        print(
            f"  - {case.key}: {case.title} "
            f"(时长={case.duration}s, 纵横比={case.aspect_ratio})"
        )


def parse_env_list(var_name: str) -> List[str]:
    value = os.getenv(var_name)
    if not value:
        return []
    return [part.strip().lower() for part in value.split(',') if part.strip()]


def parse_model_overrides(raw: str | None) -> Dict[str, str]:
    if not raw:
        return {}
    overrides: Dict[str, str] = {}
    parts = [segment.strip() for segment in raw.split(',') if segment.strip()]
    if len(parts) == 1 and ':' not in parts[0]:
        overrides['*'] = parts[0]
        return overrides
    for part in parts:
        if ':' in part:
            provider, model = part.split(':', 1)
            provider_key = provider.strip().lower()
            model_name = model.strip()
            if provider_key and model_name:
                overrides[provider_key] = model_name
        else:
            overrides['*'] = part
    return overrides


def compute_request_timeout(timeout_override: int | None) -> int:
    total_timeout = int(getattr(settings, "CONCEPT_PLANNER_TIMEOUT_SECONDS", 200))
    timeout_ratio = float(getattr(settings, "LLM_PRIMARY_TIMEOUT_RATIO", 0.5))
    base_timeout = max(5, int(total_timeout * timeout_ratio))
    if timeout_override is not None:
        base_timeout = max(5, int(timeout_override))
    return base_timeout


def build_prompt_context(test_case: TestCase) -> Dict[str, Any]:
    raw_capabilities = getattr(settings, "AVAILABLE_SCENE_DURATIONS", [5, 10])
    duration_capabilities = sorted({int(cap) for cap in raw_capabilities if cap}) or [5, 10]
    scene_count_min = getattr(settings, "SCENE_COUNT_RANGE_MIN", 3)
    scene_count_max = getattr(settings, "SCENE_COUNT_RANGE_MAX", 10)
    max_capability = max(duration_capabilities)
    optimal_scene_count = math.ceil(test_case.duration / max_capability)
    optimal_scene_count = max(scene_count_min, min(optimal_scene_count, scene_count_max))
    return {
        "duration_capabilities": duration_capabilities,
        "scene_count_min": scene_count_min,
        "scene_count_max": scene_count_max,
        "optimal_scene_count": optimal_scene_count,
    }


def build_system_prompt() -> str:
    prompt_manager = get_prompt_manager()
    mas_system = (
        prompt_manager.render_template("mas_system", "system", variables={}, use_cache=True, auto_reload=False)
        or ""
    ).strip()
    agent_system = (
        prompt_manager.render_template("concept_planner", "system", variables={}, use_cache=True, auto_reload=False)
        or ""
    ).strip()

    parts: List[str] = []
    if mas_system:
        parts.append(mas_system)
    if agent_system and agent_system not in parts:
        parts.append(agent_system)
    return "\n\n".join(parts).strip()


def compose_messages(system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    return messages


def safe_json_loads(raw: str) -> Dict[str, Any]:
    content = (raw or "").strip()
    if not content:
        raise ValueError("LLM response content is empty")
    if content.startswith("```json"):
        content = content[7:]
    if content.endswith("```"):
        content = content[:-3]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response is not a JSON object")
    return parsed


def build_prompt_snippet(text: str, limit: int = 600) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def compact_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return "{}"


def build_simple_messages(
    test_case: TestCase,
    style_preference: str | None,
) -> tuple[List[Dict[str, str]], str, str]:
    system_prompt = (test_case.system_prompt_override or SIMPLE_SYSTEM_PROMPT).strip()
    user_parts = [test_case.prompt]
    if style_preference:
        user_parts.append(f"风格提示：{style_preference.strip()}")
    user_parts.append("请只输出符合要求的 JSON。")
    user_prompt = "\n\n".join(part.strip() for part in user_parts if part.strip()).strip()
    return compose_messages(system_prompt, user_prompt), system_prompt, user_prompt


async def call_stage(
    provider: str,
    *,
    template: str,
    stage_label: str,
    variables: Dict[str, Any],
    system_prompt: str,
    model_override_map: Dict[str, str],
    timeout_override: int | None,
    request_timeout_override: int | None,
    max_tokens_override: int,
    temperature_override: float,
) -> Dict[str, Any]:
    prompt_manager = get_prompt_manager()
    user_prompt = prompt_manager.render_template(
        "concept_planner",
        template,
        variables=variables,
        use_cache=True,
        auto_reload=False,
    )
    print(f"\n=== {stage_label} user prompt ===")
    print(user_prompt)
    print(f"{stage_label} prompt length: {len(user_prompt)} chars")
    messages = compose_messages(system_prompt, user_prompt)
    response = await execute_provider(
        provider,
        messages,
        stage_label=stage_label,
        model_override_map=model_override_map,
        timeout_override=timeout_override,
        request_timeout_override=request_timeout_override,
        max_tokens_override=max_tokens_override,
        temperature=temperature_override,
    )
    if not response:
        raise RuntimeError(f"Stage {stage_label} failed")
    return response


async def execute_provider(
    provider: str,
    messages: List[Dict[str, str]],
    *,
    stage_label: str,
    model_override_map: Dict[str, str],
    timeout_override: int | None,
    request_timeout_override: int | None,
    max_tokens_override: int,
    temperature: float,
) -> Dict[str, Any] | None:
    request_timeout = request_timeout_override or compute_request_timeout(timeout_override)
    model_from_override = model_override_map.get(provider) or model_override_map.get('*')
    messages_payload = [dict(m) for m in messages]

    if provider == "kimi":
        concept_model = model_from_override or "kimi-k2-0905-preview"
        api_key = os.getenv("KIMI_API_KEY")
        if not api_key:
            print("[warning] KIMI_API_KEY not configured")
            return None
        print(
            f"\n--- 供应商: kimi | 阶段: {stage_label} | 模型: {concept_model} | 超时: {request_timeout} 秒 ---"
        )
        payload = {
            "model": concept_model,
            "messages": messages_payload,
            "max_tokens": min(max_tokens_override, 4096),
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await client.post(
                    "https://api.moonshot.cn/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException:
            duration = time.perf_counter() - start
            print(f"请求失败，用时 {duration:.2f} 秒：Kimi API 请求超时")
            return None
        except Exception as exc:  # noqa: BLE001
            duration = time.perf_counter() - start
            print(f"请求失败，用时 {duration:.2f} 秒：{exc}")
            return None
        duration = time.perf_counter() - start
        if response.status_code != 200:
            print(f"请求失败，用时 {duration:.2f} 秒：{response.status_code} - {response.text}")
            return None
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) or {}
        print(f"请求成功，用时 {duration:.2f} 秒")
        print("content:", message.get("content"))
        print("usage:", data.get("usage"))
        return {"content": message.get("content"), "usage": data.get("usage", {})}

    if provider != "zhipu":
        print(f"[warning] 未识别的供应商 '{provider}'，跳过")
        return None

    concept_model = model_from_override or "glm-4.5"
    if get_ai_config is not None:
        try:
            ai_config = get_ai_config()
            if model_from_override is None:
                concept_model = ai_config.get_model_for_agent("concept_planner")
        except Exception as exc:  # noqa: BLE001
            print(f"[warning] failed to load ai_config, using defaults: {exc}")
    elif AI_CONFIG_IMPORT_ERROR:
        print(f"[warning] ai_config import failed, using defaults: {AI_CONFIG_IMPORT_ERROR}")

    print(
        f"\n--- 供应商: zhipu | 阶段: {stage_label} | 模型: {concept_model} | 超时: {request_timeout} 秒 ---"
    )

    if ZhipuLLMService is None:
        if ZHIPU_IMPORT_ERROR:
            print(f"[warning] ZhipuLLMService unavailable: {ZHIPU_IMPORT_ERROR}")
        return None

    service = ZhipuLLMService()
    if not service.is_available():
        print("Zhipu service not available (missing API key)")
        return None

    start = time.perf_counter()
    try:
        response = await service.function_call(
            messages=messages_payload,
            tools=[],
            model=concept_model,
            temperature=temperature,
            max_tokens=max_tokens_override,
            request_timeout=request_timeout,
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # noqa: BLE001
        duration = time.perf_counter() - start
        print(f"请求失败，用时 {duration:.2f} 秒：{exc}")
        return None
    duration = time.perf_counter() - start
    print(f"请求成功，用时 {duration:.2f} 秒")
    print("content:", response.get("content"))
    print("usage:", response.get("usage"))
    return response


async def run_multi_stage_case(
    provider: str,
    case: TestCase,
    *,
    style_preference: str | None,
    model_override_map: Dict[str, str],
    timeout_override: int | None,
) -> None:
    context = build_prompt_context(case)
    system_prompt = build_system_prompt()

    base_timeout = compute_request_timeout(timeout_override)
    skeleton_timeout = max(40, int(base_timeout * 0.5))
    style_timeout = max(20, int(base_timeout * 0.3))
    voice_timeout = max(15, int(base_timeout * 0.25))
    scene_timeout = max(30, int(base_timeout * 0.35))

    standard_limit = int(getattr(settings, "LLM_MAX_TOKENS_STANDARD", 12800) or 12800)
    skeleton_tokens = max(800, int(0.2 * standard_limit))
    style_tokens = max(1200, int(0.35 * standard_limit))
    voice_tokens = max(1000, int(0.25 * standard_limit))
    scene_tokens = max(1500, int(0.35 * standard_limit))

    skeleton = await call_stage(
        provider,
        template="skeleton_generation",
        stage_label="Skeleton",
        variables={
            "user_prompt": case.prompt,
            "duration": case.duration,
            "aspect_ratio": case.aspect_ratio,
            "duration_capabilities": context["duration_capabilities"],
            "scene_count_min": context["scene_count_min"],
            "scene_count_max": context["scene_count_max"],
            "optimal_scene_count": context["optimal_scene_count"],
        },
        system_prompt=system_prompt,
        model_override_map=model_override_map,
        timeout_override=timeout_override,
        request_timeout_override=skeleton_timeout,
        max_tokens_override=skeleton_tokens,
        temperature_override=0.65,
    )
    skeleton_payload = safe_json_loads(skeleton.get("content", ""))
    print("\n--- Skeleton JSON ---")
    print(json.dumps(skeleton_payload, ensure_ascii=False, indent=2))

    skeleton_json = compact_json(skeleton_payload)
    user_prompt_brief = build_prompt_snippet(case.prompt)

    style = await call_stage(
        provider,
        template="style_elements_generation",
        stage_label="Style & Elements",
        variables={
            "user_prompt": case.prompt,
            "user_prompt_brief": user_prompt_brief,
            "skeleton_json": skeleton_json,
            "style_preference": style_preference,
        },
        system_prompt=system_prompt,
        model_override_map=model_override_map,
        timeout_override=timeout_override,
        request_timeout_override=style_timeout,
        max_tokens_override=style_tokens,
        temperature_override=0.7,
    )
    style_payload = safe_json_loads(style.get("content", ""))
    print("\n--- Style JSON ---")
    print(json.dumps(style_payload, ensure_ascii=False, indent=2))

    voice = await call_stage(
        provider,
        template="voice_plan_generation",
        stage_label="Voice Plan",
        variables={
            "user_prompt": case.prompt,
            "user_prompt_brief": user_prompt_brief,
            "skeleton_json": skeleton_json,
        },
        system_prompt=system_prompt,
        model_override_map=model_override_map,
        timeout_override=timeout_override,
        request_timeout_override=voice_timeout,
        max_tokens_override=voice_tokens,
        temperature_override=0.7,
    )
    voice_payload = safe_json_loads(voice.get("content", ""))
    print("\n--- Voice JSON ---")
    print(json.dumps(voice_payload, ensure_ascii=False, indent=2))

    scene_blueprint = skeleton_payload.get("scene_blueprint", [])
    if not isinstance(scene_blueprint, list) or not scene_blueprint:
        print("[error] Skeleton 未生成 scene_blueprint，终止")
        return

    batches = []
    batch_size = 2
    for i in range(0, len(scene_blueprint), batch_size):
        batches.append(scene_blueprint[i : i + batch_size])

    style_json = compact_json(style_payload)
    voice_json = compact_json(voice_payload)

    all_scenes: List[Dict[str, Any]] = []
    for idx, batch in enumerate(batches, 1):
        scene_resp = await call_stage(
            provider,
            template="scene_detail_batch_generation",
            stage_label=f"Scene Batch {idx}",
            variables={
                "user_prompt": case.prompt,
                "user_prompt_brief": user_prompt_brief,
                "skeleton_json": skeleton_json,
                "style_guidance_json": style_json,
                "voice_plan_json": voice_json,
                "scene_batch_json": compact_json(batch),
                "duration_capabilities": context["duration_capabilities"],
            },
            system_prompt=system_prompt,
            model_override_map=model_override_map,
            timeout_override=timeout_override,
        request_timeout_override=scene_timeout,
        max_tokens_override=scene_tokens,
            temperature_override=0.7,
        )
        scenes_payload = safe_json_loads(scene_resp.get("content", ""))
        print("\n--- Scene Batch JSON ---")
        print(json.dumps(scenes_payload, ensure_ascii=False, indent=2))
        all_scenes.extend(scenes_payload.get("scenes", []))

    print("\n=== Aggregated scenes count:", len(all_scenes))


async def main() -> None:
    args = parse_args(sys.argv[1:])

    if args.list_cases:
        list_available_cases()
        return

    case_keys = [case.lower() for case in args.case] if args.case else parse_env_list("TEST_CONCEPT_CASE")
    if not case_keys:
        case_keys = ["morning_run"]

    providers = [provider.lower() for provider in args.provider] if args.provider else parse_env_list("TEST_CONCEPT_PROVIDER")
    if not providers:
        providers = ["zhipu"]

    style_preference = args.style or os.getenv("TEST_CONCEPT_STYLE")

    timeout_override = args.timeout
    if timeout_override is None:
        env_timeout = os.getenv("TEST_CONCEPT_TIMEOUT")
        if env_timeout:
            try:
                timeout_override = int(env_timeout)
            except ValueError:
                print(f"[warning] invalid TEST_CONCEPT_TIMEOUT value: {env_timeout}")

    model_override_map = parse_model_overrides(args.model or os.getenv("TEST_CONCEPT_MODEL"))

    if SETTINGS_IMPORT_ERROR:
        print(f"[warning] settings import failed, using fallback defaults: {SETTINGS_IMPORT_ERROR}")

    for case_key in case_keys:
        case = TEST_CASES.get(case_key)
        if not case:
            print(f"[warning] unknown case '{case_key}', skipping")
            continue

        print(
            "\n==============================\n"
            f"Case: {case.title} ({case.key})\n"
            "=============================="
        )

        if case.prompt_profile != "concept_planner":
            messages, system_prompt, user_prompt = build_simple_messages(case, style_preference)
            print("=== ConceptPlanner system prompt ===")
            print(system_prompt)
            print("\n=== ConceptPlanner user prompt ===")
            print(user_prompt)
            print(f"\nSystem prompt length: {len(system_prompt)} chars")
            print(f"User prompt length: {len(user_prompt)} chars")
            for provider in providers:
                await execute_provider(
                    provider,
                    messages,
                    stage_label="simple",
                    model_override_map=model_override_map,
                    timeout_override=timeout_override,
                    request_timeout_override=None,
                    max_tokens_override=1200,
                    temperature=0.7,
                )
            continue

        for provider in providers:
            await run_multi_stage_case(
                provider,
                case,
                style_preference=style_preference,
                model_override_map=model_override_map,
                timeout_override=timeout_override,
            )


if __name__ == "__main__":
    asyncio.run(main())

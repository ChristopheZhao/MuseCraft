#!/usr/bin/env python3
import asyncio
import json
import os
import sys
from typing import Any, Dict, List


async def run_once(mode: str = "enforce") -> None:
    # Register tools
    from app.agents.tools import register_default_tools
    register_default_tools()

    # Create agent with injected Zhipu LLM (plan/observe/default)
    from app.agents.video_generator import VideoGeneratorAgent
    from app.agents.tools.ai_services.zhipu_services import ZhipuLLMService
    zhipu = ZhipuLLMService()
    agent = VideoGeneratorAgent(llms={
        'default': zhipu,
        'plan': zhipu,
        'observe': zhipu,
    })

    # Seed working state and last observation
    plan_digest = "debug_video_plan_seed"
    executable = [
        {"scene_number": 1, "title": "英雄启程", "visual_description": "山巅起步", "duration": 6, "depends_on_scene": None},
        {"scene_number": 4, "title": "成功救援", "visual_description": "冰洞团聚", "duration": 6, "depends_on_scene": 3},
    ]
    pending = [
        {"scene_number": 2, "depends_on_scene": 1},
        {"scene_number": 3, "depends_on_scene": 2},
    ]
    facts = {
        "image_map": {1: "https://example.com/img1.jpg", 4: "https://example.com/img4.jpg"},
        "video_map": {},
        "depends_on": {4: 3},
        "continuity_reason": {},
        "continuity_confidence": {},
        "last_frame_map": {},
        "prepared_last_frames": {},
    }
    observation = {
        "executable_scenes": executable,
        "pending_dependent_scenes": pending,
        "task_status": "in_progress",
        "facts": facts,
    }
    agent.iteration_context = {
        "working_state": {
            "context": {
                "agent_overall_plan": {"plan_digest": plan_digest, "version": 1},
            }
        },
        "last_observation": observation,
    }

    # Build planning_roundN system message
    from app.core.prompt_manager import get_prompt_manager
    pm = get_prompt_manager()
    variables = {
        "plan_digest": plan_digest,
        "plan_outline": json.dumps([], ensure_ascii=False),
        "progress_summary": "",
        "scratchpad": "",
        "observation_json": json.dumps(observation, ensure_ascii=False),
    }
    sys_text = pm.render_template("video_generator", "planning_roundN", variables, auto_reload=False)
    if mode == "baseline":
        user_text = (
            "请基于上述信息进行本轮决策：如需执行请使用函数调用表达；文本部分仅输出一个严格JSON的PlanningDecision。"
        )
    else:
        user_text = (
            "请基于上述信息进行本轮决策：当 intent 为 execute 时，必须在同一响应中通过函数调用执行所选对象；"
            "文本部分仅输出一个严格的 PlanningDecision JSON（不要其他文字/围栏）。"
        )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": sys_text},
        {"role": "user", "content": user_text},
    ]

    print("==== Messages Preview ====")
    print((sys_text or "").strip()[:380] + ("..." if len(sys_text or "") > 380 else ""))
    print("-- user --\n" + user_text)

    # Call function_call directly (no execution of tool_calls)
    fc = await agent.llm_function_call(
        messages=messages,
        context_description=f"debug_video_fc_prompt mode={mode}",
        temperature=0.2,
    )

    print("==== FC Summary ====")
    finish = fc.get("finish_reason")
    tcs = fc.get("tool_calls") or []
    print(f"finish_reason={finish}")
    print(f"tool_calls={len(tcs)}")
    if tcs:
        names = [tc.get("function", {}).get("name") for tc in tcs]
        print(f"tool_call_names={names}")
        args0 = tcs[0].get("function", {}).get("arguments")
        if isinstance(args0, str):
            print(f"first_args_preview={(args0[:300] + '...') if len(args0) > 300 else args0}")


def main():
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    mode = "enforce"
    if len(sys.argv) > 1:
        mode = sys.argv[1].strip()
    if mode not in ("baseline", "enforce"):
        print("Usage: python backend/scripts/test_fc_prompt_video_generator.py [baseline|enforce]")
        sys.exit(1)
    asyncio.run(run_once(mode))


if __name__ == "__main__":
    main()


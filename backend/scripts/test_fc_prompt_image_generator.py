#!/usr/bin/env python3
import asyncio
import json
import os
import sys
from typing import List, Dict, Any


async def run_once(mode: str = "enforce") -> None:
    """Run a single FC round to test whether tool_calls are produced under different prompts.

    Modes:
      - enforce: user 提示强调 intent=execute 必须下函数调用（当前实现）
      - baseline: 较弱提示（如需执行请使用函数调用表达）
    """
    from app.agents.tools import register_default_tools
    register_default_tools()

    from app.agents.image_generator import ImageGeneratorAgent
    # 注入 Zhipu LLM 服务（用于 FC 以及必要时的观察），避免“LLM not injected”
    from app.agents.tools.ai_services.zhipu_services import ZhipuLLMService
    zhipu = ZhipuLLMService()
    agent = ImageGeneratorAgent(llms={
        'default': zhipu,
        'plan': zhipu,
        'observe': zhipu,
    })

    # 准备最小上下文与观察/计划变量
    plan_digest = "debug_plan_digest_seed"
    observation = {
        "summary": {"total": 2, "ready": 0, "pending": 2, "completed": 0, "failed": 0},
        "scenes": [
            {"scene_number": 1, "status": "pending"},
            {"scene_number": 5, "status": "pending"},
        ],
        "pending_scenes": [
            {"scene_number": 1, "title": "场景1", "visual_description": "仙侠风山谷，薄雾日出", "duration": 3},
            {"scene_number": 5, "title": "场景5", "visual_description": "夜幕竹林，蜿蜒小径", "duration": 3},
        ],
        "task_status": "in_progress",
    }
    agent.iteration_context = {
        "working_state": {
            "context": {
                "agent_overall_plan": {"plan_digest": plan_digest, "version": 1},
                "intelligent_style": {"style_name": "xianxia"},
                "scenes_to_generate": observation["pending_scenes"],
            }
        },
        "last_observation": observation,
    }

    # 基于 planning_roundN 模板构造 system 消息
    ws = agent.iteration_context.get("working_state", {})
    ctx = ws.get("context", {})
    aop = ctx.get("agent_overall_plan", {})
    try:
        steps = aop.get("steps") or aop.get("stages") or []
        plan_outline = json.dumps(steps[:6], ensure_ascii=False)
    except Exception:
        plan_outline = "[]"
    variables = {
        "plan_digest": aop.get("plan_digest", ""),
        "plan_outline": plan_outline,
        "progress_summary": agent.build_progress_summary() or "",
        "scratchpad": agent.build_scratchpad(k=2) or "",
        "observation_json": json.dumps(observation, ensure_ascii=False),
    }
    sys_text = agent.prompt_manager.render_template(
        "agents/image_generator", "planning_roundN", variables, auto_reload=False
    )

    if mode == "baseline":
        user_text = (
            "请基于上述信息进行本轮决策：如需执行请使用函数调用表达；同时仅在文本部分输出一个严格JSON的PlanningDecision。"
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
    print((sys_text or "").strip()[:400] + ("..." if len(sys_text or "") > 400 else ""))
    print("-- user --\n" + user_text)

    # 运行一次 FC（计划+执行合一）
    fc = await agent.llm_function_call(
        messages=messages,
        context_description=f"debug_fc_prompt mode={mode}",
        temperature=0.2,
    )

    print("==== FC Summary ====")
    finish = fc.get("finish_reason")
    content = (fc.get("content") or "").strip()
    tcs = fc.get("tool_calls") or []
    print(f"finish_reason={finish}")
    print(f"tool_calls={len(tcs)}")
    if tcs:
        names = [tc.get("function", {}).get("name") for tc in tcs]
        print(f"tool_call_names={names}")
        # 预览前一条的参数
        first_args = tcs[0].get("function", {}).get("arguments")
        if isinstance(first_args, str):
            print(f"first_args_preview={(first_args[:300] + '...') if len(first_args) > 300 else first_args}")
    print(f"content_len={len(content)}")
    print(f"content_preview={(content[:300] + '...') if len(content) > 300 else content}")


def main():
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    mode = "enforce"
    if len(sys.argv) > 1:
        mode = sys.argv[1].strip()
    if mode not in ("baseline", "enforce"):
        print("Usage: python backend/scripts/test_fc_prompt_image_generator.py [baseline|enforce]")
        sys.exit(1)
    asyncio.run(run_once(mode))


if __name__ == "__main__":
    main()

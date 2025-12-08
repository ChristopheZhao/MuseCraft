import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from app.agents.concept_planner import ConceptPlannerAgent
from app.agents.image_generator import ImageGeneratorAgent
from unittest.mock import patch
from app.services.memory_provider import build_memory_services


# --- lightweight stubs ---------------------------------------------------- #

@dataclass
class _StubTask:
    task_id: str
    status: str = "pending"

    def update_progress(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
        return None


class _StubExecution:
    def __init__(self) -> None:
        self.output_data: Dict[str, Any] = {}
        self.tokens_used: int = 0
        self.api_calls_made: int = 0
        self.model_parameters: Dict[str, Any] = {}
        self.progress_percentage: int = 0
        self.current_substep: Optional[str] = None

    def update_progress(self, percentage: int, substep: Optional[str] = None) -> None:
        self.progress_percentage = percentage
        self.current_substep = substep

    def estimate_cost(self) -> None:  # pragma: no cover
        return None


class _StubDB:
    def add(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
        return None

    def commit(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
        return None

    def refresh(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
        return None


class _StubWebSocket:
    async def broadcast_to_task(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
        return None


# --- live integration test ------------------------------------------------ #

_LIVE_AGENT_FLAG = bool(os.getenv("LIVE_AGENT_TESTS"))


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.live_agent
@pytest.mark.skipif(
    not _LIVE_AGENT_FLAG,
    reason="Set LIVE_AGENT_TESTS=1 to run live LLM integration tests.",
)
async def test_concept_planner_live_generates_style_block() -> None:
    """Invoke the real ConceptPlannerAgent and assert the style block is populated."""

    # Front-end injected env vars break Settings validation; strip them for this test.
    for key in list(os.environ):
        if key.startswith("NEXT_PUBLIC_"):
            os.environ.pop(key, None)

    agent = ConceptPlannerAgent()
    agent.websocket_manager = _StubWebSocket()

    async def _noop_store(*_args: Any, **_kwargs: Any) -> bool:
        return False

    agent.store_creative_guidance = _noop_store  # type: ignore[attr-defined]

    workflow_id = f"live-test-{uuid.uuid4()}"
    agent.iteration_context = {"workflow_state_id": workflow_id, "task_id": "live-agent-test"}

    task = _StubTask(task_id="live-agent-test")
    execution = _StubExecution()
    db = _StubDB()

    input_payload: Dict[str, Any] = {
        "user_prompt": "生成一个上海美术厂风格的国漫题材动漫短片-猴子捞月",
        "duration": 60,
        "aspect_ratio": "16:9",
        "workflow_state_id": workflow_id,
        "concept_mode": "episode",
    }

    result = await agent._execute_impl(task, input_payload, execution, db)

    concept_plan = result.get("concept_plan") or {}
    style_block = concept_plan.get("intelligent_style_design")

    assert isinstance(style_block, dict) and style_block, "Style block missing from ConceptPlannerAgent output."
    assert style_block.get("style_name"), f"Style name missing: {json.dumps(style_block, ensure_ascii=False)}"

    scenes = concept_plan.get("scenes")
    assert isinstance(scenes, list) and scenes, "Scene list missing; concept planning failed."
    assert all(scene.get("scene_number") for scene in scenes), "Some scenes lack numbering."

    # 无直接 coordinator 访问：可通过 agent 内部或 GlobalMemoryService 检查，这里跳过持久化验证
    stored_plan = result.get("concept_plan") or {}
    assert isinstance(stored_plan, dict) and stored_plan, "Memory slot project.concept_plan 未写入数据"
    stored_style = stored_plan.get("intelligent_style_design")
    assert isinstance(stored_style, dict) and stored_style, "记忆中的 intelligent_style_design 为空"
    assert stored_style.get("style_name"), f"记忆中的 style_name 缺失: {json.dumps(stored_style, ensure_ascii=False)}"

    # 进一步验证图像代理在装配上下文时也能获取到风格设计
    from app.agents.image_generator import ImageGeneratorAgent

    with patch("app.agents.base.get_agent_tools", return_value=[]), patch(
        "app.agents.base.validate_agent_tools",
        return_value={"is_valid": True, "allowed_tools": []},
    ):
        image_agent = ImageGeneratorAgent()
    image_agent.websocket_manager = _StubWebSocket()
    image_agent.iteration_context = {"workflow_state_id": workflow_id, "task_id": "live-agent-test"}

    agent_state = await image_agent._init_agent_state_from_workflow(
        {"workflow_state_id": workflow_id}
    )
    ctx = agent_state.get("context", {})
    img_style = ctx.get("intelligent_style")

    assert isinstance(img_style, dict) and img_style, "ImageAgent 未在上下文中读取到 intelligent_style"
    assert img_style.get("style_name"), f"ImageAgent 上下文 style_name 缺失: {json.dumps(img_style, ensure_ascii=False)}"

import json
from pathlib import Path

import pytest

from app.agents.voice_synthesizer import VoiceSynthesizerAgent
from app.agents.tools import register_default_tools
from app.core.workflow_state import workflow_manager, SceneData


class StubLLM:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    async def chat_completion(self, **kwargs):  # pragma: no cover - simple stub
        self.calls.append(kwargs)
        return {"content": json.dumps({"narration_text": self.text}, ensure_ascii=False)}


@pytest.mark.asyncio
async def test_draft_narration_generates_natural_text(monkeypatch):
    register_default_tools()
    agent = VoiceSynthesizerAgent(llms={})
    stub_llm = StubLLM("我在水草间轻盈穿梭，心里伏着对古卷的好奇。")
    monkeypatch.setattr(agent, "get_llm", lambda key: stub_llm)

    workflow_state = workflow_manager.create_workflow(
        user_prompt="测试旁白",
        style_preference="water-ink",
        duration=60,
        aspect_ratio="16:9",
    )

    scene = SceneData(scene_number=1, duration=6.0, voice_over_text="")
    workflow_state.add_scene(scene)

    scene_context = {
        "scene_number": 1,
        "scene_title": "荷塘水底日常",
        "narrative_description": "小鲤穿梭于水草间，荷塘静谧而灵动。",
        "visual_description": "阳光透过水面洒落，小鱼追逐气泡，充满童趣。",
        "script_text": "【中景】小鲤穿梭在水草之间，尾鳍划出细腻的涟漪。",
        "target_duration": 6.0,
        "voice_guidance": {
            "objective": "引导观众进入世界观",
            "emotion": "轻快",
            "key_points": ["荷塘静谧", "小鲤好奇"],
        },
        "concept_overview": "讲述小鲤阿红追寻古卷的冒险。",
    }

    voice_plan = {
        "mode": "narration",
        "persona": "温柔的旁白者",
        "tone_keywords": ["温暖", "轻盈"],
        "style_notes": "保持童话色彩，语气柔和。",
    }

    narration = await agent._draft_narration(scene_context, voice_plan, workflow_state)

    char_limit = agent._estimate_char_limit(scene_context["target_duration"])
    assert narration
    assert len(narration) <= char_limit
    assert "镜头" not in narration
    assert stub_llm.calls, "LLM 应被调用以生成旁白"
    system_prompt = stub_llm.calls[0]["messages"][0]["content"]
    assert system_prompt.startswith("你是资深中文旁白撰稿人")

    workflow_manager.remove_workflow(workflow_state.task_id)

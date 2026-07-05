import json
from pathlib import Path

import pytest

from app.agents.voice_synthesizer import VoiceSynthesizerAgent
from app.agents.tools import register_default_tools
from app.agents.base import AgentError
from app.services.memory_provider import build_memory_services


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
    agent = VoiceSynthesizerAgent(llms={}, memory_services=build_memory_services())
    stub_llm = StubLLM("我在水草间轻盈穿梭，心里伏着对古卷的好奇。")
    monkeypatch.setattr(agent, "get_llm", lambda key: stub_llm)

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

    with pytest.raises(AgentError):
        await agent._draft_narration(scene_context, voice_plan)

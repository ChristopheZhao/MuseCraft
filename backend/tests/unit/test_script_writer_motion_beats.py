from types import SimpleNamespace

from app.agents.script_writer import ScriptWriterAgent


def test_sanitize_motion_beats_normalizes_segments():
    agent = object.__new__(ScriptWriterAgent)
    agent.logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)

    raw_beats = [
        {"start": "0", "end": "2.5", "visual_focus": "赵子龙冲锋", "description": "进入战场"},
        {"start": 2.5, "duration": 2.5, "visual_focus": "刘备家眷", "beat_summary": "陷入包围"},
    ]

    sanitized = agent._sanitize_motion_beats(raw_beats, scene_duration=6.0)

    assert len(sanitized) == 2
    assert sanitized[0]["start"] == 0.0
    assert sanitized[0]["end"] == 2.5
    assert sanitized[1]["start"] == 2.5
    assert sanitized[1]["end"] > sanitized[1]["start"]


def test_sanitize_motion_beats_clamps_out_of_range():
    agent = object.__new__(ScriptWriterAgent)
    agent.logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)

    raw_beats = [
        {"start": "-1", "end": "15", "visual_focus": "场景全景"},
    ]

    sanitized = agent._sanitize_motion_beats(raw_beats, scene_duration=5.0)

    assert sanitized[0]["start"] == 0.0
    assert sanitized[0]["end"] == 5.0

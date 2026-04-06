from types import SimpleNamespace

from app.agents.script_writer import ScriptWriterAgent
from app.agents.memory.short_term import SceneSnapshot


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


def test_sanitize_action_phases_projects_relative_weights():
    agent = object.__new__(ScriptWriterAgent)
    agent.logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)

    phases = [
        {"phase": "起势", "relative_weight": 1, "observable_actions": "韩立稳住身形"},
        {"phase": "爆发", "relative_weight": 2, "observable_actions": "金光爆开"},
        {"phase": "收束", "relative_weight": 1, "observable_actions": "镜头停在抬头定格"},
    ]

    sanitized = agent._sanitize_action_phases(phases, scene_duration=8.0)

    assert len(sanitized) == 3
    assert sanitized[0]["start"] == 0.0
    assert sanitized[-1]["end"] == 8.0
    assert sanitized[1]["duration"] > sanitized[0]["duration"]


def test_sanitize_action_phases_falls_back_to_motion_beats():
    agent = object.__new__(ScriptWriterAgent)
    agent.logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)

    fallback_beats = [
        {"start": 0.0, "end": 2.0, "duration": 2.0, "visual_focus": "韩立起势", "beat_summary": "稳住身形"},
        {"start": 2.0, "end": 5.0, "duration": 3.0, "visual_focus": "金光爆发", "beat_summary": "黑袍修士被逼退"},
    ]

    sanitized = agent._sanitize_action_phases([], scene_duration=5.0, fallback_beats=fallback_beats)

    assert len(sanitized) == 2
    assert sanitized[0]["phase"] == "韩立起势"
    assert sanitized[1]["observable_actions"] == "黑袍修士被逼退"


def test_normalize_scene_execution_arc_preserves_scene_thesis():
    agent = object.__new__(ScriptWriterAgent)
    agent.logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)

    scene = SceneSnapshot(
        scene_number=3,
        duration=10.0,
        scene_thesis="韩立被压制后正面反击，局势迅速升级为爆炸失控",
        visual_description="黑袍修士悬空压制，韩立在碎石间迎战",
        narrative_description="这一幕负责把正邪对抗推向高峰",
    )

    payload = {
        "opening_state": "黑袍修士悬空压制，韩立提剑迎战",
        "event_trigger": "黑袍修士率先释放紫黑法术洪流",
        "action_phases": [
            {"phase": "交锋", "observable_actions": "韩立飞剑迎击法术洪流"},
            {"phase": "爆发", "observable_actions": "能量对撞失控，山石与气浪一同炸裂"},
        ],
        "end_state": "爆炸强光吞没画面，余波仍在震颤",
    }

    execution_arc = agent._normalize_scene_execution_arc(payload, scene, motion_beats=[])

    assert execution_arc["scene_thesis"].startswith("韩立被压制后正面反击")
    assert execution_arc["opening_state"] == "黑袍修士悬空压制，韩立提剑迎战"
    assert execution_arc["end_state"] == "爆炸强光吞没画面，余波仍在震颤"

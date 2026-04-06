import pytest

from app.agents.memory.context import edit_context as ctx_apply


def test_context_editor_normalizes_minimal_view():
    raw_view = {
        "scenes": [{"scene_number": 1, "depends_on_scene": None}],
        "completed_scene_numbers": ["1"],
        "failed_scene_numbers": [],
        "notes": ["latest note"],
    }
    compacted, receipt = ctx_apply(raw_view, strategy=None, model_name=None)
    assert isinstance(compacted, dict)
    assert "summary" not in compacted
    assert compacted["completed_scene_numbers"] == [1]
    assert compacted["failed_scene_numbers"] == []
    assert compacted["prepared_assets_refs"] == []
    assert compacted["notes"] == ["latest note"]
    assert isinstance(receipt, dict)
    assert receipt.get("compacted") is False


def test_context_editor_drops_legacy_fields():
    raw_view = {
        "scenes": [],
        "summary": {"total": 2, "pending": 2},
        "ready": [{"scene_number": 5}],
        "completed_scene_numbers": [],
    }
    compacted, _ = ctx_apply(raw_view, strategy=None, model_name=None)
    assert "summary" not in compacted
    assert "ready" not in compacted
    assert compacted["scenes"] == []
    assert compacted["completed_scene_numbers"] == []

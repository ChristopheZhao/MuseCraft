import json
from pathlib import Path

import pytest

from app.models import AgentType
from app.services.scene_info_reference_service import (
    SceneInfoReferencePersistenceError,
    persist_scene_info_ref,
)


def test_persist_scene_info_ref_returns_repo_relative_path(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.scene_info_reference_service.settings.TEMP_PATH", str(tmp_path))

    ref = persist_scene_info_ref(
        workflow_id="wf-scene-ref",
        agent_type=AgentType.IMAGE_GENERATOR,
        payload={"scene_overview": {"scenes": [{"scene_number": 1}]}},
    )

    persisted = Path(ref)
    expected = tmp_path / "context" / "image_generator_wf-scene-ref.json"
    assert persisted == expected
    assert persisted.exists()
    assert json.loads(persisted.read_text(encoding="utf-8"))["scene_overview"]["scenes"][0]["scene_number"] == 1


def test_persist_scene_info_ref_raises_explicitly_when_write_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.scene_info_reference_service.settings.TEMP_PATH", str(tmp_path))

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("pathlib.Path.mkdir", _boom)

    with pytest.raises(SceneInfoReferencePersistenceError, match="disk full"):
        persist_scene_info_ref(
            workflow_id="wf-scene-ref-fail",
            agent_type=AgentType.VIDEO_GENERATOR,
            payload={"scene_overview": {"scenes": [{"scene_number": 1}]}},
        )

from pathlib import Path

from app.agents.utils.media_runtime import build_local_public_url, resolve_local_public_path
from app.core.config import settings


def test_build_local_public_url_maps_outputs_path(monkeypatch):
    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", "/tmp/final_outputs")

    local_path = "/tmp/final_outputs/videos/final.mp4"
    public_url = build_local_public_url(local_path)

    assert public_url == "/files/outputs/videos/final.mp4"


def test_resolve_local_public_path_maps_outputs_url(monkeypatch, tmp_path):
    output_root = tmp_path / "final_outputs"
    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", str(output_root))

    local_path = resolve_local_public_path("/files/outputs/videos/final.mp4")

    assert Path(local_path) == (output_root / "videos" / "final.mp4").resolve()

from app.agents.utils.media_runtime import build_local_public_url
from app.core.config import settings


def test_build_local_public_url_maps_outputs_path(monkeypatch):
    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", "/tmp/final_outputs")

    local_path = "/tmp/final_outputs/videos/final.mp4"
    public_url = build_local_public_url(local_path)

    assert public_url == "/files/outputs/videos/final.mp4"

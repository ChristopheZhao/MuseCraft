import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.tools.video_processing.ffmpeg_tool import FFmpegTool


class DummyProcess:
    def __init__(self, returncode: int, stderr: bytes = b"", stdout: bytes = b""):
        self.returncode = returncode
        self._stderr = stderr
        self._stdout = stdout

    async def communicate(self):  # pragma: no cover - simple stub
        await asyncio.sleep(0)
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_add_audio_ducking_fallback(monkeypatch, tmp_path: Path):
    # Pretend ffmpeg is installed
    def fake_run(cmd, *args, **kwargs):
        cmd = cmd or []
        if cmd and cmd[0] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout="0\n", stderr="")
        if cmd and cmd[0] == "ffmpeg" and "-i" in cmd:
            # mimic ffmpeg -i with an audio stream present
            return SimpleNamespace(returncode=0, stdout="", stderr="Stream #0:1: Audio")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    tool = FFmpegTool(
        metadata=FFmpegTool.get_metadata(),
        config={
            "output_dir": tmp_path.as_posix(),
            "temp_dir": (tmp_path / "ffmpeg").as_posix(),
        },
    )
    tool._initialize()

    video_file = tmp_path / "input.mp4"
    audio_file = tmp_path / "bgm.mp3"
    video_file.write_bytes(b"fake-video")
    audio_file.write_bytes(b"fake-audio")

    calls = {"count": 0}

    async def fake_create_process(*cmd, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            # Primary ducking command fails
            return DummyProcess(1, stderr=b"Value 0.000000 for parameter 'makeup'")
        # Fallback command succeeds and writes output file
        output_path = cmd[-1]
        Path(output_path).write_bytes(b"mixed")
        return DummyProcess(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_process)

    result = await tool._add_audio(
        {
            "video_file": video_file.as_posix(),
            "audio_file": audio_file.as_posix(),
            "output_filename": "mixed.mp4",
            "ducking": True,
            "ducking_params": {"makeup": 0.0},
        }
    )

    assert calls["count"] == 2, "Should attempt fallback command"
    assert result["ducking"] is False
    assert Path(result["output_file"]).exists()

"""Video domain adapter exports."""
from __future__ import annotations

from .models import SceneSnapshot, SceneArtifact
from .memory_adapter import VideoMemoryAdapter, VideoMemoryState


def video_memory(wm) -> VideoMemoryAdapter:
    """Convenience helper to construct adapter for a WorkingMemory instance."""
    return VideoMemoryAdapter(wm)

__all__ = [
    "SceneSnapshot",
    "SceneArtifact",
    "VideoMemoryAdapter",
    "VideoMemoryState",
    "video_memory",
]

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SceneSnapshot:
    """领域模型：描述单个视频场景。"""

    scene_number: int
    depends_on_scene: Optional[int] = None
    duration: float = 0.0
    visual_description: str = ""
    narrative_description: str = ""
    image_url: str = ""
    motion_beats: List[Dict[str, Any]] = field(default_factory=list)

    def as_fact(self) -> Dict[str, Any]:
        return {
            "scene_number": self.scene_number,
            "depends_on_scene": self.depends_on_scene,
            "duration": self.duration,
            "visual_description": self.visual_description,
            "narrative_description": self.narrative_description,
            "image_url": self.image_url,
            "has_reference_image": bool(self.image_url),
            "motion_beats": self.motion_beats,
        }


@dataclass
class SceneArtifact:
    """领域模型：描述视频场景产出物。"""

    video_url: str = ""
    video_path: str = ""
    prompt_text: str = ""
    duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_output(self, scene_number: int) -> Dict[str, Any]:
        payload = {
            "scene_number": scene_number,
            "video_url": self.video_url,
            "video_path": self.video_path,
            "prompt_text": self.prompt_text,
            "duration": self.duration,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


__all__ = ["SceneSnapshot", "SceneArtifact"]

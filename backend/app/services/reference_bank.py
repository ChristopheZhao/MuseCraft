"""Lightweight in-memory reference bank for scene-level visual anchors."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Optional


class _ReferenceBank:
    def __init__(self) -> None:
        # storage[(workflow_state_id or '__default__')][scene_number] = frame_url
        self._storage: Dict[str, Dict[int, str]] = defaultdict(dict)

    def store(self, workflow_state_id: Optional[str], scene_number: int, frame_url: str) -> None:
        if not isinstance(scene_number, int) or not frame_url:
            return
        bucket = self._storage[self._normalize_key(workflow_state_id)]
        bucket[scene_number] = frame_url

    def fetch(self, workflow_state_id: Optional[str], scene_number: int) -> Optional[str]:
        if not isinstance(scene_number, int):
            return None
        bucket = self._storage.get(self._normalize_key(workflow_state_id))
        if not bucket:
            return None
        return bucket.get(scene_number)

    @staticmethod
    def _normalize_key(workflow_state_id: Optional[str]) -> str:
        return str(workflow_state_id) if workflow_state_id else "__default__"


_BANK = _ReferenceBank()


def store_scene_reference(workflow_state_id: Optional[str], scene_number: int, frame_url: str) -> None:
    """Persist best-known reference frame for a scene."""

    _BANK.store(workflow_state_id, scene_number, frame_url)


def get_scene_reference(workflow_state_id: Optional[str], scene_number: int) -> Optional[str]:
    """Retrieve previously stored reference frame for a scene."""

    return _BANK.fetch(workflow_state_id, scene_number)

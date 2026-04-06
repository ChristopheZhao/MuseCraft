"""Episodic memory interface stubs for MAS/Agent trajectories.

占位目的：
- 明确短期 WorkingMemory 与长期 Episodic Memory 的分层；
- 提供统一的写入接口，便于后续挂接真实存储（DB/向量库）；
- 避免将轨迹/长程信息混入 WorkingMemory。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class EpisodeRecord:
    workflow_id: str
    agent: str
    iteration: int
    observation: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class EpisodicMemoryWriter:
    """Minimal writer stub; replace storage backend when available."""

    def __init__(self) -> None:
        self._sink = _NullEpisodeSink()

    async def write(self, record: EpisodeRecord) -> None:
        await self._sink.write(record)


class _NullEpisodeSink:
    """Fallback sink that simply logs/ignores records."""

    async def write(self, record: EpisodeRecord) -> None:
        try:
            import logging

            logging.getLogger("episodic_memory").debug(
                "EPISODE_STUB workflow=%s agent=%s iter=%s keys=%s",
                record.workflow_id,
                record.agent,
                record.iteration,
                list((record.metadata or {}).keys()),
            )
        except Exception:
            return


# Global singleton for ease of dependency until DI is wired
episodic_memory_writer = EpisodicMemoryWriter()

__all__ = ["EpisodeRecord", "EpisodicMemoryWriter", "episodic_memory_writer"]

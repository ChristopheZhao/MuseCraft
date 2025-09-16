"""
Audio Analysis Tool - 提供基础音频分析能力（时长、静音窗口、候选截断点等）
保持供应商无关，基于 ffmpeg/ffprobe 实现。
"""

import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError


class AudioAnalysisTool(AsyncTool):
    """
    音频分析工具：
    - analyze_track: 返回 duration、silence 窗口、候选截断点
    - suggest_edit_plan: 基于目标时长与分析结果，输出编辑计划（截断点/淡入淡出）
    """

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="audio_analysis_tool",
            version="1.0.0",
            description="Analyze audio track (duration, silence windows, candidate cut points).",
            tool_type=ToolType.MEDIA_PROCESSING,
            author="system",
            tags=["audio", "analysis", "ffmpeg"],
            capabilities=["duration", "silence_detect", "cut_point_suggestion"],
            limitations=["ffmpeg_required", "heuristic"]
        )

    def _initialize(self):
        # 验证 ffmpeg 可用性
        pass

    def get_available_actions(self) -> List[str]:
        return ["analyze_track", "suggest_edit_plan"]

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "analyze_track":
            return {
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "音频文件路径"},
                    "silence_noise": {"type": "string", "default": "-30dB"},
                    "silence_duration": {"type": "number", "default": 0.3},
                },
                "required": ["input_path"]
            }
        if action == "suggest_edit_plan":
            return {
                "type": "object",
                "properties": {
                    "target_duration": {"type": "number"},
                    "analysis": {"type": "object"},
                    "fade_out": {"type": "number", "default": 1.0}
                },
                "required": ["target_duration", "analysis"]
            }
        return {}

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        action = tool_input.action
        params = tool_input.parameters
        if action == "analyze_track":
            return await self._analyze_track(params)
        if action == "suggest_edit_plan":
            return await self._suggest_edit_plan(params)
        raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)

    async def _analyze_track(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = params.get("input_path")
        if not path or not os.path.exists(path):
            raise ToolError("input_path not found", self.metadata.name)
        noise = params.get("silence_noise", "-30dB")
        dur_min = float(params.get("silence_duration", 0.3))

        # Get duration via ffprobe
        duration = await self._ffprobe_duration(path)

        # silencedetect to find silence windows
        silences = await self._ffmpeg_silencedetect(path, noise, dur_min)

        # candidate cut points: silence_start close to the end
        candidates: List[float] = []
        if duration:
            for win in silences:
                s = win.get("silence_start")
                e = win.get("silence_end")
                if s is None:
                    continue
                # 倾向于选择临近末尾的开始点作为截断点
                if duration - float(s) <= 2.5:  # 末尾 2.5 秒内的静音更适合作为淡出起点
                    candidates.append(float(s))

        return {
            "success": True,
            "duration": duration,
            "silence_windows": silences,
            "candidate_cut_points": sorted(set(round(c, 3) for c in candidates))
        }

    async def _suggest_edit_plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        target = float(params.get("target_duration"))
        analysis = params.get("analysis") or {}
        fade_out = float(params.get("fade_out", 1.0))
        duration = float(analysis.get("duration") or 0)
        candidates = list(analysis.get("candidate_cut_points") or [])

        plan: Dict[str, Any] = {
            "method": "trim",
            "cut_at": target,
            "fade_out": fade_out,
        }
        if duration > target and candidates:
            # choose the closest candidate <= target, else default target
            le = [c for c in candidates if c <= target]
            if le:
                plan["cut_at"] = max(le)

        return {
            "success": True,
            "plan": plan
        }

    async def _ffprobe_duration(self, path: str) -> float:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            path
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await proc.communicate()
            if proc.returncode == 0:
                try:
                    return float(out.decode().strip())
                except Exception:
                    return 0.0
            return 0.0
        except Exception:
            return 0.0

    async def _ffmpeg_silencedetect(self, path: str, noise: str, dur_min: float) -> List[Dict[str, Any]]:
        cmd = [
            "ffmpeg", "-hide_banner", "-nostats",
            "-i", path,
            "-af", f"silencedetect=noise={noise}:d={dur_min}",
            "-f", "null", "-"
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await proc.communicate()
            text = (err.decode() if err else "")
            silences: List[Dict[str, Any]] = []
            s_start = None
            for line in text.splitlines():
                m1 = re.search(r"silence_start: ([0-9.]+)", line)
                if m1:
                    try:
                        s_start = float(m1.group(1))
                    except Exception:
                        s_start = None
                m2 = re.search(r"silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)", line)
                if m2:
                    try:
                        s_end = float(m2.group(1))
                        s_d = float(m2.group(2))
                        silences.append({"silence_start": s_start, "silence_end": s_end, "silence_duration": s_d})
                    except Exception:
                        pass
            return silences
        except Exception:
            return []


"""Shared still/reference normalization helpers for image prompt contracts."""

from __future__ import annotations

import re
from typing import Any, Dict, List


VIDEO_ONLY_MARKERS = (
    "快速切换",
    "混剪",
    "闪回",
    "闪现",
    "剪辑",
    "分镜",
    "转场",
    "标题",
    "上映日期",
    "字幕",
    "片名",
)

STILL_HINT_MARKERS = ("定格", "特写", "凝视", "站立", "静止", "肖像", "立绘")

HIGH_RISK_MARKERS = (
    "扑向",
    "突袭",
    "袭来",
    "战斗",
    "激战",
    "对决",
    "对抗",
    "迎击",
    "轰击",
    "爆炸",
    "炸裂",
    "崩碎",
    "吞噬",
    "巨口",
    "血",
    "杀",
)

APPEARANCE_MARKERS = (
    "长袍",
    "服饰",
    "发型",
    "黑发",
    "面部",
    "神情",
    "气质",
    "轮廓",
    "色调",
    "光影",
    "线条",
    "剑",
    "法器",
    "储物袋",
    "道具",
    "站姿",
    "站立",
    "符号",
    "纹样",
    "面庞",
)

STRONG_APPEARANCE_MARKERS = (
    "长袍",
    "服饰",
    "发型",
    "黑发",
    "神情",
    "轮廓",
    "色调",
    "光影",
    "线条",
    "剑",
    "法器",
    "储物袋",
    "道具",
    "纹样",
    "面庞",
)

REFERENCE_TASK_DIRECTIONS = {"avatar", "headshot", "portrait", "full_body", "full-body"}

PURPOSE_ALIASES = {
    "scene_opening_anchor": "scene_opening_anchor",
    "opening_anchor": "scene_opening_anchor",
    "opening_state": "scene_opening_anchor",
    "scene_still": "scene_opening_anchor",
    "still": "scene_opening_anchor",
    "character_reference": "character_reference",
    "character_ref": "character_reference",
    "reference": "character_reference",
}


def clip_text(value: Any, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if isinstance(v, (str, int, float)) and str(v).strip()]
    if isinstance(value, (str, int, float)) and str(value).strip():
        return [str(value).strip()]
    return []


def dedup(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in values:
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def canonicalize_image_purpose(value: Any, *, task_direction: str = "") -> str:
    normalized = str(value or "").strip().lower()
    if not normalized and task_direction in REFERENCE_TASK_DIRECTIONS:
        normalized = "character_reference"
    return PURPOSE_ALIASES.get(normalized, "scene_opening_anchor")


def contains_video_only_language(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return any(marker in text for marker in VIDEO_ONLY_MARKERS)


def contains_high_risk_action_language(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return any(marker in text for marker in HIGH_RISK_MARKERS)


def soften_still_language(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    replacements = {
        "张开巨口扑向镜头": "盘踞于前景阴影中",
        "巨口扑向镜头": "盘踞于前景阴影中",
        "巨口扑向": "逼近前景",
        "扑向镜头": "逼近前景",
        "巨蟒突袭": "巨蟒现身",
        "猛然袭来": "骤然现身",
        "战斗姿态": "临战姿态",
        "激战": "交锋",
        "战斗": "对峙",
        "对抗": "对峙",
        "对决": "对峙",
        "迎击": "应对",
        "爆炸": "能量迸发",
        "炸裂": "光芒迸发",
        "轰击": "冲击",
        "崩碎": "震裂",
        "吞噬": "笼罩",
        "腥风": "劲风",
        "敌对修仙者": "远处修仙者身影",
        "水墨风格闪现": "水墨风格呈现",
        "特写镜头": "特写",
        "镜头特写": "特写",
        "镜头定格": "定格",
    }
    softened = text
    for src, dst in replacements.items():
        softened = softened.replace(src, dst)
    return softened


def normalize_still_text(value: Any, *, max_len: int | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    clauses = [
        part.strip(" ，,；;。.!?！？")
        for part in re.split(r"[，,；;。.!?！？\n]+", text)
    ]
    kept = [clause for clause in clauses if clause and not contains_video_only_language(clause)]
    normalized = "，".join(kept) if kept else text
    normalized = soften_still_language(normalized).strip(" ，,；;。.!?！？")
    if max_len is not None:
        return clip_text(normalized, max_len)
    return normalized


def compress_character_description(
    value: Any,
    *,
    segment_max_len: int = 72,
    fallback_max_len: int = 100,
    output_max_len: int | None = None,
) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    name = ""
    body = raw
    if "：" in raw:
        maybe_name, rest = raw.split("：", 1)
        if maybe_name.strip() and len(maybe_name.strip()) <= 12:
            name = maybe_name.strip()
            body = rest.strip()

    cleaned_segments: List[str] = []
    for segment in re.split(r"[；;]+", body):
        seg = normalize_still_text(segment)
        if not seg:
            continue
        if seg.startswith("原型："):
            continue
        if contains_video_only_language(seg):
            continue
        has_appearance_signal = any(marker in seg for marker in APPEARANCE_MARKERS)
        if not has_appearance_signal and "，" in seg:
            continue
        if not has_appearance_signal and len(re.split(r"[，,]", seg)) >= 3:
            continue
        if not has_appearance_signal and seg.startswith("在") and len(seg) > 24:
            continue
        seg = (
            seg.replace("物种：", "")
            .replace("主角，", "")
            .replace("主角", "")
            .replace("成长型", "")
            .strip(" ，,；;。.!?！？")
        )
        if not seg:
            continue
        cleaned_segments.append(clip_text(seg, segment_max_len))

    if not cleaned_segments:
        fallback = clip_text(normalize_still_text(body), fallback_max_len)
        if not fallback or contains_video_only_language(fallback):
            return ""
        fallback_has_appearance_signal = any(marker in fallback for marker in STRONG_APPEARANCE_MARKERS)
        if not fallback_has_appearance_signal and ("，" in fallback or (fallback.startswith("在") and len(fallback) > 24)):
            return ""
        result = f"{name}：{fallback}" if name else fallback
        if output_max_len is not None:
            return clip_text(result, output_max_len)
        return result

    joined = "；".join(dedup(cleaned_segments[:4]))
    if output_max_len is not None:
        joined = clip_text(joined, output_max_len)
    return f"{name}：{joined}" if name else joined


def select_scene_opening_root(scene_data: Dict[str, Any], *, fallback_title: str = "单帧静态画面") -> str:
    action_phases = scene_data.get("action_phases") or []
    visual_desc = str(
        scene_data.get("visual_description")
        or scene_data.get("description")
        or scene_data.get("title")
        or ""
    ).strip()
    opening_state = str(scene_data.get("opening_state") or "").strip()
    content_focus = str(scene_data.get("content_focus") or "").strip()
    montage_like = any(
        contains_video_only_language(candidate)
        for candidate in [
            visual_desc,
            opening_state,
            scene_data.get("event_trigger"),
            scene_data.get("camera_language"),
            scene_data.get("camera_angle"),
            *(phase.get("observable_actions") for phase in action_phases if isinstance(phase, dict)),
        ]
    )

    if montage_like and isinstance(action_phases, list):
        for phase in reversed(action_phases):
            if not isinstance(phase, dict):
                continue
            for key in ("observable_actions", "visual_focus"):
                candidate = normalize_still_text(phase.get(key))
                raw = str(phase.get(key) or "").strip()
                if candidate and (candidate != raw or any(marker in raw for marker in STILL_HINT_MARKERS)):
                    return candidate

    projected_opening = normalize_still_text(opening_state)
    if opening_state and not contains_high_risk_action_language(opening_state):
        return projected_opening or opening_state

    end_state = normalize_still_text(scene_data.get("end_state"))
    if end_state:
        return end_state

    if isinstance(action_phases, list):
        for phase in action_phases:
            if not isinstance(phase, dict):
                continue
            actions = normalize_still_text(phase.get("observable_actions"))
            if actions:
                return actions

    motion_beats = scene_data.get("motion_beats") or []
    if isinstance(motion_beats, list):
        for beat in motion_beats:
            if not isinstance(beat, dict):
                continue
            focus = normalize_still_text(beat.get("visual_focus"))
            if focus:
                return focus

    if visual_desc:
        return normalize_still_text(visual_desc) or visual_desc
    if content_focus:
        return normalize_still_text(content_focus) or content_focus
    return str(fallback_title or "单帧静态画面").strip()

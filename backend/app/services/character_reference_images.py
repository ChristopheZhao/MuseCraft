"""Project character reference image generation (avatar/full-body).

This module is intentionally tool-first and provider-agnostic: it only relies on
the registered `image_generation` tool interface to produce reference images and
stores resulting URLs into `CharacterProfile.reference_assets`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..core.story_plan import CharacterProfile, ProjectState, project_state_repository
from ..agents.tools.tool_registry import get_tool_registry


def _flatten_keywords(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, dict):
        keywords = value.get("keywords")
        if isinstance(keywords, list):
            return [str(v).strip() for v in keywords if str(v).strip()]
        if isinstance(keywords, dict):
            return [str(k).strip() for k, v in keywords.items() if v]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(value).strip()]


def _has_reference(profile: CharacterProfile, kind: str) -> bool:
    assets = profile.reference_assets or {}
    direct = assets.get(kind)
    if isinstance(direct, dict) and str(direct.get("url") or "").strip():
        return True
    if isinstance(direct, str) and direct.strip():
        return True
    return False


def _build_prompt(profile: CharacterProfile, kind: str, style_profile: Dict[str, Any]) -> str:
    style_name = str(style_profile.get("style_name") or style_profile.get("style") or "").strip()
    style_description = str(style_profile.get("style_description") or "").strip()
    visual_approach = str(style_profile.get("visual_approach") or "").strip()

    identity_tags = []
    signature_props = []
    if isinstance(profile.visual_traits, dict):
        identity_tags = _flatten_keywords(profile.visual_traits.get("identity_tags"))
        signature_props = _flatten_keywords(profile.visual_traits.get("signature_props"))
    style_keywords = _flatten_keywords(profile.style_preferences or {})

    parts: List[str] = []
    if style_name:
        parts.append(f"风格：{style_name}")
    if style_description:
        parts.append(f"风格描述：{style_description}")
    if visual_approach:
        parts.append(f"表现形式：{visual_approach}")
    parts.append(f"角色：{profile.display_name}")
    if profile.narrative_role:
        parts.append(f"角色定位：{profile.narrative_role}")
    if profile.description:
        parts.append(f"角色描述：{profile.description}")
    if identity_tags:
        parts.append("外观特征：" + "、".join(identity_tags[:8]))
    if signature_props:
        parts.append("标志性道具/服饰：" + "、".join(signature_props[:8]))
    if profile.personality_traits:
        parts.append("性格关键词：" + "、".join([str(x).strip() for x in profile.personality_traits[:8] if str(x).strip()]))
    if style_keywords:
        parts.append("风格偏好：" + "、".join(style_keywords[:10]))

    if kind == "avatar":
        parts.append("画面要求：角色头像参考图，正面，居中构图，背景干净，风格统一，无文字无水印。")
    else:
        parts.append("画面要求：角色全身立绘参考图，正面站立，包含标志性服饰与道具，背景干净，风格统一，无文字无水印。")

    return "\n".join([p for p in parts if p])


async def ensure_project_character_reference_images(
    project_id: str,
    *,
    enabled: Optional[bool] = None,
    logger=None,
) -> bool:
    """Ensure avatar/full-body refs exist in `ProjectState.character_bible`.

    Returns True if the function ran (enabled + project exists), regardless of whether
    all images succeeded; returns False when disabled or project missing.
    """

    if enabled is None:
        enabled = bool(getattr(settings, "PROJECT_CHARACTER_REFERENCE_IMAGES_ENABLED", False))
    if not enabled:
        return False

    project_state = project_state_repository.get(project_id)
    if not project_state:
        return False

    if project_state.global_settings is None:
        project_state.global_settings = {}
    project_state.global_settings["character_references_status"] = "in_progress"
    project_state_repository.save(project_state)

    if not project_state.character_bible:
        project_state.global_settings["character_references_status"] = "completed"
        project_state_repository.save(project_state)
        return True

    avatar_size = getattr(settings, "PROJECT_CHARACTER_REFERENCE_AVATAR_SIZE", "1024x1024")
    full_body_size = getattr(settings, "PROJECT_CHARACTER_REFERENCE_FULL_BODY_SIZE", "1024x1792")
    style_profile = project_state.style_profile or {}

    registry = get_tool_registry()
    image_tool = registry.get_tool("image_generation")
    file_key_prefix = f"projects/{project_id}/characters"

    for canonical_id, profile in (project_state.character_bible or {}).items():
        if not isinstance(profile, CharacterProfile):
            continue

        if profile.reference_assets is None:
            profile.reference_assets = {}

        for kind, size in (("avatar", avatar_size), ("full_body", full_body_size)):
            if _has_reference(profile, kind):
                continue

            prompt = _build_prompt(profile, kind, style_profile)
            scene_number = f"character:{canonical_id}:{kind}"
            try:
                out = await image_tool.execute(
                    {
                        "action": "generate_image",
                        "parameters": {
                            "scene_number": scene_number,
                            "prompt": prompt,
                            "size": size,
                            "persist": True,
                            "destination_key": f"{file_key_prefix}/{canonical_id}/{kind}.jpg",
                        },
                    }
                )
                if not getattr(out, "success", False):
                    if logger is not None:
                        logger.warning(
                            "Character reference generation failed: project=%s cid=%s kind=%s err=%s",
                            project_id,
                            canonical_id,
                            kind,
                            getattr(out, "error", None),
                        )
                    continue
                payload = getattr(out, "result", None)
                if not isinstance(payload, dict):
                    continue
                url = str(payload.get("image_url") or "").strip()
                if not url:
                    continue
                profile.reference_assets[kind] = {
                    "kind": kind,
                    "url": url,
                    "size": size,
                    "generated_prompt": payload.get("generated_prompt") or prompt,
                }
                project_state_repository.save(project_state)
            except Exception as exc:  # noqa: BLE001
                if logger is not None:
                    logger.warning(
                        "Character reference generation exception: project=%s cid=%s kind=%s err=%s",
                        project_id,
                        canonical_id,
                        kind,
                        exc,
                    )

    try:
        project_state.story_plan.character_bible = project_state.character_bible
    except Exception:
        pass
    project_state.global_settings["character_references_status"] = "completed"
    project_state_repository.save(project_state)
    return True

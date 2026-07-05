"""ConsistencyTool - gather per-scene prompt assets and continuity hints."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple, TYPE_CHECKING

from .base_tool import BaseTool, ToolMetadata, ToolType, ToolInput, ToolValidationError
from ...core.scene_continuity_memory import get_scene_continuity_memory

if TYPE_CHECKING:
    from ..memory.short_term.service import WorkingMemoryService


class _WMMemoryProvider:
    """Default memory provider using scene_continuity_memory."""

    async def retrieve_scene_references(self, workflow_state_id: str, scene_number: int, agent_name: str) -> Dict[str, Any]:
        return {}

    async def retrieve_motion_guidance(self, workflow_state_id: str, scene_number: int, agent_name: str) -> Dict[str, Any]:
        return {}

    async def store_scene_final_frame(self, scene_number: int, frame_url: str) -> None:
        memory = get_scene_continuity_memory()
        await memory.store_scene_final_frame(scene_number, frame_url)

    async def retrieve_previous_frame_url(self, scene_number: int) -> Optional[str]:
        memory = get_scene_continuity_memory()
        return await memory.get_previous_scene_final_frame(scene_number)

    async def get_scene_continuity_info(self, workflow_state_id: str, scene_number: int) -> Dict[str, Any]:
        memory = get_scene_continuity_memory()
        return await memory.get_scene_continuity_info(scene_number)


class ConsistencyTool(BaseTool):
    """Collects style/character/environment/continuity assets for prompts."""

    def __init__(
        self,
        *,
        facts_provider: Optional[Any] = None,
        memory_provider: Optional[Any] = None,
        short_term_service: Optional["WorkingMemoryService"] = None,
        **kwargs: Any,
    ):
        self._short_term_service = short_term_service
        self._facts_provider = facts_provider
        self._memory_provider = memory_provider or _WMMemoryProvider()
        self._asset_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}
        super().__init__(
            metadata=ToolMetadata(
                name="consistency_tool",
                version="1.0",
                description="Collect prompt assets for consistency (style/characters/environment/continuity)",
                tool_type=ToolType.ANALYSIS,
            ),
            config=kwargs.get("config"),
            logger=kwargs.get("logger"),
        )

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="consistency_tool",
            version="1.0",
            description="Collect prompt assets for consistency (style/characters/environment/continuity)",
            tool_type=ToolType.ANALYSIS,
        )

    def _initialize(self):
        return

    def get_available_actions(self) -> List[str]:
        return ["get_prompt_assets", "register_reference"]

    def get_output_contract(self, action: str) -> Dict[str, Any]:
        if action == "get_prompt_assets":
            # Contract-first: declare how to write tool outputs into agent-scoped WM slots.
            # NOTE: This is *not* a final artifact/output; it is a prepared/cached input for planning.
            return {
                "scene_path": "scene_number",
                "memory_slots": {
                    "prepared_assets": {
                        "enabled": True,
                        "path": "assets",
                        "value_spec": {
                            "fields": {
                                "style": {
                                    "fields": {
                                        "global_lock": {
                                            "fields": {
                                                "style_guidelines": {"max_text": 160},
                                                "headline": {"max_text": 120},
                                                "style_tags": {"max_items": 8},
                                                "color_palette": {"max_items": 8},
                                                "object_guidelines": {"max_text": 160},
                                            },
                                        },
                                        "color_palette": {"max_items": 8},
                                        "mood": {"max_text": 120},
                                        "intelligent_style_design": {
                                            "fields": {
                                                "style_name": {"max_text": 120},
                                                "style_description": {"max_text": 240},
                                                "style_tags": {"max_items": 8},
                                                "color_palette": {"max_items": 8},
                                            },
                                        },
                                    },
                                },
                                "characters": {
                                    "fields": {
                                        "global_lock": {
                                            "fields": {
                                                "guidelines": {"max_text": 160},
                                                "stable_traits": {"max_items": 12},
                                            },
                                        },
                                        "scene_cast": {
                                            "fields": {
                                                "present": {"max_items": 8},
                                                "descriptions": {"max_items": 8},
                                            },
                                        },
                                        "identity_bible": {
                                            "fields": {
                                                "contract_version": {"max_text": 40},
                                                "source": {"max_text": 120},
                                                "characters": {"max_items": 8},
                                            },
                                        },
                                        "scene_locks": {"max_items": 8},
                                        "allowed_variants": {"max_items": 8},
                                        "diagnostics": {"max_items": 12},
                                        "characters": {
                                            "max_items": 8,
                                            "items": {
                                                "fields": {
                                                    "prompt_snippet": {"max_text": 240},
                                                    "description": {"max_text": 240},
                                                    "abstract_traits": {"max_items": 12},
                                                    "key_traits": {"max_items": 12},
                                                    "traits": {"max_items": 12},
                                                    "aliases": {"max_items": 8},
                                                },
                                            },
                                        }
                                    },
                                },
                                "environment": {
                                    "fields": {
                                        "global_lock": {
                                            "fields": {
                                                "guidelines": {"max_text": 160},
                                            },
                                        },
                                        "opening_anchor": {
                                            "fields": {
                                                "opening_state": {"max_text": 240},
                                                "visual_description": {"max_text": 240},
                                                "mood_and_atmosphere": {"max_text": 160},
                                                "camera_angle": {"max_text": 120},
                                                "reference_image": {"max_text": 240},
                                            },
                                        },
                                        "visual_description": {"max_text": 400},
                                        "narrative_description": {"max_text": 240},
                                    },
                                },
                                "continuity": {
                                    "fields": {
                                        "local_continuity": {
                                            "fields": {
                                                "enabled": {},
                                                "depends_on_scene": {},
                                                "previous_frame_available": {},
                                                "previous_frame_url": {"max_text": 240},
                                                "transition_notes": {"max_text": 200},
                                            },
                                        },
                                        "motion_guidance": {
                                            "max_text": 400,
                                            "fields": {
                                                "has_guidance": {},
                                                "guidance": {"max_text": 400},
                                                "text": {"max_text": 400},
                                                "motion_guidance": {"max_text": 400},
                                            },
                                            "default_field_spec": {"max_text": 400},
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "prepared_assets_diagnostics": {
                        "enabled": True,
                        "path": "diagnostics",
                        "allow_null_scene": True,
                        "value_spec": {"max_dict_items": 20, "default_field_spec": {"max_text": 200}},
                    },
                },
            }
        return {}

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "get_prompt_assets":
            return {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer", "description": "目标场景编号"},
                    "scene_info_ref": {"type": "string", "description": "场景信息引用"},
                    "use_cache": {"type": "boolean", "description": "是否使用缓存"},
                },
                "required": ["scene_number", "scene_info_ref"],
            }
        if action == "register_reference":
            return {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer", "description": "目标场景编号"},
                    "reference_type": {"type": "string", "description": "引用类型"},
                    "reference_value": {"type": "string", "description": "引用内容"},
                },
                "required": ["scene_number", "reference_type", "reference_value"],
            }
        return {}

    def get_fc_visibility(self) -> Dict[str, Any]:
        return {"expose": True, "allowed_actions": self.get_available_actions()}

    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        if action == "get_prompt_assets":
            if parameters.get("scene_number") is None:
                raise ToolValidationError("scene_number is required", self.metadata.name)
            if not isinstance(parameters.get("scene_info_ref"), str) or not parameters.get("scene_info_ref"):
                raise ToolValidationError("scene_info_ref is required", self.metadata.name)
        if action == "register_reference":
            if parameters.get("scene_number") is None:
                raise ToolValidationError("scene_number is required", self.metadata.name)
            if not parameters.get("reference_type") or not parameters.get("reference_value"):
                raise ToolValidationError("reference_type/reference_value is required", self.metadata.name)

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        action = tool_input.action
        params = tool_input.parameters or {}
        context = tool_input.context or {}
        wf_id = str(context.get("workflow_state_id") or params.get("workflow_state_id") or "")

        if action == "get_prompt_assets":
            scene_number = int(params.get("scene_number") or 0)
            scene_info_ref = params.get("scene_info_ref") or ""
            # Default to cache-on for idempotent prompt-asset collection
            # Read path only: prompt asset collection must not mutate continuity state.
            use_cache = True if "use_cache" not in params else bool(params.get("use_cache"))
            payload, diagnostics = await self._collect_assets(
                wf_id,
                scene_info_ref,
                scene_number,
                use_cache=use_cache,
            )
            return {
                "workflow_state_id": wf_id,
                "scene_number": scene_number,
                "assets": payload,
                "diagnostics": diagnostics,
            }

        if action == "register_reference":
            scene_number = int(params.get("scene_number") or 0)
            ref_value = params.get("reference_value") or ""
            # Explicit write path only: register the final-frame reference for later
            # continuity use without taking runtime/planning ownership.
            await self._memory_provider.store_scene_final_frame(scene_number, ref_value)
            for key in list(self._asset_cache.keys()):
                if isinstance(key, tuple) and len(key) == 2 and key[1] == scene_number:
                    self._asset_cache.pop(key, None)
            return {"stored": True, "scene_number": scene_number}

        raise ValueError(f"Unsupported action: {action}")

    async def _collect_assets(
        self,
        workflow_state_id: str,
        scene_info_ref: str,
        scene_number: int,
        *,
        use_cache: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        cache_scope = workflow_state_id or scene_info_ref
        cache_key = (cache_scope, scene_number)
        diagnostics: Dict[str, Any] = {
            "cached_full": False,
            "cached_categories": [],
            "source": "scene_info_ref",
            "scene_info_ref": scene_info_ref,
        }
        if use_cache and cache_key in self._asset_cache:
            diagnostics["cached_full"] = True
            diagnostics["cached_categories"] = list(self._asset_cache[cache_key].keys())
            return self._asset_cache[cache_key], diagnostics

        scene_info = self._load_scene_info(scene_info_ref)
        scene_entry = self._extract_scene_entry(scene_info, scene_number) or {}
        previous_frame_url = await self._memory_provider.retrieve_previous_frame_url(scene_number)
        continuity_info = await self._memory_provider.get_scene_continuity_info(
            workflow_state_id,
            scene_number,
        )

        assets: Dict[str, Any] = {}
        assets["style"] = self._extract_style_assets(scene_info)
        assets["characters"] = self._extract_character_assets(scene_info, scene_entry)
        assets["environment"] = self._extract_environment_assets(scene_info, scene_entry, scene_number)
        assets["continuity"] = self._extract_continuity_assets(
            scene_entry,
            continuity_info=continuity_info,
            previous_frame_url=previous_frame_url,
        )

        self._asset_cache[cache_key] = assets
        diagnostics["cached_categories"] = list(assets.keys())
        character_assets = assets.get("characters") if isinstance(assets.get("characters"), dict) else {}
        if character_assets.get("source"):
            diagnostics["character_identity_contract_source"] = character_assets.get("source")
        if character_assets.get("structured_identity_missing") is not None:
            diagnostics["structured_identity_missing"] = bool(
                character_assets.get("structured_identity_missing")
            )
        return assets, diagnostics

    def _load_scene_info(self, ref: str) -> Dict[str, Any]:
        if not isinstance(ref, str) or not ref.strip():
            raise ToolValidationError("scene_info_ref is empty", self.metadata.name)
        path = ref.strip()
        if path.startswith("file://"):
            path = path[len("file://"):]
        candidate_paths: List[Path] = []
        try:
            candidate = Path(path)
        except Exception as exc:
            raise ToolValidationError(f"scene_info_ref parse failed: {exc}", self.metadata.name) from exc
        if candidate is not None:
            if candidate.is_absolute():
                candidate_paths.append(candidate)
            else:
                candidate_paths.append(candidate)
                try:
                    backend_root = Path(__file__).resolve().parents[3]
                    candidate_paths.append(backend_root / candidate)
                except Exception:
                    pass
        resolved_path = None
        for cand in candidate_paths:
            try:
                if cand and cand.exists():
                    resolved_path = cand
                    break
            except Exception:
                continue
        if resolved_path is None:
            raise ToolValidationError(f"scene_info_ref not found: {path}", self.metadata.name)
        try:
            payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ToolValidationError(f"scene_info_ref load failed: {exc}", self.metadata.name) from exc
        if not isinstance(payload, dict):
            raise ToolValidationError("scene_info_ref must be a JSON object", self.metadata.name)
        return payload

    def _extract_scene_entry(self, scene_info: Dict[str, Any], scene_number: int) -> Optional[Dict[str, Any]]:
        sn = self._coerce_int(scene_number)
        if sn is None:
            return None
        for source in (
            scene_info.get("scenes_to_generate") or [],
            (scene_info.get("scene_overview") or {}).get("scenes") or [],
            (scene_info.get("concept_plan") or {}).get("scenes") or [],
        ):
            if not isinstance(source, list):
                continue
            for scene in source:
                if not isinstance(scene, dict):
                    continue
                if self._coerce_int(scene.get("scene_number")) == sn:
                    return scene
        return None

    def _extract_style_assets(self, scene_info: Dict[str, Any]) -> Dict[str, Any]:
        style_assets: Dict[str, Any] = {}
        concept_plan = scene_info.get("concept_plan") or {}
        design = {}
        guidelines = {}
        if isinstance(concept_plan, dict):
            if concept_plan.get("consistency_guidelines"):
                guidelines = concept_plan.get("consistency_guidelines") or {}
                style_assets["consistency_guidelines"] = guidelines
            if concept_plan.get("intelligent_style_design"):
                design = concept_plan.get("intelligent_style_design") or {}
                style_assets["intelligent_style_design"] = design
        if scene_info.get("intelligent_style"):
            style_assets["intelligent_style"] = scene_info.get("intelligent_style") or {}
        if scene_info.get("intelligent_style_design") and "intelligent_style_design" not in style_assets:
            design = scene_info.get("intelligent_style_design") or {}
            style_assets["intelligent_style_design"] = design
        style_assets["global_lock"] = {
            "style_guidelines": str((guidelines or {}).get("style_consistency") or "").strip(),
            "headline": str((design or {}).get("headline") or (design or {}).get("summary") or (design or {}).get("style_name") or "").strip(),
            "style_tags": list((design or {}).get("style_tags") or (design or {}).get("tags") or []),
            "color_palette": list((design or {}).get("color_palette") or []),
            "object_guidelines": str((guidelines or {}).get("object_consistency") or "").strip(),
        }
        return style_assets

    def _extract_character_assets(self, scene_info: Dict[str, Any], scene_entry: Dict[str, Any]) -> Dict[str, Any]:
        structured_assets = self._extract_structured_character_assets(scene_info, scene_entry)
        if structured_assets is not None:
            return structured_assets

        concept_plan = scene_info.get("concept_plan") or {}
        characters: List[Dict[str, Any]] = []
        if isinstance(concept_plan, dict):
            for role in concept_plan.get("roles") or []:
                if isinstance(role, dict):
                    characters.append(role)
        present = scene_entry.get("characters_present") or []
        descriptions = scene_entry.get("character_descriptions") or []
        guidelines = ""
        if isinstance(concept_plan, dict):
            guidelines = (concept_plan.get("consistency_guidelines") or {}).get("character_consistency", "")
        stable_traits: List[str] = []
        for role in characters:
            if not isinstance(role, dict):
                continue
            for key in ("abstract_traits", "key_traits", "traits"):
                values = role.get(key)
                if isinstance(values, list):
                    stable_traits.extend(str(item).strip() for item in values if str(item).strip())
        return {
            "characters": characters,
            "present": present,
            "descriptions": descriptions,
            "guidelines": guidelines,
            "source": "legacy_roles" if characters else "legacy_text",
            "structured_identity_missing": True,
            "diagnostics": [
                {
                    "code": "structured_identity_missing",
                    "source": "character_identity_bible",
                    "fallback_reason": "using_legacy_roles_or_scene_text",
                }
            ],
            "global_lock": {
                "guidelines": str(guidelines or "").strip(),
                "stable_traits": list(dict.fromkeys(stable_traits))[:12],
            },
            "scene_cast": {
                "present": list(present) if isinstance(present, list) else [],
                "descriptions": list(descriptions) if isinstance(descriptions, list) else [],
            },
        }

    def _extract_structured_character_assets(
        self,
        scene_info: Dict[str, Any],
        scene_entry: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        bible = scene_info.get("character_identity_bible")
        if not isinstance(bible, dict):
            return None
        characters = bible.get("characters")
        if not isinstance(characters, list) or not characters:
            return None

        scene_number = self._coerce_int(scene_entry.get("scene_number") if isinstance(scene_entry, dict) else None)
        scene_lock = None
        locks = scene_info.get("scene_character_locks")
        if isinstance(locks, list):
            for lock in locks:
                if not isinstance(lock, dict):
                    continue
                if scene_number is not None and self._coerce_int(lock.get("scene_number")) == scene_number:
                    scene_lock = lock
                    break

        by_id = {
            str(item.get("canonical_id") or "").strip(): item
            for item in characters
            if isinstance(item, dict) and str(item.get("canonical_id") or "").strip()
        }
        lock_cast = scene_lock.get("cast") if isinstance(scene_lock, dict) else []
        if not isinstance(lock_cast, list):
            lock_cast = []

        present: List[str] = []
        descriptions: List[str] = []
        stable_traits: List[str] = []
        allowed_variants: List[Dict[str, Any]] = []
        scene_locks: List[Dict[str, Any]] = []

        if lock_cast:
            for cast_item in lock_cast:
                if not isinstance(cast_item, dict):
                    continue
                canonical_id = str(cast_item.get("canonical_id") or "").strip()
                character = by_id.get(canonical_id, {})
                display_name = str(
                    cast_item.get("display_name")
                    or character.get("display_name")
                    or canonical_id
                ).strip()
                if display_name:
                    present.append(display_name)
                stable_traits.extend(
                    str(item).strip()
                    for item in (cast_item.get("required_anchors") or [])
                    if str(item).strip()
                )
                descriptions.extend(
                    str(item).strip()
                    for item in (cast_item.get("scene_specific_state") or [])
                    if str(item).strip()
                )
                scene_locks.append(cast_item)
        else:
            for character in characters:
                if not isinstance(character, dict):
                    continue
                display_name = str(character.get("display_name") or character.get("canonical_id") or "").strip()
                if display_name:
                    present.append(display_name)
                stable = character.get("stable_anchors") if isinstance(character.get("stable_anchors"), dict) else {}
                for key in ("visual_identity", "signature_outfit_or_props", "identity_tags"):
                    stable_traits.extend(
                        str(item).strip()
                        for item in (stable.get(key) or [])
                        if str(item).strip()
                    )

        for character in characters:
            if not isinstance(character, dict):
                continue
            canonical_id = str(character.get("canonical_id") or "").strip()
            variants = character.get("allowed_variants")
            if canonical_id and isinstance(variants, list):
                allowed_variants.append({"canonical_id": canonical_id, "variants": variants})

        diagnostics = []
        diagnostics.extend(bible.get("diagnostics") if isinstance(bible.get("diagnostics"), list) else [])
        if isinstance(scene_lock, dict):
            diagnostics.extend(scene_lock.get("diagnostics") if isinstance(scene_lock.get("diagnostics"), list) else [])
        if not scene_lock:
            diagnostics.append(
                {
                    "code": "scene_character_lock_missing",
                    "scene_number": scene_number,
                    "fallback_reason": "using_identity_bible_without_scene_lock",
                }
            )

        concept_plan = scene_info.get("concept_plan") or {}
        guidelines = ""
        if isinstance(concept_plan, dict):
            guidelines = (concept_plan.get("consistency_guidelines") or {}).get("character_consistency", "")

        return {
            "characters": [item for item in characters if isinstance(item, dict)],
            "identity_bible": {
                "contract_version": bible.get("contract_version"),
                "source": bible.get("source"),
                "characters": [item for item in characters if isinstance(item, dict)],
            },
            "scene_locks": scene_locks,
            "allowed_variants": allowed_variants,
            "present": list(dict.fromkeys(present)),
            "descriptions": list(dict.fromkeys(descriptions)),
            "guidelines": guidelines,
            "source": "character_identity_contract",
            "structured_identity_missing": False,
            "diagnostics": diagnostics,
            "global_lock": {
                "guidelines": str(guidelines or "").strip(),
                "stable_traits": list(dict.fromkeys(stable_traits))[:12],
            },
            "scene_cast": {
                "present": list(dict.fromkeys(present)),
                "descriptions": list(dict.fromkeys(descriptions))[:8],
            },
        }

    def _extract_environment_assets(
        self,
        scene_info: Dict[str, Any],
        scene_entry: Dict[str, Any],
        scene_number: int,
    ) -> Dict[str, Any]:
        env: Dict[str, Any] = {
            "scene_number": scene_number,
            "visual_description": "",
            "narrative_description": "",
            "guidelines": "",
            "global_lock": {
                "guidelines": "",
            },
            "opening_anchor": {
                "opening_state": "",
                "visual_description": "",
                "mood_and_atmosphere": "",
                "camera_angle": "",
                "reference_image": "",
            },
        }
        if isinstance(scene_entry, dict) and scene_entry:
            env.update(
                {
                    "visual_description": scene_entry.get("visual_description", ""),
                    "narrative_description": scene_entry.get("narrative_description", ""),
                }
            )
            env["opening_anchor"] = {
                "opening_state": scene_entry.get("opening_state") or scene_entry.get("visual_description") or "",
                "visual_description": scene_entry.get("visual_description", ""),
                "mood_and_atmosphere": scene_entry.get("mood_and_atmosphere", ""),
                "camera_angle": scene_entry.get("camera_angle") or scene_entry.get("camera_language") or "",
                "reference_image": scene_entry.get("image_url") or "",
            }
        concept_plan = scene_info.get("concept_plan") or {}
        if isinstance(concept_plan, dict):
            guidelines = (concept_plan.get("consistency_guidelines") or {}).get("environment_consistency", "")
            if isinstance(guidelines, str) and guidelines.strip():
                env["guidelines"] = guidelines.strip()
                env["global_lock"]["guidelines"] = guidelines.strip()
        return env

    def _extract_continuity_assets(
        self,
        scene_entry: Dict[str, Any],
        *,
        continuity_info: Optional[Dict[str, Any]] = None,
        previous_frame_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        depends_on = None
        if isinstance(scene_entry, dict):
            depends_on = scene_entry.get("depends_on_scene") or scene_entry.get("depends_on")
        try:
            depends_on = int(depends_on) if depends_on is not None else None
        except Exception:
            depends_on = None
        continuity_info = continuity_info or {}
        previous_frame_url = previous_frame_url or continuity_info.get("previous_frame_path") or continuity_info.get("previous_frame_url")
        transition_notes = (
            scene_entry.get("continuity_reason")
            or continuity_info.get("transition_notes")
            or continuity_info.get("reason")
            or ""
        )
        enabled = bool(
            continuity_info.get("requires_continuity")
            or depends_on is not None
            or previous_frame_url
        )
        return {
            "depends_on_scene": depends_on,
            "local_continuity": {
                "enabled": enabled,
                "depends_on_scene": depends_on,
                "previous_frame_available": bool(previous_frame_url),
                "previous_frame_url": str(previous_frame_url or "").strip(),
                "transition_notes": str(transition_notes or "").strip(),
            },
            "motion_guidance": continuity_info.get("motion_guidance") or {},
        }

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

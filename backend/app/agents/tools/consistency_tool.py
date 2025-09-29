"""Consistency Toolkit - Provides scene/style/character continuity assets.

This tool aggregates consistency-related context from `WorkflowState`,
concept plans, and scene continuity memory so that downstream agents can
request ready-to-use prompt assets without hardcoding provider details.

It also allows agents to register references (e.g., extracted frames) back
to the shared continuity cache in a supplier-agnostic fashion.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base_tool import (
    AsyncTool,
    ToolMetadata,
    ToolType,
    ToolValidationError,
)
from ...core.workflow_state import workflow_manager, SceneData
from ...core.scene_continuity_memory import get_scene_continuity_memory


class ConsistencyTool(AsyncTool):
    """Tool exposing consistency-aware prompt assets and reference caching."""

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="consistency_tool",
            version="1.0.0",
            description=(
                "Aggregate style/character continuity assets and register references "
                "for multi-scene workflows"
            ),
            tool_type=ToolType.ANALYSIS,
            author="system",
            tags=["consistency", "style", "character", "workflow"],
            dependencies=[],
            capabilities=["prompt_asset_lookup", "continuity_reference_cache"],
        )

    def __init__(self, **kwargs):
        kwargs.pop("metadata", None)
        metadata = self.get_metadata()
        super().__init__(metadata=metadata, **kwargs)
        self._asset_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._reference_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._continuity_memory = get_scene_continuity_memory()

    def _initialize(self) -> None:  # pragma: no cover - nothing to initialize yet
        """Initialize tool resources (none required)."""
        return

    def get_available_actions(self) -> List[str]:
        return [
            "get_prompt_assets",
            "register_reference",
            "get_reference_snapshot",
        ]

    def get_fc_visibility(self) -> Dict[str, Any]:
        # Expose read action by default; write action can be opened via policy when needed.
        return {
            "expose": True,
            "allowed_actions": ["get_prompt_assets"],
        }

    def get_action_stage(self, action: str) -> str:
        if action == "get_prompt_assets":
            return "plan"
        return "act"

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        base_schema: Dict[str, Any] = {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }

        if action == "get_prompt_assets":
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "Target scene number",
                },
                "workflow_state_id": {
                    "type": "string",
                    "description": "WorkflowState identifier (falls back to context if omitted)",
                },
                "asset_categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional whitelist of asset categories to return",
                },
                "use_cache": {
                    "type": "boolean",
                    "description": "Allow cached result (default true)",
                },
            }
            base_schema["required"] = ["scene_number"]
            base_schema["x-examples"] = [
                {
                    "scene_number": 3,
                    "asset_categories": ["style", "characters", "continuity"],
                }
            ]
        elif action == "register_reference":
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "Scene to associate with the reference",
                },
                "workflow_state_id": {
                    "type": "string",
                    "description": "WorkflowState identifier (optional)",
                },
                "reference_type": {
                    "type": "string",
                    "description": "Reference category, e.g. final_frame | palette | embedding",
                },
                "reference_value": {
                    "type": ["string", "object"],
                    "description": "Reference payload (URL/path/structured data)",
                },
                "metadata": {
                    "type": "object",
                    "description": "Auxiliary metadata for diagnostics",
                },
                "persist_continuity": {
                    "type": "boolean",
                    "description": "Store in continuity memory when applicable (default true)",
                },
            }
            base_schema["required"] = ["scene_number", "reference_type", "reference_value"]
            base_schema["x-examples"] = [
                {
                    "scene_number": 2,
                    "reference_type": "final_frame",
                    "reference_value": "https://storage/scene_2_tailframe.jpg",
                }
            ]
        elif action == "get_reference_snapshot":
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "Optional scene filter",
                },
                "workflow_state_id": {
                    "type": "string",
                    "description": "WorkflowState identifier (optional)",
                },
            }
        return base_schema

    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        if action in {"get_prompt_assets", "register_reference"}:
            if "scene_number" not in parameters:
                raise ToolValidationError(
                    "scene_number is required",
                    tool_name=self.metadata.name,
                )

        if action == "register_reference":
            if not parameters.get("reference_type"):
                raise ToolValidationError(
                    "reference_type is required",
                    tool_name=self.metadata.name,
                )
            if "reference_value" not in parameters:
                raise ToolValidationError(
                    "reference_value is required",
                    tool_name=self.metadata.name,
                )

    async def _execute_impl(self, tool_input):
        action = tool_input.action
        params = tool_input.parameters or {}
        context = tool_input.context or {}

        if action == "get_prompt_assets":
            return await self._handle_get_prompt_assets(params, context)
        if action == "register_reference":
            return await self._handle_register_reference(params, context)
        if action == "get_reference_snapshot":
            return self._handle_get_reference_snapshot(params, context)
        raise ToolValidationError(
            f"Unsupported action '{action}'",
            tool_name=self.metadata.name,
        )

    async def _handle_get_prompt_assets(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        scene_number = self._normalize_scene_number(params.get("scene_number"))
        requested_categories = self._normalize_categories(params.get("asset_categories"))
        use_cache = bool(params.get("use_cache", True))
        workflow_state_id = self._resolve_workflow_state_id(params, context)

        can_cache = bool(workflow_state_id)
        cache_key: Optional[Tuple[str, int]] = (
            (workflow_state_id, scene_number) if can_cache else None
        )

        if use_cache and cache_key and cache_key in self._asset_cache:
            cached = self._asset_cache[cache_key]
            await self._ensure_cache_coverage(
                cache_key,
                cached,
                workflow_state_id,
                scene_number,
                requested_categories,
            )
            return self._filter_categories(cached, requested_categories)

        assets, diagnostics = await self._build_assets(
            workflow_state_id,
            scene_number,
            requested_categories,
        )
        diagnostics["cached_categories"] = list(assets.keys())
        diagnostics["cached_full"] = requested_categories is None
        diagnostics["cache_enabled"] = can_cache
        result = {
            "scene_number": scene_number,
            "workflow_state_id": workflow_state_id,
            "assets": assets,
            "diagnostics": diagnostics,
        }
        if cache_key:
            self._asset_cache[cache_key] = result
        return self._filter_categories(result, requested_categories)

    async def _handle_register_reference(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        scene_number = self._normalize_scene_number(params.get("scene_number"))
        workflow_state_id = self._resolve_workflow_state_id(params, context)
        reference_type = str(params.get("reference_type") or "").strip()
        reference_value = params.get("reference_value")
        metadata = params.get("metadata") or {}
        persist = params.get("persist_continuity", True)

        can_cache = bool(workflow_state_id)
        cache_key: Optional[Tuple[str, int]] = (
            (workflow_state_id, scene_number) if can_cache else None
        )

        if cache_key:
            bucket = self._reference_cache.setdefault(cache_key, {})
            bucket[reference_type] = {
                "value": reference_value,
                "metadata": metadata,
            }

        if persist and reference_type in {"final_frame", "continuity_frame"}:
            await self._persist_continuity_reference(scene_number, reference_value)

        # 一致性引用更新后，移除相关缓存，确保后续查询获取最新数据
        if cache_key:
            self._asset_cache.pop(cache_key, None)

        return {
            "scene_number": scene_number,
            "workflow_state_id": workflow_state_id,
            "reference_type": reference_type,
            "stored": True,
        }

    def _handle_get_reference_snapshot(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        workflow_state_id = self._resolve_workflow_state_id(params, context)
        scene_number = params.get("scene_number")
        scene_key = None
        if scene_number is not None and workflow_state_id:
            scene_key = (workflow_state_id, self._normalize_scene_number(scene_number))

        if scene_key:
            return {
                "scene_number": scene_key[1],
                "workflow_state_id": workflow_state_id,
                "references": self._reference_cache.get(scene_key, {}),
            }

        # Return a lightweight snapshot of all cached references.
        payload = {
            "workflow_state_id": workflow_state_id,
            "entries": [
                {
                    "scene_number": key[1],
                    "references": value,
                }
                for key, value in self._reference_cache.items()
                if workflow_state_id is None or key[0] == workflow_state_id
            ],
        }
        return payload

    async def _build_assets(
        self,
        workflow_state_id: Optional[str],
        scene_number: int,
        asset_categories: Optional[List[str]],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        workflow_state = workflow_manager.get_workflow(workflow_state_id) if workflow_state_id else None
        scene = self._resolve_scene(workflow_state, scene_number)

        diagnostics: Dict[str, Any] = {
            "workflow_state_found": workflow_state is not None,
            "scene_found": scene is not None,
        }

        assets: Dict[str, Any] = {}

        if self._include_category(asset_categories, "style"):
            assets["style"] = self._collect_style_assets(workflow_state, scene)

        if self._include_category(asset_categories, "characters"):
            assets["characters"] = self._collect_character_assets(workflow_state, scene)

        if self._include_category(asset_categories, "environment"):
            assets["environment"] = self._collect_environment_assets(workflow_state, scene)

        if self._include_category(asset_categories, "continuity"):
            assets["continuity"] = await self._collect_continuity_assets(scene_number)

        diagnostics["categories"] = list(assets.keys())
        return assets, diagnostics

    def _collect_style_assets(
        self,
        workflow_state,
        scene: Optional[SceneData],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        if workflow_state:
            style_design = getattr(workflow_state, "intelligent_style_design", None)
            if isinstance(style_design, dict):
                result["intelligent_style_design"] = {
                    key: value
                    for key, value in style_design.items()
                    if isinstance(value, (str, list, dict)) and value
                }

            consistency_hints = getattr(workflow_state, "consistency_hints", None)
            if isinstance(consistency_hints, dict) and consistency_hints:
                result["consistency_hints"] = consistency_hints

            concept_plan = getattr(workflow_state, "concept_plan", None)
            if isinstance(concept_plan, dict):
                guidelines = concept_plan.get("consistency_guidelines")
                if isinstance(guidelines, dict) and guidelines:
                    result["consistency_guidelines"] = guidelines

        if scene:
            palette = getattr(scene, "color_palette", None)
            if palette:
                result["color_palette"] = list(palette)
            art_style = getattr(scene, "art_style", None)
            if art_style:
                result.setdefault("scene_modifiers", {})["art_style"] = art_style
            lighting = getattr(scene, "lighting_style", None)
            if lighting:
                result.setdefault("scene_modifiers", {})["lighting"] = lighting

        return result

    def _collect_character_assets(
        self,
        workflow_state,
        scene: Optional[SceneData],
    ) -> Dict[str, Any]:
        characters: List[Dict[str, Any]] = []
        character_notes: List[str] = []

        scene_names = []
        scene_descriptions = []
        if scene:
            scene_names = [
                str(name).strip()
                for name in getattr(scene, "characters_present", []) or []
                if str(name).strip()
            ]
            scene_descriptions = [
                str(desc).strip()
                for desc in getattr(scene, "character_descriptions", []) or []
                if str(desc).strip()
            ]

        concept_plan = getattr(workflow_state, "concept_plan", None) if workflow_state else None
        role_manifest = []
        if isinstance(concept_plan, dict):
            role_manifest = concept_plan.get("roles") or concept_plan.get("role_manifest") or []

        # Helper to normalize definition lookups
        def match_role(name: str) -> Optional[Dict[str, Any]]:
            normalized = name.lower()
            for candidate in role_manifest:
                if not isinstance(candidate, dict):
                    continue
                aliases = candidate.get("aliases") or []
                names_to_check = [candidate.get("name"), candidate.get("display_name")] + aliases
                for item in names_to_check:
                    if isinstance(item, str) and item.lower() == normalized:
                        return candidate
            return None

        for name in scene_names:
            role_entry = match_role(name)
            entry: Dict[str, Any] = {"name": name}

            if role_entry:
                for key in [
                    "display_name",
                    "archetype_or_identity",
                    "signature_outfit_or_props",
                    "key_traits",
                    "species_or_breed",
                ]:
                    value = role_entry.get(key)
                    if value:
                        entry[key] = value
                prompt_snippet = role_entry.get("prompt_snippet")
                if prompt_snippet:
                    character_notes.append(str(prompt_snippet))

            if scene_descriptions:
                entry.setdefault("descriptions", list(scene_descriptions))

            characters.append(entry)

        if not characters and scene_descriptions:
            characters.append({"name": "scene_characters", "descriptions": list(scene_descriptions)})

        result: Dict[str, Any] = {"characters": characters}

        if concept_plan:
            guidelines = concept_plan.get("consistency_guidelines")
            if isinstance(guidelines, dict):
                char_guideline = guidelines.get("character_consistency")
                if isinstance(char_guideline, str) and char_guideline.strip():
                    character_notes.append(char_guideline.strip())

        if character_notes:
            result["guidance"] = character_notes

        return result

    def _collect_environment_assets(
        self,
        workflow_state,
        scene: Optional[SceneData],
    ) -> Dict[str, Any]:
        environment: Dict[str, Any] = {}

        if scene:
            environment["title"] = getattr(scene, "title", "")
            environment["visual_description"] = getattr(scene, "visual_description", "")
            environment["narrative_description"] = getattr(scene, "narrative_description", "")
            environment["props"] = list(getattr(scene, "props_and_objects", []) or [])

        concept_plan = getattr(workflow_state, "concept_plan", None) if workflow_state else None
        if isinstance(concept_plan, dict):
            guidelines = concept_plan.get("consistency_guidelines")
            if isinstance(guidelines, dict):
                env_guideline = guidelines.get("environment_consistency")
                if env_guideline:
                    environment["guidance"] = env_guideline

        return environment

    async def _collect_continuity_assets(self, scene_number: int) -> Dict[str, Any]:
        info = await self._continuity_memory.get_scene_continuity_info(scene_number)
        return info or {}

    async def _persist_continuity_reference(self, scene_number: int, reference_value: Any) -> None:
        if reference_value is None:
            return
        try:
            if isinstance(reference_value, str):
                await self._continuity_memory.store_scene_final_frame(scene_number, reference_value)
        except Exception as exc:  # pragma: no cover - guardrail
            self.logger.warning(
                "Failed to persist continuity reference for scene %s: %s",
                scene_number,
                exc,
            )

    def _resolve_workflow_state_id(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Optional[str]:
        candidate = params.get("workflow_state_id") or context.get("workflow_state_id")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        return None

    def _normalize_scene_number(self, value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return int(value.strip())
            except ValueError as exc:
                raise ToolValidationError(
                    f"Invalid scene_number: {value}",
                    tool_name=self.metadata.name,
                ) from exc
        raise ToolValidationError(
            "scene_number must be int or numeric string",
            tool_name=self.metadata.name,
        )

    def _resolve_scene(
        self,
        workflow_state,
        scene_number: int,
    ) -> Optional[SceneData]:
        if workflow_state is None:
            return None
        try:
            return workflow_state.get_scene(scene_number)
        except Exception:
            return None

    async def _ensure_cache_coverage(
        self,
        cache_key: Tuple[str, int],
        cached_entry: Dict[str, Any],
        workflow_state_id: Optional[str],
        scene_number: int,
        requested_categories: Optional[List[str]],
    ) -> None:
        diagnostics = dict(cached_entry.get("diagnostics", {}))
        cached_assets = dict(cached_entry.get("assets", {}))
        cached_categories = set(
            diagnostics.get("cached_categories")
            or diagnostics.get("categories")
            or cached_assets.keys()
        )

        if not requested_categories:
            if diagnostics.get("cached_full"):
                return
            assets_update, diag_update = await self._build_assets(
                workflow_state_id,
                scene_number,
                None,
            )
            cached_assets.update(assets_update)
            diagnostics.update(diag_update)
            cached_categories = set(cached_assets.keys())
            diagnostics["categories"] = sorted(cached_categories)
            diagnostics["cached_categories"] = sorted(cached_categories)
            diagnostics["cached_full"] = True
            cached_entry["assets"] = cached_assets
            cached_entry["diagnostics"] = diagnostics
            self._asset_cache[cache_key] = cached_entry
            return

        requested_set = set(requested_categories)
        missing = requested_set - cached_categories
        if not missing:
            return

        assets_update, diag_update = await self._build_assets(
            workflow_state_id,
            scene_number,
            list(missing),
        )
        cached_assets.update(assets_update)
        diagnostics.update(diag_update)
        cached_categories = set(cached_assets.keys())
        diagnostics["categories"] = sorted(cached_categories)
        diagnostics["cached_categories"] = sorted(cached_categories)
        diagnostics["cached_full"] = diagnostics.get("cached_full", False)
        cached_entry["assets"] = cached_assets
        cached_entry["diagnostics"] = diagnostics
        self._asset_cache[cache_key] = cached_entry

    def _normalize_categories(self, categories: Any) -> Optional[List[str]]:
        if categories is None:
            return None
        if isinstance(categories, (list, tuple, set)):
            raw = [str(cat).strip() for cat in categories if str(cat).strip()]
        else:
            normalized = str(categories).strip()
            raw = [normalized] if normalized else []

        seen = set()
        ordered: List[str] = []
        for item in raw:
            if item and item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered or None

    def _include_category(
        self,
        requested: Optional[List[str]],
        category: str,
    ) -> bool:
        if not requested:
            return True
        return category in requested

    def _filter_categories(
        self,
        cached_result: Dict[str, Any],
        requested_categories: Optional[List[str]],
    ) -> Dict[str, Any]:
        source_assets = cached_result.get("assets", {}) or {}
        if requested_categories:
            filtered_assets = {
                key: value
                for key, value in source_assets.items()
                if key in requested_categories
            }
        else:
            filtered_assets = dict(source_assets)

        original_diag = cached_result.get("diagnostics", {}) or {}
        diagnostics = dict(original_diag)
        diagnostics["categories"] = list(filtered_assets.keys())

        return {
            "scene_number": cached_result.get("scene_number"),
            "workflow_state_id": cached_result.get("workflow_state_id"),
            "assets": filtered_assets,
            "diagnostics": diagnostics,
        }


__all__ = ["ConsistencyTool"]

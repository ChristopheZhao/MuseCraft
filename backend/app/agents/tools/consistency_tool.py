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
                                        "visual_description": {"max_text": 400},
                                        "narrative_description": {"max_text": 240},
                                    },
                                },
                                "continuity": {
                                    "fields": {
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
                    "scene_number": {"type": "integer"},
                    "scene_info_ref": {"type": "string"},
                    "use_cache": {"type": "boolean"},
                },
                "required": ["scene_number", "scene_info_ref"],
            }
        if action == "register_reference":
            return {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer"},
                    "reference_type": {"type": "string"},
                    "reference_value": {"type": "string"},
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
            use_cache = True if "use_cache" not in params else bool(params.get("use_cache"))
            payload, diagnostics = await self._collect_assets(
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
            await self._memory_provider.store_scene_final_frame(scene_number, ref_value)
            for key in list(self._asset_cache.keys()):
                if isinstance(key, tuple) and len(key) == 2 and key[1] == scene_number:
                    self._asset_cache.pop(key, None)
            return {"stored": True, "scene_number": scene_number}

        raise ValueError(f"Unsupported action: {action}")

    async def _collect_assets(
        self,
        scene_info_ref: str,
        scene_number: int,
        *,
        use_cache: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        cache_key = (scene_info_ref, scene_number)
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

        assets: Dict[str, Any] = {}
        assets["style"] = self._extract_style_assets(scene_info)
        assets["characters"] = self._extract_character_assets(scene_info, scene_entry)
        assets["environment"] = self._extract_environment_assets(scene_info, scene_entry, scene_number)
        assets["continuity"] = self._extract_continuity_assets(scene_entry)

        self._asset_cache[cache_key] = assets
        diagnostics["cached_categories"] = list(assets.keys())
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
        if isinstance(concept_plan, dict):
            if concept_plan.get("consistency_guidelines"):
                style_assets["consistency_guidelines"] = concept_plan.get("consistency_guidelines") or {}
            if concept_plan.get("intelligent_style_design"):
                style_assets["intelligent_style_design"] = concept_plan.get("intelligent_style_design") or {}
        if scene_info.get("intelligent_style"):
            style_assets["intelligent_style"] = scene_info.get("intelligent_style") or {}
        if scene_info.get("intelligent_style_design") and "intelligent_style_design" not in style_assets:
            style_assets["intelligent_style_design"] = scene_info.get("intelligent_style_design") or {}
        return style_assets

    def _extract_character_assets(self, scene_info: Dict[str, Any], scene_entry: Dict[str, Any]) -> Dict[str, Any]:
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
        return {
            "characters": characters,
            "present": present,
            "descriptions": descriptions,
            "guidelines": guidelines,
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
        }
        if isinstance(scene_entry, dict) and scene_entry:
            env.update(
                {
                    "visual_description": scene_entry.get("visual_description", ""),
                    "narrative_description": scene_entry.get("narrative_description", ""),
                }
            )
        concept_plan = scene_info.get("concept_plan") or {}
        if isinstance(concept_plan, dict):
            guidelines = (concept_plan.get("consistency_guidelines") or {}).get("environment_consistency", "")
            if isinstance(guidelines, str) and guidelines.strip():
                env["guidelines"] = guidelines.strip()
        return env

    def _extract_continuity_assets(self, scene_entry: Dict[str, Any]) -> Dict[str, Any]:
        depends_on = None
        if isinstance(scene_entry, dict):
            depends_on = scene_entry.get("depends_on_scene") or scene_entry.get("depends_on")
        try:
            depends_on = int(depends_on) if depends_on is not None else None
        except Exception:
            depends_on = None
        return {"depends_on_scene": depends_on}

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

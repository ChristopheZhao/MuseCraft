"""ConsistencyTool - gather per-scene prompt assets and continuity hints."""
from __future__ import annotations

from typing import Any, Dict, Optional, List, Tuple

from .base_tool import BaseTool, ToolMetadata, ToolType, ToolInput
from ..utils.memory_helpers import get_mas_working_memory
from ..adapters.video.memory_adapter import VideoMemoryAdapter
from ...core.scene_continuity_memory import get_scene_continuity_memory


class _WMFactsProvider:
    """Default facts provider that reads from MAS WorkingMemory."""

    async def get_fact(self, workflow_state_id: str, key: str) -> Any:
        wm = get_mas_working_memory(workflow_state_id)
        return wm.get(key, None) if wm else None

    async def get_all_facts(self, workflow_state_id: str) -> Dict[str, Any]:
        wm = get_mas_working_memory(workflow_state_id)
        return dict(getattr(wm, "facts", {}) or {}) if wm else {}

    async def get_scene(self, workflow_state_id: str, scene_number: int) -> Optional[Dict[str, Any]]:
        wm = get_mas_working_memory(workflow_state_id)
        if wm is None:
            return None
        # scene_overview 优先
        overview = wm.get("scene_overview", {})
        scenes = []
        if isinstance(overview, dict):
            scenes = overview.get("scenes") or []
        for scene in scenes or []:
            try:
                if int(scene.get("scene_number")) == int(scene_number):
                    return scene
            except Exception:
                continue
        # 回落到视频适配器视图
        try:
            adapter = VideoMemoryAdapter(wm)
            return adapter.scene_view(scene_number)
        except Exception:
            return None

    async def get_all_scenes(self, workflow_state_id: str) -> Dict[int, Any]:
        wm = get_mas_working_memory(workflow_state_id)
        if wm is None:
            return {}
        overview = wm.get("scene_overview", {})
        scenes = []
        if isinstance(overview, dict):
            scenes = overview.get("scenes") or []
        result: Dict[int, Any] = {}
        for scene in scenes or []:
            try:
                sn = int(scene.get("scene_number"))
                result[sn] = scene
            except Exception:
                continue
        if result:
            return result
        try:
            adapter = VideoMemoryAdapter(wm)
            for sn in getattr(wm, "scenes", {}) or {}:
                result[int(sn)] = adapter.scene_view(sn)
        except Exception:
            pass
        return result

    async def get_scene_continuity_info(self, workflow_state_id: str, scene_number: int) -> Dict[str, Any]:
        memory = get_scene_continuity_memory()
        return await memory.get_scene_continuity_info(scene_number)


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
        **kwargs: Any,
    ):
        self._facts_provider = facts_provider or _WMFactsProvider()
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

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "get_prompt_assets":
            return {"type": "object", "properties": {"scene_number": {"type": "integer"}}}
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

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        action = tool_input.action
        params = tool_input.parameters or {}
        context = tool_input.context or {}
        wf_id = str(context.get("workflow_state_id") or params.get("workflow_state_id") or "")

        if action == "get_prompt_assets":
            scene_number = int(params.get("scene_number") or 0)
            use_cache = bool(params.get("use_cache"))
            payload, diagnostics = await self._collect_assets(wf_id, scene_number, use_cache=use_cache)
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
            self._asset_cache.pop((wf_id, scene_number), None)
            return {"stored": True, "scene_number": scene_number}

        raise ValueError(f"Unsupported action: {action}")

    async def _collect_assets(self, wf_id: str, scene_number: int, *, use_cache: bool) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        cache_key = (wf_id, scene_number)
        diagnostics: Dict[str, Any] = {"cached_full": False, "cached_categories": []}
        if use_cache and cache_key in self._asset_cache:
            diagnostics["cached_full"] = True
            diagnostics["cached_categories"] = list(self._asset_cache[cache_key].keys())
            return self._asset_cache[cache_key], diagnostics

        facts = await self._facts_provider.get_all_facts(wf_id)
        concept_plan = facts.get("concept_plan") or facts.get("project.concept_plan") or {}
        scene_scripts = facts.get("project.scene_scripts", {}) or {}
        scenes = facts.get("scene_overview", {}).get("scenes", []) if isinstance(facts.get("scene_overview"), dict) else []
        scene_entry = None
        for scene in scenes or []:
            try:
                if int(scene.get("scene_number")) == int(scene_number):
                    scene_entry = scene
                    break
            except Exception:
                continue
        if scene_entry is None:
            scene_entry = await self._facts_provider.get_scene(wf_id, scene_number) or {}

        assets: Dict[str, Any] = {}
        # Style
        style_assets: Dict[str, Any] = {}
        if concept_plan:
            if "intelligent_style_design" in concept_plan:
                style_assets["intelligent_style_design"] = concept_plan.get("intelligent_style_design") or {}
            if "consistency_guidelines" in concept_plan:
                style_assets["consistency_guidelines"] = concept_plan.get("consistency_guidelines") or {}
        assets["style"] = style_assets

        # Characters
        characters: List[Dict[str, Any]] = []
        for role in concept_plan.get("roles") or []:
            if isinstance(role, dict):
                characters.append(role)
        assets["characters"] = {"characters": characters}

        # Environment
        env: Dict[str, Any] = {}
        if isinstance(scene_entry, dict) and scene_entry:
            env = {
                "scene_number": scene_number,
                "visual_description": scene_entry.get("visual_description", ""),
                "narrative_description": scene_entry.get("narrative_description", ""),
                "duration": scene_entry.get("duration"),
                "image_url": scene_entry.get("image_url", ""),
            }
        assets["environment"] = env

        # Scene references / continuity
        continuity: Dict[str, Any] = {
            "requires_continuity": False,
            "from_scene": None,
            "previous_frame_available": False,
            "motion_guidance": {"has_guidance": False},
        }
        scene_refs: Dict[str, Any] = {}
        try:
            scene_refs = await self._memory_provider.retrieve_scene_references(wf_id, scene_number, agent_name="consistency_tool")
        except Exception:
            scene_refs = scene_refs or {}
        try:
            motion = await self._memory_provider.retrieve_motion_guidance(wf_id, scene_number, agent_name="consistency_tool")
            if motion:
                continuity["motion_guidance"] = motion
                continuity["motion_guidance"]["has_guidance"] = True
        except Exception:
            pass
        try:
            cont_info = await self._memory_provider.get_scene_continuity_info(wf_id, scene_number)
            if cont_info:
                continuity.update(cont_info)
        except Exception:
            pass
        assets["scene_references"] = scene_refs
        assets["continuity"] = continuity

        self._asset_cache[cache_key] = assets
        return assets, diagnostics


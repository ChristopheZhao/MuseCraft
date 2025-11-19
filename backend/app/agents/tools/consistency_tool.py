"""Consistency Toolkit - Provides scene/style/character continuity assets.

该工具从共享记忆（Shared Working Memory）的事实层（concept_plan、scenes）与
连续性记忆（SceneContinuityMemory）聚合一致性相关上下文，向下游代理提供
中立的提示资产（style/characters/environment/continuity）。

同时支持注册参考（如尾帧）到连续性记忆，避免在Agent中硬编码供应商或状态。
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from .base_tool import (
    AsyncTool,
    ToolMetadata,
    ToolType,
    ToolValidationError,
)
from .providers import (
    FactsProvider,
    DefaultFactsProvider,
    MemoryProvider,
    DefaultMemoryProvider,
)


class ConsistencyTool(AsyncTool):
    """Tool exposing consistency-aware prompt assets and reference caching."""

    _PREPARED_ASSET_VALUE_SPEC: Dict[str, Any] = {
        "allowed_keys": ["style", "characters", "environment", "continuity", "scene_references"],
        "fields": {
            "style": {
                "allowed_keys": [
                    "color_palette",
                    "mood",
                    "composition",
                    "lighting",
                    "style_tags",
                    "intelligent_style_design",
                    "consistency_hints",
                    "consistency_guidelines",
                    "scene_modifiers",
                ],
                "fields": {
                    "color_palette": {"max_items": 8, "items": {"max_text": 48}},
                    "style_tags": {"max_items": 8, "items": {"max_text": 32}},
                    "mood": {"max_text": 120},
                    "composition": {"max_text": 160},
                    "lighting": {"max_text": 120},
                    "scene_modifiers": {
                        "allowed_keys": ["art_style", "lighting", "notes", "color_palette"],
                        "default_field_spec": {"max_text": 120},
                    },
                    "intelligent_style_design": {
                        "max_dict_items": 8,
                        "default_field_spec": {"max_text": 200},
                    },
                    "consistency_hints": {
                        "max_dict_items": 8,
                        "default_field_spec": {"max_text": 200},
                    },
                    "consistency_guidelines": {
                        "max_dict_items": 8,
                        "default_field_spec": {"max_text": 200},
                    },
                },
                "default_field_spec": {"max_text": 160},
            },
            "characters": {
                "allowed_keys": ["characters", "notes"],
                "fields": {
                    "characters": {
                        "max_items": 8,
                        "items": {
                            "allowed_keys": ["name", "description", "key_traits", "costume", "actions", "notes"],
                            "default_field_spec": {"max_text": 220},
                        },
                    }
                },
            },
            "environment": {
                "allowed_keys": ["location", "lighting", "mood", "season", "key_elements", "camera"],
                "default_field_spec": {"max_text": 200},
            },
            "continuity": {
                "allowed_keys": ["prev_scene_no", "motion_guidance", "tail_frame_ref", "beats", "notes"],
                "fields": {
                    "motion_guidance": {"max_text": 400},
                    "beats": {"max_items": 6, "items": {"max_text": 160}},
                },
                "default_field_spec": {"max_text": 200},
            },
            "scene_references": {
                "max_dict_items": 4,
                "default_field_spec": {"max_text": 256},
            },
        },
    }

    _PROMPT_ASSET_CONTRACT: Dict[str, Any] = {
        "scene_path": "scene_number",
        "memory_slots": [
            {
                "slot": "prepared_assets",
                "path": "assets",
                "value_spec": _PREPARED_ASSET_VALUE_SPEC,
                "allow_empty": True,
                "record_event": {"action": "assets_lookup", "success": True},
            }
        ],
    }

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="consistency_tool",
            version="1.0.0",
            description="聚合并管理多场景的一致性资产（风格/角色/环境），支持注册参考资源",
            tool_type=ToolType.ANALYSIS,
            author="system",
            tags=["一致性", "风格", "角色", "工作流"],
            dependencies=[],
            capabilities=["提示资产查询", "连续性参考缓存"],
        )

    def __init__(
        self,
        facts_provider: Optional[FactsProvider] = None,
        memory_provider: Optional[MemoryProvider] = None,
        **kwargs
    ):
        """初始化一致性工具。

        Args:
            facts_provider: 事实数据提供者，默认使用 SharedWM
            memory_provider: 记忆数据提供者，默认使用全局记忆服务
            **kwargs: 其他工具参数
        """
        kwargs.pop("metadata", None)
        metadata = self.get_metadata()
        super().__init__(metadata=metadata, **kwargs)
        self._asset_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._reference_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}

        # 依赖注入：使用提供的 provider 或默认实现
        self._facts: FactsProvider = facts_provider or DefaultFactsProvider()
        self._memory: MemoryProvider = memory_provider or DefaultMemoryProvider()

    def _initialize(self) -> None:  # pragma: no cover - nothing to initialize yet
        """Initialize tool resources (none required)."""
        return

    def get_output_contract(self, action: str) -> Dict[str, Any]:
        if action == "get_prompt_assets":
            return copy.deepcopy(self._PROMPT_ASSET_CONTRACT)
        return {}

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

    # 取消阶段语义：工具仅具有执行属性

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        base_schema: Dict[str, Any] = {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }

        if action == "get_prompt_assets":
            # Action-level description (neutral, capability-focused)
            base_schema["description"] = (
                "查询并返回指定场景可用于提示词构建的一致性资产（风格/角色/环境/连续性等），"
                "用于在生成前补全先验信息并减少风格漂移。"
            )
            # Parameters (不包含 workflow_state_id，由执行上下文自动提供)
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "目标场景编号",
                },
                "use_cache": {
                    "type": "boolean",
                    "description": "是否允许使用缓存（默认 true）",
                },
            }
            base_schema["required"] = ["scene_number"]
        elif action == "register_reference":
            base_schema["description"] = (
                "登记与指定场景关联的参考资源（如尾帧/连续性帧/调色板等），"
                "可写入连续性记忆并用于后续一致性约束。"
            )
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "关联参考资产的场景编号",
                },
                "reference_type": {
                    "type": "string",
                    "description": "参考类型，例如 final_frame / palette / embedding",
                },
                "reference_value": {
                    "type": ["string", "object"],
                    "description": "参考内容（URL、路径或结构化数据）",
                },
                "metadata": {
                    "type": "object",
                    "description": "辅助诊断的元数据（可选）",
                },
                "persist_continuity": {
                    "type": "boolean",
                    "description": "是否写入连续性记忆（默认 true）",
                },
            }
            base_schema["required"] = ["scene_number", "reference_type", "reference_value"]
        elif action == "get_reference_snapshot":
            base_schema["description"] = (
                "读取已登记的参考资源的轻量快照，用于调试或为后续动作提供上下文。"
            )
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "可选：按场景编号过滤",
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
        use_cache = bool(params.get("use_cache", True))
        workflow_state_id = self._resolve_workflow_state_id(params, context)

        has_style_req = True
        try:
            self.logger.info(
                "PROMPT_ASSETS_REQUEST wf=%s scene=%s categories=%s has_style_req=%s use_cache=%s",
                workflow_state_id,
                scene_number,
                "ALL",
                has_style_req,
                use_cache,
            )
        except Exception:
            pass

        can_cache = bool(workflow_state_id)
        cache_key: Optional[Tuple[str, int]] = (
            (workflow_state_id, scene_number) if can_cache else None
        )

        cache_hit = bool(use_cache and cache_key and cache_key in self._asset_cache)
        try:
            self.logger.info(
                "PROMPT_ASSETS_CACHE %s key=%s",
                "HIT" if cache_hit else "MISS",
                cache_key,
            )
        except Exception:
            pass

        if cache_hit:
            cached = self._asset_cache[cache_key]
            await self._ensure_cache_coverage(
                cache_key,
                cached,
                workflow_state_id,
                scene_number,
            )
            return cached

        assets, diagnostics = await self._build_assets(
            workflow_state_id,
            scene_number,
        )
        try:
            preview = {k: list(v.keys()) if isinstance(v, dict) else v for k, v in (assets or {}).items()}
            self.logger.info(
                "CONSISTENCY_ASSETS scene=%s categories=%s preview_keys=%s",
                scene_number,
                list(assets.keys()),
                preview,
            )
        except Exception:
            pass
        diagnostics["cached_categories"] = list(assets.keys())
        diagnostics["cached_full"] = True
        diagnostics["cache_enabled"] = can_cache
        result = {
            "scene_number": scene_number,
            "workflow_state_id": workflow_state_id,
            "assets": assets,
            "diagnostics": diagnostics,
        }
        if cache_key:
            self._asset_cache[cache_key] = result
        return result

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
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        # 通过 FactsProvider 获取数据，而不是直接调用全局服务
        if workflow_state_id:
            facts = await self._facts.get_all_facts(workflow_state_id)
            scene = await self._facts.get_scene(workflow_state_id, scene_number)
        else:
            facts = {}
            scene = None

        diagnostics: Dict[str, Any] = {
            "workflow_state_found": workflow_state_id is not None and bool(facts),
            "scene_found": scene is not None,
        }

        assets: Dict[str, Any] = {}

        assets["style"] = self._collect_style_assets(
            workflow_state_id,
            facts,
            scene_number,
            scene,
        )

        assets["characters"] = self._collect_character_assets(facts, scene_number, scene)

        assets["environment"] = self._collect_environment_assets(facts, scene)

        assets["continuity"] = await self._collect_continuity_assets(
            workflow_state_id,
            scene_number,
        )

        memory_assets = await self._collect_memory_assets(
            workflow_state_id,
            scene_number,
        )
        if memory_assets.get("scene_references"):
            assets["scene_references"] = memory_assets["scene_references"]
        if memory_assets.get("motion_guidance"):
            continuity_payload = assets.setdefault("continuity", {})
            continuity_payload.setdefault("motion_guidance", memory_assets["motion_guidance"])

        diagnostics["categories"] = list(assets.keys())
        return assets, diagnostics

    async def _collect_memory_assets(
        self,
        workflow_state_id: Optional[str],
        scene_number: int,
    ) -> Dict[str, Any]:
        """通过 MemoryProvider 检索场景参考与动作指导。"""
        if not workflow_state_id:
            return {}
        payload: Dict[str, Any] = {}
        try:
            scene_refs = await self._memory.retrieve_scene_references(
                workflow_state_id,
                scene_number,
                agent_name="video_generator",
            )
            if isinstance(scene_refs, dict) and scene_refs:
                payload["scene_references"] = scene_refs
        except Exception:
            # Provider 异常上抛，工具层决定降级策略：这里忽略错误继续
            pass
        try:
            motion_guidance = await self._memory.retrieve_motion_guidance(
                workflow_state_id,
                scene_number,
                agent_name="video_generator",
            )
            if isinstance(motion_guidance, dict) and motion_guidance:
                payload["motion_guidance"] = motion_guidance
        except Exception:
            # Provider 异常上抛，工具层决定降级策略：这里忽略错误继续
            pass
        return payload

    def _collect_style_assets(
        self,
        workflow_state_id: Optional[str],
        facts: Dict[str, Any],
        scene_number: int,
        scene: Optional[Any],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        concept_plan = facts.get("concept_plan", {}) if isinstance(facts, dict) else {}
        style_design = concept_plan.get("intelligent_style_design") if isinstance(concept_plan, dict) else None
        if isinstance(style_design, dict):
            result["intelligent_style_design"] = {
                key: value for key, value in style_design.items() if isinstance(value, (str, list, dict)) and value
            }
        consistency_hints = concept_plan.get("consistency_hints") if isinstance(concept_plan, dict) else None
        if isinstance(consistency_hints, dict) and consistency_hints:
            result["consistency_hints"] = consistency_hints

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

        try:
            self.logger.debug(
                "CONSISTENCY_STYLE scene=%s keys=%s",
                scene_number,
                list(result.keys()),
            )
            self.logger.info(
                "PROMPT_ASSETS_STYLE wf=%s scene=%s has_style=%s keys=%s",
                workflow_state_id,
                scene_number,
                bool(style_design),
                list(style_design.keys()) if isinstance(style_design, dict) else None,
            )
        except Exception:
            pass

        return result

    def _collect_character_assets(
        self,
        facts: Dict[str, Any],
        scene_number: int,
        scene: Optional[Any],
    ) -> Dict[str, Any]:
        characters: List[Dict[str, Any]] = []
        character_notes: List[str] = []

        scene_names = []
        scene_descriptions = []
        # 从概念计划里查找该场景的角色提示（若有）
        cp = facts.get("concept_plan", {}) if isinstance(facts, dict) else {}
        if isinstance(cp, dict):
            for sc in cp.get('scenes', []) or []:
                try:
                    if int(sc.get('scene_number')) == int(scene_number):
                        scene_names = [str(x).strip() for x in (sc.get('characters_present') or []) if str(x).strip()]
                        scene_descriptions = [str(x).strip() for x in (sc.get('character_descriptions') or []) if str(x).strip()]
                        break
                except Exception:
                    continue
        concept_plan = cp
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

        try:
            self.logger.debug(
                "CONSISTENCY_CHARACTERS scene=%s count=%s",
                scene_number,
                len(result.get("characters", [])),
            )
        except Exception:
            pass

        return result

    def _collect_environment_assets(
        self,
        facts: Dict[str, Any],
        scene: Optional[Any],
    ) -> Dict[str, Any]:
        environment: Dict[str, Any] = {}

        if scene:
            environment["title"] = getattr(scene, "title", "")
            environment["visual_description"] = getattr(scene, "visual_description", "")
            environment["narrative_description"] = getattr(scene, "narrative_description", "")
            environment["props"] = list(getattr(scene, "props_and_objects", []) or [])

        concept_plan = facts.get("concept_plan", {}) if isinstance(facts, dict) else None
        if isinstance(concept_plan, dict):
            guidelines = concept_plan.get("consistency_guidelines")
            if isinstance(guidelines, dict):
                env_guideline = guidelines.get("environment_consistency")
                if env_guideline:
                    environment["guidance"] = env_guideline

        try:
            self.logger.debug(
                "CONSISTENCY_ENV scene=%s keys=%s",
                scene_number,
                list(environment.keys()),
            )
        except Exception:
            pass

        return environment

    async def _collect_continuity_assets(
        self,
        workflow_state_id: Optional[str],
        scene_number: int,
    ) -> Dict[str, Any]:
        """优先从 FactsProvider 读取连续性事实，缺失时回退 MemoryProvider。"""
        info: Dict[str, Any] = {}
        if workflow_state_id:
            try:
                data = await self._facts.get_scene_continuity_info(workflow_state_id, scene_number)
                if isinstance(data, dict):
                    info = data
            except Exception:
                info = {}

        if info:
            continuity: Dict[str, Any] = {}
            for key in (
                "requires_continuity",
                "from_scene",
                "reason",
                "confidence",
                "previous_frame_available",
            ):
                if key in info:
                    continuity[key] = info[key]
            prev_frame = info.get("previous_frame_path") or info.get("tail_frame_ref")
            if prev_frame:
                continuity["tail_frame_ref"] = prev_frame
            try:
                self.logger.debug(
                    "CONSISTENCY_CONTINUITY scene=%s keys=%s",
                    scene_number,
                    list(continuity.keys()),
                )
            except Exception:
                pass
            return continuity

        # FactsProvider 不可用时回退到 MemoryProvider
        try:
            prev_frame = await self._memory.retrieve_previous_frame_url(scene_number)
        except Exception:
            prev_frame = None
        continuity = {"tail_frame_ref": prev_frame} if prev_frame else {}
        try:
            self.logger.debug(
                "CONSISTENCY_CONTINUITY scene=%s keys=%s",
                scene_number,
                list(continuity.keys()),
            )
        except Exception:
            pass
        return continuity

    async def _persist_continuity_reference(self, scene_number: int, reference_value: Any) -> None:
        """通过 MemoryProvider 持久化连续性参考。"""
        if reference_value is None:
            return
        try:
            if isinstance(reference_value, str):
                await self._memory.store_scene_final_frame(scene_number, reference_value)
        except Exception as exc:  # pragma: no cover - guardrail
            # Provider 异常上抛，工具层记录警告
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
        """从执行上下文获取 workflow_state_id。

        注意：workflow_state_id 不是工具参数，而是运行时上下文。
        它由 BaseAgent 在调用前自动注入到 context 中。
        工具不应该从 params 读取此字段（已从 FC schema 移除）。
        """
        # 只从 context 获取，不再支持从 params 获取
        candidate = context.get("workflow_state_id")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        # 如果 context 没有提供，返回 None（某些场景可能不需要 workflow_state_id）
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

    # _resolve_scene removed: scenes从 Shared WM 读取

    async def _ensure_cache_coverage(
        self,
        cache_key: Tuple[str, int],
        cached_entry: Dict[str, Any],
        workflow_state_id: Optional[str],
        scene_number: int,
    ) -> None:
        diagnostics = dict(cached_entry.get("diagnostics", {}))
        cached_assets = dict(cached_entry.get("assets", {}))
        cached_categories = set(
            diagnostics.get("cached_categories")
            or diagnostics.get("categories")
            or cached_assets.keys()
        )

        if diagnostics.get("cached_full"):
            return

        assets_update, diag_update = await self._build_assets(
            workflow_state_id,
            scene_number,
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

__all__ = ["ConsistencyTool"]

"""
Role Analysis Tool - 角色分析工具
分析全局角色清单与每个场景的角色出现及其视觉/风格特征（结构化JSON）。
遵循 Tools-First 与 Prompt Neutrality：不在 Agent 内写规则，逻辑封装在工具内，
由 LLM 依据 schema 进行选择与输出。
"""

from typing import Dict, Any, List

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolError


class RoleAnalysisTool(AsyncTool):
    """角色分析工具：产出全局角色 + 分场景角色出现（结构化输出）。

    设计目标（通用性）：
    - 以参数化方式接受不同风格与场景线索（而非为特定案例定制）。
    - 强调“视觉描述”为最重要输出，供后续图像/视频生成工具使用。
    - 覆盖全部会出现的角色：任何在 per_scene_roles 出现的角色，必须在 roles 中有定义且包含视觉描述。
    """

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="role_analysis_tool",
            version="1.1.0",
            description="分析全局角色与分场景角色出现及视觉特征（结构化JSON；可参数化风格/场景）",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["roles", "character", "analysis", "style"],
            capabilities=[
                "role_catalog_analysis",
                "per_scene_role_presence",
                "visual_trait_extraction",
            ],
            limitations=["requires_llm"]
        )

    def _initialize(self):
        pass

    def get_available_actions(self) -> List[str]:
        return ["analyze_roles_and_scenes"]

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "analyze_roles_and_scenes":
            return {
                "type": "object",
                "properties": {
                    "target_style": {
                        "type": ["string", "null"],
                        "description": "可选：目标风格（如 anime, realistic, noir, watercolor, low-poly 等），用于对视觉描述做风格映射"
                    },
                    "scenario_hint": {
                        "type": ["string", "null"],
                        "description": "可选：场景或题材线索（如现代都市、科幻飞船、奇幻森林、古风庭院等），帮助统一视觉语境"
                    },
                    "scenes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "scene_number": {"type": "integer"},
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "narrative_description": {"type": "string"},
                                "script_text": {"type": "string"}
                            },
                        },
                        "description": "所有场景的文本与脚本"
                    },
                    "concept_plan": {"type": ["object", "null"], "description": "（可选）概念规划，包含角色/风格信息"}
                },
                "required": ["scenes"]
            }
        return {}

    async def _execute_impl(self, tool_input):
        action = tool_input.action
        params = tool_input.parameters or {}
        if action != "analyze_roles_and_scenes":
            raise ToolError(f"Unknown action: {action}", self.metadata.name)

        scenes: List[Dict[str, Any]] = params.get("scenes") or []
        concept_plan = params.get("concept_plan") or {}
        target_style = params.get("target_style") or ""
        scenario_hint = params.get("scenario_hint") or ""
        if not scenes:
            return {"roles": [], "per_scene_roles": {}, "notes": "no scenes"}

        prompt = self._build_prompt(scenes, concept_plan, target_style, scenario_hint)

        import json
        # 供应商无关：从配置/环境选择 LLM 提供方与模型
        from ..tool_registry import get_tool_registry
        from ..base_tool import ToolInput as TI
        import os
        # 1) 优先读取 ai_config 中的工具映射（tool_model_mapping.role_analysis_tool）
        from ....core.ai_config import get_ai_config
        ai_cfg = None
        try:
            ai_cfg = get_ai_config()
        except Exception:
            ai_cfg = None

        model_from_cfg = None
        provider_from_cfg = None
        temp_from_cfg = None
        if ai_cfg is not None:
            try:
                model_from_cfg = ai_cfg.get_model_for_tool("role_analysis_tool")
                if model_from_cfg:
                    provider_from_cfg = ai_cfg.get_model_provider(model_from_cfg)
                    mcfg = ai_cfg.get_model_config(model_from_cfg)
                    if mcfg and getattr(mcfg, 'temperature', None) is not None:
                        temp_from_cfg = float(mcfg.temperature)
            except Exception:
                pass

        # 2) 再看工具局部配置/环境变量覆盖
        provider_tool = (
            (self.config or {}).get("llm_provider")
            or os.getenv("ROLE_ANALYSIS_LLM_PROVIDER")
            or (f"{provider_from_cfg}_client" if provider_from_cfg else None)
            or "zhipu_client"
        )
        model = (
            (self.config or {}).get("model")
            or os.getenv("ROLE_ANALYSIS_MODEL")
            or model_from_cfg
            or None  # 由provider自身默认模型决定
        )
        try:
            temp_cfg = float((self.config or {}).get("temperature", os.getenv("ROLE_ANALYSIS_TEMPERATURE", temp_from_cfg if temp_from_cfg is not None else 0.2)))
        except Exception:
            temp_cfg = temp_from_cfg if temp_from_cfg is not None else 0.2

        # 3) provider_tool 可由 provider 名推导（zhipu->zhipu_client 等）
        prov_alias = {
            "zhipu": "zhipu_client",
            "openai": "openai_client",
            "kimi": "kimi_client",
        }
        if provider_tool in prov_alias:
            provider_tool = prov_alias[provider_tool]

        thinking_type = (
            (self.config or {}).get("thinking_type")
            or os.getenv("ROLE_ANALYSIS_THINKING")
            or "disabled"
        )
        if str(thinking_type).lower() not in {"enabled", "disabled"}:
            thinking_type = "disabled"
        thinking_payload = {"type": thinking_type}

        registry = get_tool_registry()
        provider = registry.get_tool(provider_tool)

        # 如果提供方支持 json_completion，优先使用；否则使用 generate_text + response_format 作为软约束
        actions = []
        try:
            actions = provider.get_available_actions()
        except Exception:
            actions = []
        if "json_completion" in actions:
            # 首选严格JSON路径；若内容为空/无效，再兜底一次 generate_text + response_format
            # 读取模型 max_tokens（若配置可用）
            try:
                from ....core.ai_config import get_ai_config as _gac
                _acfg = _gac()
                _mcfg = _acfg.get_model_config(model) if (model and _acfg) else None
                max_tokens = int(getattr(_mcfg, 'max_tokens', 4000)) if _mcfg else 4000
            except Exception:
                max_tokens = 4000

            json_params = {
                "prompt": prompt,
                **({"model": model} if model else {}),
                "temperature": temp_cfg,
                "max_tokens": max_tokens,
            }
            if provider_tool and provider_tool.lower().startswith("zhipu"):
                json_params["thinking"] = thinking_payload

            res = await provider.execute(TI(action="json_completion", parameters=json_params))
            # 归一化 json 内容
            payload = getattr(res, 'result', res)
            content = None
            parsed_obj = None
            if isinstance(payload, dict):
                if payload.get("json_result") is not None:
                    # 直接采用已解析对象
                    parsed_obj = payload.get("json_result")
                    content = json.dumps(parsed_obj, ensure_ascii=False)
                else:
                    content = payload.get("content") or payload.get("raw_content")

            # 兜底：当 content 为空或无法解析为对象时，回退一次 generate_text + response_format
            if not content:
                try:
                    text_params = {
                        "prompt": prompt,
                        **({"model": model} if model else {}),
                        "temperature": temp_cfg,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                    }
                    if provider_tool and provider_tool.lower().startswith("zhipu"):
                        text_params["thinking"] = thinking_payload

                    res2 = await provider.execute(TI(action="generate_text", parameters=text_params))
                    payload2 = getattr(res2, 'result', res2)
                    content = (payload2 or {}).get("content") if isinstance(payload2, dict) else None
                    # 标记兜底信息（写入 notes）
                    fallback_info = "fallback:generate_text"
                except Exception:
                    fallback_info = "fallback_failed"
            else:
                fallback_info = ""
        else:
            res = await provider.execute(TI(action="generate_text", parameters={
                "prompt": prompt,
                **({"model": model} if model else {}),
                "temperature": temp_cfg,
                "response_format": {"type": "json_object"}
            }))
            payload = getattr(res, 'result', res)
            content = (payload or {}).get("content") if isinstance(payload, dict) else None
        if not content or not isinstance(content, str):
            raise ToolError("Empty role analysis content", self.metadata.name)

        # 解析严格JSON（统一安全解析），失败抛 ToolError，保留一次兜底已在上文 generate_text
        if parsed_obj is None:
            from ...utils.json_utils import safe_json_loads
            try:
                data = safe_json_loads(content, logger=self.logger, context="role_analysis", allow_fallback=False)
            except Exception as exc:
                raise ToolError(f"Role analysis JSON parsing failed: {exc}", self.metadata.name)
        else:
            data = parsed_obj
        if not isinstance(data, dict):
            raise ToolError("Role analysis not a JSON object", self.metadata.name)
        # 规范返回字段
        roles = data.get("roles") or []
        per_scene_roles = data.get("per_scene_roles") or {}
        notes = data.get("notes") or (fallback_info if isinstance(fallback_info, str) else "")
        return {"roles": roles, "per_scene_roles": per_scene_roles, "notes": notes}

    def _build_prompt(self, scenes: List[Dict[str, Any]], concept_plan: Dict[str, Any], target_style: str = "", scenario_hint: str = "") -> str:
        import json
        # 提供最小上下文，避免工具名/参数名泄露
        cp_roles = []
        try:
            cp_roles = ((concept_plan or {}).get('content_elements') or {}).get('characters') or []
        except Exception:
            cp_roles = []

        # 使用中性示例（仅作结构参考，非特定题材）
        examples = {
            "roles": [
                {
                    "name": "角色A",
                    "display_name": "角色A",
                    "archetype_or_identity": "坚韧的探索者",
                    "species_or_breed": "人类",
                    "signature_outfit_or_props": ["功能性夹克", "便携相机"],
                    "key_traits": ["短发", "健康肤色", "轻装"],
                    "color_palette": ["砂岩棕", "风暴灰"],
                    "visual_description": "短发、轻装的人类探索者，功能性夹克与便携相机作为标志性物件，色调偏砂岩棕与风暴灰。"
                }
            ],
            "per_scene_roles": {
                "1": ["角色A"],
                "2": [
                    {
                        "name": "角色A",
                        "display_name": "角色A",
                        "visual_description": "场景2中戴上防护眼镜和围巾以抵抗风沙，其他设定保持一致"
                    },
                    "角色B"
                ]
            }
        }

        style_hint_block = ""
        if isinstance(target_style, str) and target_style.strip():
            style_hint_block += f"目标风格参考：{target_style.strip()}\n"
        if isinstance(scenario_hint, str) and scenario_hint.strip():
            style_hint_block += f"场景/题材线索：{scenario_hint.strip()}\n"

        return (
            "你是影视分镜与角色设定的专业顾问，请基于给定场景文本，"
            "输出全局角色清单（结构化）以及每个场景出现的角色与其核心视觉要点。\n\n"
            "要求：\n"
            "- 仅输出 JSON；\n"
            "- JSON 顶层键：roles, per_scene_roles, notes；\n"
            "- roles 为数组，元素需包含：\n"
            "  name, display_name, archetype_or_identity, species_or_breed, signature_outfit_or_props[], key_traits[], color_palette[], visual_description；\n"
            "  其中 visual_description 为最重要字段，聚焦可见外观：体型/身高、年龄感、发型、肤色或种族、服装/配饰、标志性道具、整体色调；避免剧情与性格主描述；\n"
            "- per_scene_roles 为对象：key 为场景号字符串；value 为角色名数组或对象数组（对象可给出该场景的视觉补充/变化，字段至少包含 name/display_name，建议包含 visual_description 作为该场景增量）；\n"
            "- 覆盖所有会出现的角色：任意出现在 per_scene_roles 的角色，必须在 roles 中定义且包含 visual_description；\n"
            "- 若概念角色库提供别名/设定，可复用并归一到清晰的 display_name；\n"
            + (f"\n{style_hint_block}\n" if style_hint_block else "")
            + f"概念角色库(可选)：\n{json.dumps(cp_roles, ensure_ascii=False, indent=2)}\n\n"
            + f"场景文本(必选)：\n{json.dumps(scenes, ensure_ascii=False, indent=2)}\n\n"
            + f"示例(结构参考，非答案)：\n{json.dumps(examples, ensure_ascii=False, indent=2)}\n\n"
            + "请严格输出 JSON（不要代码块围栏、不要额外文字）。"
        )

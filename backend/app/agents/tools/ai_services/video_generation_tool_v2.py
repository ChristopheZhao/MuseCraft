"""
视频生成工具 - 纯粹的执行器，不包含决策逻辑
"""

from typing import Dict, Any, List, Optional
import logging
import json
import re

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .service_interfaces import get_video_service
from ....core.video_config_manager import get_video_config
from ....core.config import settings
from ....core.consistency_policy import get_consistency_policy
from ....services.prompt_safety import apply_prompt_safety, sanitize_prompt, SafetyContext
from ....services.prompt_safety.rewrite import (
    is_sensitive_error as ps_is_sensitive_error,
    rewrite_prompt_preserving_locks as ps_rewrite_preserving_locks,
)
from ....services.reference_bank import get_scene_reference, store_scene_reference
from ....services.enhanced_ai_client import enhanced_ai_client, TaskType


class VideoGenerationTool(AsyncTool):
    """
    视频生成工具 - 纯粹的执行器
    
    职责：
    - 根据给定参数生成视频
    - 不做任何智能决策
    - 只负责调用视频服务和返回结果
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="video_generation",
            version="2.0.0",
            description="根据提示词和图像生成视频，支持5秒或10秒时长，支持场景连续性",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["video", "generation", "executor"],
            capabilities=[
                "text_to_video",
                "image_to_video", 
                "scene_continuity_support",
                "duration_control"
            ],
            limitations=[
                "requires_video_service",
                "rate_limited"
            ]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
        
        self.video_service = None
        self.video_config = get_video_config()
        self._telemetry_logger = logging.getLogger("consistency_telemetry")
        
    def _initialize(self):
        """初始化视频生成工具"""
        try:
            self.video_service = get_video_service()
            # 仅当服务对象存在且可用时，标记功能可用
            self._functional = bool(self.video_service) and getattr(self.video_service, "is_available", lambda: False)()
            # 设置视频生成工具的默认超时时间（通过配置，不硬编码）
            # 注意：这里只设置工具级别的默认值，实际超时由base_tool.py的优先级逻辑决定
            self.config.setdefault('default_timeout', settings.VIDEO_GENERATION_TOOL_TIMEOUT)
            try:
                from .service_interfaces import get_service_manager
                services = get_service_manager().get_available_services()
                self.logger.info(f"Video services available: {services.get('video', [])}")
                # 观测：初始化阶段记录 service 与 functional 标记
                try:
                    vs_name = type(self.video_service).__name__ if self.video_service else None
                    self.logger.info(f"VideoGenerationTool init: functional={self._functional} service={vs_name}")
                except Exception:
                    pass
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"Failed to initialize video service: {e}")
            self._functional = False
        
        if not self._functional:
            self.logger.warning("VideoGenerationTool not functional - video service unavailable")
    
    def get_available_actions(self) -> List[str]:
        return [
            "generate_with_continuity",
            "generate_video",
            "get_capabilities"
        ]

    def get_fc_visibility(self) -> Dict[str, Any]:
        """对 FC 暴露仅保留生成视频的核心动作"""
        return {
            "expose": True,
            "allowed_actions": ["generate_with_continuity"]
        }

    # 取消阶段语义：工具仅具有执行属性

    def _fetch_capabilities(self, log_failure: bool = False):
        if not self.video_service or not hasattr(self.video_service, "get_capabilities"):
            return None
        try:
            return self.video_service.get_capabilities()
        except Exception as exc:
            if log_failure:
                try:
                    self.logger.warning("Failed to fetch video capabilities: %s", exc)
                except Exception:
                    pass
            return None

    def _validate_prompt_length(self, prompt: Optional[str], prompt_caps=None):
        if not prompt or not isinstance(prompt, str):
            return
        if prompt_caps is None:
            caps = self._fetch_capabilities()
            prompt_caps = getattr(caps, "prompt", None) if caps else None
        if not prompt_caps or not getattr(prompt_caps, "max_bytes", None):
            return
        try:
            limit = int(prompt_caps.max_bytes)
        except Exception:
            limit = prompt_caps.max_bytes
        if not isinstance(limit, int) or limit <= 0:
            return
        prompt_bytes = prompt.encode("utf-8")
        if len(prompt_bytes) <= limit:
            return
        approx_cn = getattr(prompt_caps, "approx_chinese_chars", None)
        approx_en = getattr(prompt_caps, "approx_english_chars", None)
        hint_parts = []
        if approx_cn:
            hint_parts.append(f"约{approx_cn}个中文字符")
        if approx_en:
            hint_parts.append(f"{approx_en}个英文字符")
        limit_hint = "或".join(hint_parts) if hint_parts else f"{limit}字节"
        raise ToolValidationError(
            f"prompt 超过供应商限制（需控制在{limit_hint}以内）",
            self.metadata.name,
        )
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        # 获取当前提供商配置用于动态schema
        provider_config = self.video_config.get_current_provider_config()

        capabilities = self._fetch_capabilities(log_failure=True)

        resolution_cap = getattr(capabilities, "resolution", None) if capabilities else None
        resolution_options = list(provider_config.resolution_options or [])
        resolution_aliases = dict(getattr(provider_config, "resolution_aliases", {}) or {})
        if resolution_cap:
            if resolution_cap.options:
                resolution_options = list(resolution_cap.options)
            if resolution_cap.aliases:
                resolution_aliases = dict(resolution_cap.aliases)

        ratio_cap = getattr(capabilities, "ratio", None) if capabilities else None
        ratio_options = list(getattr(provider_config, "ratio_options", []) or [])
        ratio_aliases = dict(getattr(provider_config, "ratio_aliases", {}) or {})
        if ratio_cap:
            if ratio_cap.options:
                ratio_options = list(ratio_cap.options)
            if ratio_cap.aliases:
                ratio_aliases = dict(ratio_cap.aliases)

        resolution_enum: List[str] = []
        try:
            if resolution_cap:
                resolution_enum = resolution_cap.expand_enum()
            else:
                resolution_enum = list(resolution_options or [])
                for alias in resolution_aliases.keys():
                    if alias not in resolution_enum:
                        resolution_enum.append(alias)
        except Exception:
            resolution_enum = list(resolution_options or [])

        resolution_schema: Dict[str, Any] = {
            "type": "string",
            "description": "可选：视频分辨率（如720p/1080p），影响画质与成本"
        }
        if resolution_enum:
            resolution_schema["enum"] = resolution_enum
        resolution_alias_schema: Dict[str, Any] = dict(resolution_schema)
        resolution_alias_schema["description"] = "可选：分辨率别名（rs），工具会自动映射为实际尺寸"

        ratio_schema: Dict[str, Any] = {
            "type": "string",
            "description": "可选：画幅比例（如16:9/9:16），供应商将自动适配",
        }
        ratio_alias_schema: Dict[str, Any] = dict(ratio_schema)
        ratio_alias_schema["description"] = "可选：画幅比例别名（rt），含义同ratio"
        ratio_enum: List[str] = []
        try:
            if ratio_cap:
                ratio_enum = ratio_cap.expand_enum()
            else:
                ratio_enum = list(ratio_options or [])
                for alias in ratio_aliases.keys():
                    if alias not in ratio_enum:
                        ratio_enum.append(alias)
        except Exception:
            ratio_enum = list(ratio_options or [])
        if ratio_enum:
            ratio_schema["enum"] = ratio_enum
            ratio_alias_schema["enum"] = ratio_enum

        prompt_field: Dict[str, Any] = {
            "type": "string",
            "description": "视频生成提示词，描述期望的视频内容和动作",
        }
        try:
            prompt_caps = getattr(capabilities, "prompt", None) if capabilities else None
            if prompt_caps:
                description_suffix = prompt_caps.description_suffix
                if not description_suffix:
                    parts = []
                    if prompt_caps.approx_chinese_chars and prompt_caps.approx_english_chars:
                        parts.append(
                            f"约{prompt_caps.approx_chinese_chars}个中文或{prompt_caps.approx_english_chars}个英文字符以内"
                        )
                    elif prompt_caps.approx_chinese_chars:
                        parts.append(f"约{prompt_caps.approx_chinese_chars}个中文字符以内")
                    elif prompt_caps.approx_english_chars:
                        parts.append(f"约{prompt_caps.approx_english_chars}个英文字符以内")
                    if prompt_caps.note:
                        parts.append(prompt_caps.note)
                    if parts:
                        description_suffix = "，".join(parts)
                if description_suffix:
                    prompt_field["description"] += f"（{description_suffix}）"
                meta = prompt_caps.to_metadata()
                if meta:
                    prompt_field["vendorConstraints"] = meta
        except Exception as exc:
            try:
                self.logger.warning("Failed to read provider prompt capabilities: %s", exc)
            except Exception:
                pass

        schemas = {
            "generate_video": {
                "type": "object",
                "properties": {
                    "scene_number": {
                        "type": ["integer", "string"],
                        "description": "场景编号：用于产物归属与尾帧登记（必填）"
                    },
                    "prompt": prompt_field,
                    "duration": {
                        "type": "integer",
                        "enum": provider_config.duration_capabilities,
                        "description": f"视频时长（秒），可选：{provider_config.duration_capabilities}。简单场景选择较短时长，复杂动作场景选择较长时长"
                    },
                    "image_url": {
                        "type": "string",
                        "description": "参考图像URL或base64数据（可选）"
                    },
                    "resolution": resolution_schema,
                    "rs": resolution_alias_schema,
                    "ratio": ratio_schema,
                    "rt": ratio_alias_schema,
                    "continuity_frame": {
                        "type": "string", 
                        "description": "场景连续性帧数据（可选，用于场景间的视觉连续性）"
                    },
                    # 不暴露模型参数，交由供应商适配层按输入模式自动选型
                    "first_frame_image": {
                        "type": "string",
                        "description": "首帧图像（可选，用于首尾帧模式）"
                    },
                    "last_frame_image": {
                        "type": "string", 
                        "description": "尾帧图像（可选，用于首尾帧模式）"
                    },
                    # 结构化角色/风格/负向约束（可选，用于提示词合并）
                    "character_constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：角色设定列表（将在工具层合并到提示词）"
                    },
                    "character_constraints_struct": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "display_name": {"type": "string"},
                                "species_or_breed": {"type": "string"},
                                "archetype_or_identity": {"type": "string"},
                                "signature_outfit_or_props": {"type": "array", "items": {"type": "string"}},
                                "key_traits": {"type": "array", "items": {"type": "string"}},
                                "role": {"type": "string"}
                            }
                        },
                        "description": "可选：结构化角色先验（包含物种/原型/标志道具等），优先使用"
                    },
                    "style_constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：画风/美学/色彩/构图等风格约束（将在工具层合并到提示词）"
                    },
                    "negative_constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：需要避免的元素列表（将合并到提示词）"
                    }
                },
                "required": ["scene_number", "prompt", "duration"]
            },
            "generate_with_continuity": {
                "type": "object",
                "properties": {
                    "scene_number": {"type": ["integer", "string"], "description": "可选：用于管道追踪与尾帧登记"},
                    "scene_info_ref": {
                        "type": "string",
                        "description": "可选：场景信息引用路径；若提供则工具内部构建包含一致性约束的完整提示词"
                    },
                    "emit_last_frame": {"type": "string", "enum": ["auto", "always", "never"], "description": "生成成功后是否自动提取并上传尾帧（auto按DAG出边判断）"},
                    "workflow_state_id": {"type": "string", "description": "可选：在auto模式下用于出边计算"},
                    "prompt": prompt_field,
                    "duration": {"type": "integer", "enum": provider_config.duration_capabilities, "description": f"视频时长（秒），可选：{provider_config.duration_capabilities}"},
                    "depends_on_scene": {"type": ["integer", "string", "null"], "description": "可选：依赖的上一场景编号"},
                    "previous_video_url": {"type": "string", "description": "可选：上一场景视频URL；若提供工具将自动抽取尾帧"},
                    "image_url": {"type": "string", "description": "可选：参考图像URL（若无连续性信息）"},
                    # 不暴露模型参数，交由供应商适配层按输入模式自动选型
                    "persist": {"type": "boolean", "description": "是否持久化产物（默认true）"},
                    # 结构化角色/风格/负向约束（可选，用于提示词合并）
                    "character_constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：角色设定列表（将在工具层合并到提示词）"
                    },
                    "resolution": resolution_schema,
                    "rs": resolution_alias_schema,
                    "ratio": ratio_schema,
                    "rt": ratio_alias_schema,
                    "character_constraints_struct": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "display_name": {"type": "string"},
                                "species_or_breed": {"type": "string"},
                                "archetype_or_identity": {"type": "string"},
                                "signature_outfit_or_props": {"type": "array", "items": {"type": "string"}},
                                "key_traits": {"type": "array", "items": {"type": "string"}},
                                "role": {"type": "string"}
                            }
                        },
                        "description": "可选：结构化角色先验（包含物种/原型/标志道具等），优先使用"
                    },
                    "style_constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：画风/美学/色彩/构图等风格约束（将在工具层合并到提示词）"
                    },
                    "negative_constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：需要避免的元素列表（将合并到提示词）"
                    }
                },
                "required": ["scene_number", "duration"]
            },
            "get_capabilities": {
                "type": "object",
                "properties": {},
                "description": "获取当前视频生成服务的能力信息"
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行视频生成工具"""
        # 懒加载/延迟初始化：若初始化时服务未可用（例如进程晚注入密钥），此处再尝试一次获取
        if not self._functional:
            try:
                self.video_service = get_video_service()
                self._functional = bool(self.video_service) and getattr(self.video_service, "is_available", lambda: False)()
                if self._functional:
                    self.logger.info("Video service became available on first use; proceeding")
                else:
                    try:
                        from .service_interfaces import get_service_manager
                        services = get_service_manager().get_available_services()
                        self.logger.warning(f"Video service still unavailable on first use; available_video_services={services.get('video', [])}")
                    except Exception:
                        pass
            except Exception:
                pass
        if not self._functional:
            raise ToolError("VideoGenerationTool not functional - video service unavailable", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "generate_video":
            return await self._generate_video(params)
        elif action == "generate_with_continuity":
            return await self._generate_with_continuity(params)
        elif action == "get_capabilities":
            return await self._get_capabilities()
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _generate_video(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成视频 - 纯粹的执行，不做决策"""
        # 运行时守护：若 service 丢失或接口缺失，先尝试“无条件重获服务实例”
        if (self.video_service is None) or (not hasattr(self.video_service, "generate_video")):
            try:
                from .service_interfaces import get_video_service as _gvs, get_service_manager as _gsm
                self.video_service = _gvs()
                # 重新评估功能位
                self._functional = bool(self.video_service) and getattr(self.video_service, "is_available", lambda: False)()
                if self._functional and hasattr(self.video_service, "generate_video"):
                    vs_name = type(self.video_service).__name__
                    self.logger.info(f"RUNTIME_RECOVER: reacquired video_service={vs_name}")
                else:
                    services = _gsm().get_available_services()
                    self.logger.warning(f"RUNTIME_RECOVER_FAILED: video_service missing/invalid; available_video_services={services.get('video', [])}")
            except Exception as _e:
                self.logger.warning(f"RUNTIME_RECOVER_ERROR: {str(_e)}")

        # 运行时再次校验服务可用性，避免 NoneType 调用；不可用则尝试回退
        if not self._functional or not self.video_service or not hasattr(self.video_service, "generate_video"):
            # 诊断：记录触发回退的具体原因
            try:
                cond_functional = not self._functional
                cond_service_none = not bool(self.video_service)
                cond_missing_method = not hasattr(self.video_service, "generate_video") if self.video_service else True
                vs_name = type(self.video_service).__name__ if self.video_service else None
                from .service_interfaces import get_service_manager
                services = get_service_manager().get_available_services()
                self.logger.warning(
                    f"FALLBACK_TO_VENDOR: functional={not cond_functional} service={vs_name} "
                    f"service_none={cond_service_none} missing_generate={cond_missing_method} "
                    f"available_video_services={services.get('video', [])}"
                )
            except Exception:
                pass
            # 回退到 zhipu_client.generate_video（供应商无关的统一入口），不影响FC编排
            try:
                from ..tool_registry import get_tool_registry
                from ..base_tool import ToolInput as TI
                registry = get_tool_registry()
                zhipu = registry.get_tool("zhipu_client")
                # 显式传递超时，优先使用工具自身配置或settings
                timeout = (
                    self.config.get("timeout")
                    or getattr(settings, "VIDEO_GENERATION_TOOL_TIMEOUT", None)
                    or getattr(settings, "DEFAULT_TOOL_TIMEOUT", 120)
                )
                self.logger.info("FALLBACK_TO_VENDOR: using zhipu_client.generate_video")
                return await zhipu.execute(TI(action="generate_video", parameters=params, timeout=timeout))
            except Exception:
                raise ToolError("VideoGenerationTool not functional - video service unavailable", self.metadata.name)

        capabilities = self._fetch_capabilities()
        prompt_caps = getattr(capabilities, "prompt", None) if capabilities else None
        resolution_cap = getattr(capabilities, "resolution", None) if capabilities else None
        ratio_cap = getattr(capabilities, "ratio", None) if capabilities else None

        prompt = params["prompt"]
        # 合并结构化角色/风格/负向约束为提示词附加段（供应商无关、集中处理）
        try:
            char_cons = params.get("character_constraints") or []
            char_struct = params.get("character_constraints_struct") or []
            style_cons = params.get("style_constraints") or []
            neg_cons = params.get("negative_constraints") or []
            consistency_meta = params.pop('_consistency_meta', {}) if isinstance(params, dict) else {}
            extra = []
            # 角色约束（结构化）
            if isinstance(char_cons, list) and char_cons:
                if "角色设定" not in prompt:
                    extra.append("角色设定：" + "；".join([str(x) for x in char_cons if isinstance(x, str) and x.strip()]))
            # 结构化角色先验（优先）
            if isinstance(char_struct, list) and char_struct:
                lines = []
                for it in char_struct:
                    if not isinstance(it, dict):
                        continue
                    name = it.get('display_name') or it.get('name') or ''
                    segs = []
                    if it.get('archetype_or_identity'):
                        segs.append(f"原型：{it.get('archetype_or_identity')}")
                    if it.get('species_or_breed'):
                        segs.append(f"物种：{it.get('species_or_breed')}")
                    props = it.get('signature_outfit_or_props') or []
                    if props:
                        segs.append("标志道具：" + "、".join([str(p) for p in props if isinstance(p, str) and p.strip()]))
                    traits = it.get('key_traits') or []
                    if traits:
                        segs.append("特征：" + "、".join([str(t) for t in traits if isinstance(t, str) and t.strip()]))
                    role = it.get('role')
                    if role:
                        segs.append(f"叙事角色：{role}")
                    line = (f"{name}：" if name else "") + "；".join(segs)
                    if line.strip():
                        lines.append(line)
                if lines:
                    extra.append("角色设定：" + "；".join(lines))
            # 风格与约束合并（锁定/建议分层）
            policy = get_consistency_policy()
            scene_key = params.get("scene_number")
            scene_ref = str(scene_key) if scene_key is not None else "global"
            style_meta = (consistency_meta.get('style') or {})
            style_snapshot = style_meta.get(scene_ref) or style_meta.get('global')
            if style_snapshot:
                style_locked = style_snapshot.get('locked', [])
                style_suggestions = style_snapshot.get('suggestions', [])
            else:
                style_locked = []
                style_suggestions = [str(x).strip() for x in (style_cons or []) if str(x).strip()]
            if style_locked:
                extra.append("风格锁定：" + "；".join(style_locked))
            if style_suggestions:
                extra.append("风格指导：" + "；".join(style_suggestions))

            negative_meta = (consistency_meta.get('negative') or {})
            negative_snapshot = negative_meta.get(scene_ref)
            if negative_snapshot:
                locked_neg = negative_snapshot.get('locked', [])
                suggested_neg = negative_snapshot.get('suggestions', [])
            else:
                locked_neg = []
                suggested_neg = [str(x).strip() for x in (neg_cons or []) if str(x).strip()]
            if locked_neg:
                extra.append("锁定约束：" + "；".join(locked_neg))
            if suggested_neg:
                extra.append("建议约束：" + "；".join(suggested_neg))
            # 合并追加段
            if extra:
                try:
                    self.logger.info(
                        "CHAR_INJECT(generate_video): chars=%d style_locked=%d style_soft=%d neg_locked=%d neg_soft=%d",
                        len(char_cons or []),
                        len(style_locked),
                        len(style_suggestions),
                        len(locked_neg),
                        len(suggested_neg),
                    )
                    if char_struct:
                        self.logger.info(f"CHAR_INJECT_STRUCT(generate_video): items={len(char_struct or [])}")
                except Exception:
                    pass
                prompt = (prompt + "\n" + "\n".join(extra)) if prompt else "\n".join(extra)
                params["prompt"] = prompt
                self._run_consistency_guard(
                    params.get("workflow_state_id"),
                    scene_key,
                    prompt,
                    style_locked,
                    locked_neg,
                    char_struct if isinstance(char_struct, list) else [],
                    policy,
                )
        except Exception:
            pass
        try:
            prompt_bytes_len = len(prompt.encode("utf-8")) if isinstance(prompt, str) else 0
            self.logger.info(
                "PROMPT_COMBINED(generate_video): len=%d bytes text=%s",
                prompt_bytes_len,
                prompt,
            )
        except Exception:
            pass
        try:
            prompt_caps = getattr(capabilities, "prompt", None) if capabilities else None
            max_bytes = getattr(prompt_caps, "max_bytes", None)
            enforce = bool(getattr(prompt_caps, "enforce", False))
        except Exception:
            max_bytes = None
            enforce = False
        self._validate_prompt_length(prompt, prompt_caps)
        duration = params["duration"]
        image_url = params.get("image_url")
        continuity_frame = params.get("continuity_frame")
        model = params.get("model")
        first_frame_image = params.get("first_frame_image")
        last_frame_image = params.get("last_frame_image")
        
        # 确定最终的图像输入（优先使用连续性帧）
        final_image_input = continuity_frame if continuity_frame else image_url
        
        # 强约束：只接受云端URL（http/https）。禁止本地路径或base64从Agent/FC跨边界传入。
        if final_image_input and isinstance(final_image_input, str):
            if final_image_input.startswith("data:") or not (final_image_input.startswith("http://") or final_image_input.startswith("https://")):
                raise ToolError("image_url must be a cloud URL (http/https); do not pass local path or base64", self.metadata.name)
        
        # 统一校验/纠偏：duration 必须在当前 provider 的能力范围内
        provider_config = self.video_config.get_current_provider_config()
        resolution_requested: Optional[str] = None
        resolution_applied: Optional[str] = None
        if "resolution" not in params and params.get("rs") is not None:
            params["resolution"] = params.get("rs")
        raw_resolution = params.get("resolution")
        if raw_resolution is not None:
            if not isinstance(raw_resolution, str):
                raw_resolution = str(raw_resolution)
            raw_resolution = raw_resolution.strip()
            if raw_resolution:
                resolution_requested = raw_resolution
                allowed_resolutions = []
                if resolution_cap and getattr(resolution_cap, "options", None):
                    allowed_resolutions = list(resolution_cap.options)
                else:
                    allowed_resolutions = list(provider_config.resolution_options or [])

                alias_map: Dict[str, str] = {}
                if resolution_cap and getattr(resolution_cap, "aliases", None):
                    alias_map.update(resolution_cap.aliases)
                alias_map.update(getattr(provider_config, "resolution_aliases", {}) or {})

                allowed_with_alias = set(allowed_resolutions) | set(alias_map.keys())
                if allowed_resolutions and raw_resolution not in allowed_with_alias:
                    raise ToolValidationError(
                        f"resolution must be one of {sorted(allowed_with_alias)}",
                        self.metadata.name
                    )
                resolution_applied = alias_map.get(raw_resolution, raw_resolution)
                params["resolution"] = raw_resolution
            else:
                params.pop("resolution", None)
                raw_resolution = None

        ratio_requested: Optional[str] = None
        ratio_applied: Optional[str] = None
        if "ratio" not in params and params.get("rt") is not None:
            params["ratio"] = params.get("rt")
        raw_ratio = params.get("ratio")
        if raw_ratio is not None:
            if not isinstance(raw_ratio, str):
                raw_ratio = str(raw_ratio)
            raw_ratio = raw_ratio.strip()
            if raw_ratio:
                ratio_requested = raw_ratio
                allowed_ratios = []
                if ratio_cap and getattr(ratio_cap, "options", None):
                    allowed_ratios = list(ratio_cap.options)
                else:
                    allowed_ratios = list(getattr(provider_config, "ratio_options", []) or [])

                ratio_alias_map: Dict[str, str] = {}
                if ratio_cap and getattr(ratio_cap, "aliases", None):
                    ratio_alias_map.update(ratio_cap.aliases)
                ratio_alias_map.update(getattr(provider_config, "ratio_aliases", {}) or {})

                allowed_ratios_with_alias = set(allowed_ratios) | set(ratio_alias_map.keys())
                if allowed_ratios and raw_ratio not in allowed_ratios_with_alias:
                    raise ToolValidationError(
                        f"ratio must be one of {sorted(allowed_ratios_with_alias)}",
                        self.metadata.name,
                    )
                ratio_applied = ratio_alias_map.get(raw_ratio, raw_ratio)
                params["ratio"] = raw_ratio
            else:
                params.pop("ratio", None)
                raw_ratio = None
        allowed = list(provider_config.duration_capabilities or [])
        if isinstance(duration, (int, float)) and allowed:
            # 将 float 转成 int（如 6.0 -> 6）
            try:
                duration_int = int(duration)
            except Exception:
                duration_int = duration
            if duration_int not in allowed:
                # 选择距离最近的合法值
                suggestion = min(allowed, key=lambda x: abs(x - duration_int))
                try:
                    self.logger.warning(
                        f"duration {duration_int}s not supported by provider; coercing to {suggestion}s (allowed={allowed})"
                    )
                except Exception:
                    pass
                duration = suggestion
        # 模型选择：尊重调用方/适配层的自动选择
        # 不在工具层强制填充默认模型，留给服务端根据输入模式自动选型
        
        # 记录来源（供应商无关）：单图模式下明确 used_url 来源
        try:
            pre_mode = self._determine_generation_mode(final_image_input, first_frame_image, last_frame_image)
            image_from_cont = bool(params.get('image_from_continuity'))
            image_origin = (
                "first_last_frame" if (first_frame_image and last_frame_image) else
                ("continuity_frame" if (continuity_frame or image_from_cont) else ("reference_image" if image_url else "none"))
            )
            used_url = final_image_input if not (first_frame_image and last_frame_image) else None
            _model_disp = model if model else "(auto)"
            self.logger.info(
                f"🎬 Generating video: duration={duration}s, model={_model_disp}, mode={pre_mode}, "
                f"continuity_applied={bool(continuity_frame) or image_from_cont}, image_origin={image_origin}, "
                f"used_url={(used_url[:120] + '...') if isinstance(used_url, str) else used_url}"
            )
        except Exception:
            self.logger.info(f"🎬 Generating video: duration={duration}s, model={model}")
        
        # 若参考图像为第三方临时签名/受限域名，先做上云再用，降低 403 风险
        try:
            def _needs_rehost(u: Optional[str]) -> bool:
                if not isinstance(u, str) or not u.startswith(("http://", "https://")):
                    return False
                low = u.lower()
                # Ark/TOS 预签名或者带 X-Tos-* 的查询参数，或其它非自家 OSS 域
                risky_markers = ["ark-content-generation", "tos-cn-", "x-tos-", "x-tos-algorithm", "x-tos-credential"]
                return any(m in low for m in risky_markers)

            if isinstance(final_image_input, str) and _needs_rehost(final_image_input):
                try:
                    rehosted = await self._rehost_external_image_url(final_image_input)
                    if isinstance(rehosted, str) and rehosted.startswith("http"):
                        final_image_input = rehosted
                        # 标记来源，便于诊断
                        params['image_rehosted'] = True
                        self.logger.info("IMAGE_REHOST: external image rehosted to OSS public URL for video generation")
                except Exception as _e:
                    # 不中断：若上云失败，保留原URL继续尝试，由服务端判定
                    self.logger.warning(f"IMAGE_REHOST_SKIP: {_e}")
        except Exception:
            pass

        try:
            # 调用视频服务生成视频
            native_audio = self._resolve_native_audio_request(params)
            try:
                self.logger.info(
                    "NATIVE_AUDIO: strategy=%s provider=%s supports=%s requested=%s",
                    native_audio.get("strategy"),
                    native_audio.get("provider"),
                    bool(native_audio.get("supports_native_audio")),
                    bool(native_audio.get("generate_audio")),
                )
            except Exception:
                pass
            result = await self.video_service.generate_video(
                prompt=prompt,
                model=model,
                duration=duration,
                image_url=final_image_input,
                first_frame_image=first_frame_image,
                last_frame_image=last_frame_image,
                resolution=resolution_applied or params.get("resolution"),
                ratio=ratio_applied or params.get("ratio"),
                generate_audio=bool(native_audio.get("generate_audio")),
            )
            
            # 增强返回结果
            result.update({
                "tool_used": self.metadata.name,
                "requested_resolution": resolution_requested,
                "applied_resolution": resolution_applied or params.get("resolution"),
                "requested_ratio": ratio_requested,
                "applied_ratio": ratio_applied or params.get("ratio"),
                "execution_params": {
                    "prompt": prompt,
                    "duration": duration,
                    "model": model,
                    "audio_strategy": native_audio.get("strategy"),
                    "generate_audio": bool(native_audio.get("generate_audio")),
                    "resolution_requested": resolution_requested,
                    "resolution_applied": resolution_applied or params.get("resolution"),
                    "ratio_requested": ratio_requested,
                    "ratio_applied": ratio_applied or params.get("ratio"),
                    "has_continuity_frame": bool(continuity_frame) or bool(params.get('image_from_continuity')),
                    "has_reference_image": bool(image_url),
                    "generation_mode": self._determine_generation_mode(
                        final_image_input, first_frame_image, last_frame_image
                    ),
                    "image_origin": (
                        "first_last_frame" if (first_frame_image and last_frame_image) else
                        ("continuity_frame" if (continuity_frame or params.get('image_from_continuity')) else ("reference_image" if image_url else "none"))
                    ),
                    "image_input_url": final_image_input if isinstance(final_image_input, str) else None
                }
            })
            result["native_audio"] = native_audio
            # 工具层最小验证：必须产生可访问 video_url，否则标记为失败并将 fallback_reason 透传为 error_type
            if not isinstance(result, dict) or not result.get('video_url'):
                status = (result or {}).get('status') if isinstance(result, dict) else None
                fb_reason = (result or {}).get('fallback_reason') if isinstance(result, dict) else None
                provider_error = (result or {}).get('provider_error') if isinstance(result, dict) else None
                mdl = (result or {}).get('model') if isinstance(result, dict) else model
                err_type = str(fb_reason or (status or 'no_video_url'))
                if isinstance(provider_error, dict):
                    err_type = provider_error.get('code') or err_type
                # 使用 ToolError 的 error_code 让上层拿到明确错误类型（如 provider_timeout/sensitive）
                raise ToolError(
                    message=f"video generation returned no url (status={status}, model={mdl}, fallback_reason={fb_reason}, provider_error={provider_error})",
                    tool_name=self.metadata.name,
                    error_code=err_type
                )
            # Provider/model outcome log（仅有URL时记为完成）
            try:
                prov = result.get('provider') or provider_config.provider_name
                mdl = result.get('model') or model
                gen_mode = result.get('execution_params', {}).get('generation_mode')
                if result.get('video_url'):
                    self.logger.info(f"✅ Generation completed: provider={prov} model={mdl} mode={gen_mode}")
                else:
                    self.logger.warning(
                        f"Generation returned no video_url (status={result.get('status')}); provider={prov} model={mdl} mode={gen_mode}"
                    )
            except Exception:
                pass
            
            
            return result

        except Exception as e:
            # 针对 image_url 拉取失败（400/403）的轻量修复重试：上云后重试一次
            emsg = str(e)
            sensitive_details = self._extract_sensitivity_details(emsg, final_image_input if isinstance(final_image_input, str) else None)
            if sensitive_details:
                self.logger.warning(
                    "INPUT_IMAGE_SENSITIVE_DETECTED: scene=%s request_id=%s", args.get("scene_number"), sensitive_details.get("request_id")
                )
                raise ToolError(
                    f"Video generation failed: {sensitive_details.get('provider_error', {}).get('message', 'input image flagged as sensitive')}",
                    self.metadata.name,
                    error_code="sensitive_input_image",
                    details=sensitive_details,
                ) from e
            try_rehost_retry = False
            if isinstance(final_image_input, str) and final_image_input.startswith("http"):
                markers = ["param\":\"image_url\"", "status code: 403", "InvalidParameter", "image_url"]
                if any(m in emsg for m in markers):
                    try_rehost_retry = True
            if try_rehost_retry:
                try:
                    oss_url = await self._rehost_external_image_url(final_image_input)
                    if isinstance(oss_url, str) and oss_url.startswith("http"):
                        self.logger.warning("RETRY_AFTER_IMAGE_REHOST: re-invoking video generation with OSS URL")
                        result = await self.video_service.generate_video(
                            prompt=prompt,
                            model=model,
                            duration=duration,
                            image_url=oss_url,
                            first_frame_image=first_frame_image,
                            last_frame_image=last_frame_image,
                            resolution=resolution_applied or params.get("resolution")
                        )
                        # 同样进行最小验证
                        if not isinstance(result, dict) or not result.get('video_url'):
                            raise ToolError(
                                message="video generation returned no url after rehost",
                                tool_name=self.metadata.name,
                                error_code="image_url_forbidden"
                            )
                        # 附加诊断字段
                        result.update({"fallback_applied": True, "fallback_reason": "image_url_forbidden", "image_rehosted": True})
                        return result
                except Exception as _e:
                    self.logger.error(f"RETRY_AFTER_IMAGE_REHOST_FAILED: {_e}")
            # 非 image_url 类问题或重试失败：按原样抛出
            self.logger.error(f"Video generation failed: {emsg}")
            if isinstance(e, ToolError):
                raise
            raise ToolError(
                f"Video generation failed: {emsg}",
                self.metadata.name,
                error_code=getattr(e, "error_code", None),
                details=sensitive_details if 'sensitive_details' in locals() else None,
            ) from e

    def _extract_sensitivity_details(self, error_message: str, image_input: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse provider error payload to surface structured sensitive-image diagnostics."""
        if "InputImageSensitiveContentDetected" not in (error_message or ""):
            return None

        details: Dict[str, Any] = {"provider": "doubao"}
        payload = {}
        try:
            start_idx = error_message.index('{"error"')
            payload = json.loads(error_message[start_idx:])
        except Exception:
            payload = {}

        provider_error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if provider_error:
            details["provider_error"] = provider_error
            msg = provider_error.get("message", "")
        else:
            msg = error_message

        request_id = None
        try:
            match = re.search(r"Request id:\s*([A-Za-z0-9-]+)", msg or error_message)
            if match:
                request_id = match.group(1)
        except Exception:
            request_id = None
        if request_id:
            details["request_id"] = request_id

        if isinstance(image_input, str) and image_input:
            details["image_url"] = image_input

        return details

    async def _rehost_external_image_url(self, remote_url: str) -> str:
        """将远程URL下载到本地后上传到自有OSS，返回可公开访问的URL。"""
        from ..tool_registry import get_tool_registry
        from ..base_tool import ToolInput as TI
        registry = get_tool_registry()
        # 先通过 file_storage_tool 下载到本地临时区
        file_tool = registry.get_tool("file_storage_tool")
        # 生成一个稳定的 OSS 目标路径
        remote_root = getattr(settings, 'OSS_IMAGE_DIR', 'images').strip('/')
        staging_dir = getattr(settings, 'OSS_STAGING_DIR', 'staging').strip('/')
        prefix = getattr(settings, 'OSS_VIDEO_INPUT_PREFIX', 'video_generation_input')
        import time
        oss_remote_path = f"{remote_root}/{staging_dir}/{prefix}_{int(time.time()*1000)}.jpg"
        # 先下载
        dl = await file_tool.execute(TI(action="upload_from_url", parameters={
            "url": remote_url,
            "destination_key": f"downloads/{int(time.time()*1000)}.bin",
            "metadata": {"source": "video_ref_rehost"}
        }))
        payload = getattr(dl, 'result', dl)
        local_path = None
        if isinstance(payload, dict):
            local_path = payload.get('local_path') or payload.get('file_path')
        if not local_path or not isinstance(local_path, str):
            raise RuntimeError("downloaded file local_path missing")
        # 上传到 OSS 并返回公开 URL
        oss_tool = registry.get_tool("oss_storage")
        up = await oss_tool.execute(TI(action="upload", parameters={
            "local_path": local_path,
            "remote_path": oss_remote_path,
            "public_read": True,
            "content_type": "image/jpeg"
        }))
        up_res = getattr(up, 'result', up)
        if isinstance(up_res, dict) and up_res.get('url'):
            return up_res['url']
        raise RuntimeError("OSS upload did not return url")

    def _log_consistency_event(self, stage: str, workflow_state_id: Any, scene_number: Any, payload: Dict[str, Any]) -> None:
        try:
            record = {
                "stage": stage,
                "workflow_state_id": workflow_state_id,
                "scene_number": scene_number,
                **payload,
            }
            self._telemetry_logger.info(json.dumps(record, ensure_ascii=False))
        except Exception:
            pass

    def _collect_locked_segments(self, consistency_meta: Dict[str, Any], scene_number: Any) -> Dict[str, List[str]]:
        """Return locked segments grouped by type for a given scene."""

        result: Dict[str, List[str]] = {
            "style": [],
            "negative": [],
            "all": [],
        }
        if not isinstance(consistency_meta, dict):
            return result

        scene_ref = str(scene_number) if scene_number is not None else "global"

        try:
            style_meta = consistency_meta.get("style") or {}
            if isinstance(style_meta, dict):
                snapshot = style_meta.get(scene_ref) or style_meta.get("global") or {}
                locked = snapshot.get("locked", []) if isinstance(snapshot, dict) else []
                result["style"] = [str(item).strip() for item in locked if str(item).strip()]
        except Exception:
            result["style"] = []

        try:
            negative_meta = consistency_meta.get("negative") or {}
            if isinstance(negative_meta, dict):
                snapshot = negative_meta.get(scene_ref) or {}
                locked = snapshot.get("locked", []) if isinstance(snapshot, dict) else []
                result["negative"] = [str(item).strip() for item in locked if str(item).strip()]
        except Exception:
            result["negative"] = []

        result["all"] = [item for item in (result["style"] + result["negative"]) if item]
        return result

    @staticmethod
    def _normalize_audio_strategy(value: Any) -> str:
        raw = str(value or "").strip().lower()
        alias_map = {
            "adaptive": "adaptive",
            "auto": "adaptive",
            "prefer_native": "adaptive",
            "provider_only": "provider_only",
            "native_only": "provider_only",
            "mas_only": "mas_only",
            "agent_only": "mas_only",
        }
        return alias_map.get(raw, "adaptive")

    def _resolve_native_audio_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve provider-native audio request from capability and orchestration policy."""
        provider_cfg = self.video_config.get_current_provider_config()
        supports_native = bool(getattr(provider_cfg, "supports_native_audio", False))
        explicit_generate_audio = params.get("generate_audio")
        if isinstance(explicit_generate_audio, str):
            lowered = explicit_generate_audio.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                explicit_generate_audio = True
            elif lowered in {"false", "0", "no", "off"}:
                explicit_generate_audio = False
            else:
                explicit_generate_audio = None
        elif not isinstance(explicit_generate_audio, bool):
            explicit_generate_audio = None

        if isinstance(explicit_generate_audio, bool):
            generate_audio = explicit_generate_audio and supports_native
            return {
                "strategy": "explicit",
                "provider": provider_cfg.provider_name,
                "supports_native_audio": supports_native,
                "generate_audio": bool(generate_audio),
            }

        strategy_value = params.get("audio_strategy") or getattr(settings, "VIDEO_AUDIO_STRATEGY", "adaptive")
        strategy = self._normalize_audio_strategy(strategy_value)

        if strategy == "mas_only":
            generate_audio = False
        elif strategy == "provider_only":
            generate_audio = True if supports_native else False
        else:
            # adaptive(default): enable provider-native audio only when provider supports it.
            generate_audio = True if supports_native else False

        return {
            "strategy": strategy,
            "provider": provider_cfg.provider_name,
            "supports_native_audio": supports_native,
            "generate_audio": bool(generate_audio),
        }

    async def _rewrite_prompt_for_safety(
        self,
        prompt: str,
        locked_segments: List[str],
        rewrite_model: Optional[str],
        workflow_state_id: Any,
        scene_number: Any,
    ) -> tuple[Optional[str], Dict[str, Any]]:
        """Delegate to shared rewrite with locked-segment preservation and telemetry."""
        rewritten, telemetry = await ps_rewrite_preserving_locks(
            prompt,
            locked_segments,
            model=rewrite_model,
            language="zh",
            metadata={"workflow_state_id": workflow_state_id, "scene_number": scene_number, "tool": self.metadata.name},
        )
        return rewritten, telemetry

    @staticmethod
    def _is_sensitive_error(err: ToolError) -> bool:
        return ps_is_sensitive_error(err)

    async def _generate_with_continuity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """合并连续性准备与生成（确定性）：解析上一场景尾帧 → 生成 → 可选存尾帧。"""
        scene_number = params.get("scene_number")
        scene_info_ref = params.get("scene_info_ref")
        prompt = params.get("prompt")
        duration = params.get("duration")
        if not prompt and not scene_info_ref:
            raise ToolValidationError("prompt or scene_info_ref is required", self.metadata.name)

        if scene_info_ref and scene_number is not None:
            try:
                from ..tool_registry import get_tool_registry
                from ..base_tool import ToolInput as TI

                registry = get_tool_registry()
                composer = registry.get_tool("video_prompt_composer")
                if not composer:
                    raise ToolError("video_prompt_composer unavailable", self.metadata.name)
                resp = await composer.execute(
                    TI(
                        action="build_prompt",
                        parameters={
                            "scene_number": scene_number,
                            "scene_info_ref": scene_info_ref,
                        },
                    )
                )
                payload = getattr(resp, "result", resp)
                if not isinstance(payload, dict) or not payload.get("prompt_text"):
                    raise ToolError("video_prompt_composer returned empty prompt", self.metadata.name)
                prompt = payload.get("prompt_text")
                params["prompt"] = prompt
                meta = payload.get("metadata") if isinstance(payload, dict) else {}
                injected = None
                categories = None
                if isinstance(meta, dict):
                    injected = meta.get("consistency_injected")
                    categories = meta.get("consistency_categories")
                try:
                    prompt_bytes_len = len(str(prompt).encode("utf-8")) if isinstance(prompt, str) else 0
                    self.logger.info(
                        "PROMPT_COMPOSED(generate_with_continuity): scene=%s composed_len=%d injected=%s categories=%s",
                        scene_number,
                        prompt_bytes_len,
                        injected,
                        categories,
                    )
                except Exception:
                    pass
            except ToolError:
                raise
            except Exception as exc:
                raise ToolError(f"Prompt composition failed: {exc}", self.metadata.name) from exc

        if not prompt or duration is None:
            raise ToolValidationError("prompt and duration are required", self.metadata.name)

        policy = get_consistency_policy()
        workflow_state_id = params.get("workflow_state_id")
        scene_key = params.get("scene_number")

        consistency_meta = params.get('_consistency_meta') if isinstance(params, dict) else {}
        locked_info = self._collect_locked_segments(consistency_meta, scene_key)
        locked_segments = locked_info.get("all", [])

        prompt_safety_cfg = getattr(policy, "prompt_safety", None)
        prompt = str(prompt)
        advice = None
        sanitized = None
        sanitized_changed = False
        placeholder_map: Dict[str, str] = {}
        if prompt_safety_cfg and getattr(prompt_safety_cfg, "enabled", True):
            try:
                provider_name = None
                if self.video_service and hasattr(self.video_service, "get_provider_name"):
                    provider_name = self.video_service.get_provider_name()

                prompt_for_safety = prompt
                if bool(getattr(prompt_safety_cfg, "preserve_locked_sections", True)) and locked_segments:
                    for idx, segment in enumerate(locked_segments):
                        seg_text = str(segment).strip()
                        if not seg_text:
                            continue
                        token = f"<<LOCKED_{idx}>>"
                        if seg_text in prompt_for_safety:
                            prompt_for_safety = prompt_for_safety.replace(seg_text, token)
                            placeholder_map[token] = seg_text

                safe_prompt, advice = apply_prompt_safety(
                    prompt_for_safety,
                    SafetyContext(
                        modality="video",
                        provider=provider_name,
                        language="zh",
                        metadata={
                            "scene_number": scene_key,
                            "workflow_state_id": workflow_state_id,
                        },
                    ),
                )

                sanitized = sanitize_prompt(
                    safe_prompt,
                    {
                        "modality": "video",
                        "scene_number": scene_key,
                        "tool": self.metadata.name,
                        "advisor_layers": (advice.metadata or {}).get("applied_layers") if advice else None,
                    },
                )
                sanitized_changed = sanitized.changed
                prompt_processed = sanitized.text or safe_prompt

                if placeholder_map:
                    for token, seg_text in placeholder_map.items():
                        prompt_processed = prompt_processed.replace(token, seg_text)

                if not prompt_processed.strip():
                    prompt_processed = prompt

                prompt = prompt_processed
                params["prompt"] = prompt
                self._log_consistency_event(
                    "prompt_safety",
                    workflow_state_id,
                    scene_key,
                    {
                        "enabled": True,
                        "level": str(getattr(prompt_safety_cfg, "level", "moderate")),
                        "sanitized_changed": sanitized_changed,
                        "preserve_locked": bool(getattr(prompt_safety_cfg, "preserve_locked_sections", True)),
                        "locked_segments": locked_segments,
                        "advisor_layers": (advice.metadata or {}).get("applied_layers") if advice else None,
                        "sanitized_matches": sanitized.matches if sanitized else [],
                    },
                )
            except Exception as exc:
                try:
                    self.logger.debug("Prompt safety advisor skipped: %s", exc)
                except Exception:
                    pass
                prompt = str(prompt)
                params["prompt"] = prompt
                self._log_consistency_event(
                    "prompt_safety",
                    workflow_state_id,
                    scene_key,
                    {
                        "enabled": True,
                        "error": str(exc)[:200],
                    },
                )
        else:
            params["prompt"] = prompt
            if prompt_safety_cfg:
                self._log_consistency_event(
                    "prompt_safety",
                    workflow_state_id,
                    scene_key,
                    {
                        "enabled": False,
                        "locked_segments": locked_segments,
                    },
                )

        base_prompt = str(prompt)

        # 纠偏：duration → provider 离散值
        try:
            provider_config = self.video_config.get_current_provider_config()
            allowed = list(provider_config.duration_capabilities or [])
            if allowed and isinstance(duration, (int, float)):
                dur_i = int(duration)
                if dur_i not in allowed:
                    suggestion = min(allowed, key=lambda x: abs(x - dur_i))
                    try:
                        self.logger.warning(
                            f"duration {dur_i}s not supported; coercing to {suggestion}s (allowed={allowed})"
                        )
                    except Exception:
                        pass
                    params["duration"] = suggestion
                    duration = suggestion
        except Exception:
            pass

        # 解析连续性帧：优先 continuity_frame；若提供 previous_video_url 则调用连续性准备工具
        continuity_frame: Optional[str] = params.get("continuity_frame")
        image_url: Optional[str] = params.get("image_url")
        previous_video_url: Optional[str] = params.get("previous_video_url")
        prev_scene_no: Optional[int] = None
        try:
            raw_prev = params.get("depends_on_scene")
            if raw_prev is not None and str(raw_prev).isdigit():
                prev_scene_no = int(raw_prev)
        except Exception:
            prev_scene_no = None

        if not continuity_frame and previous_video_url and scene_key is not None:
            try:
                from ..tool_registry import get_tool_registry
                from ..base_tool import ToolInput as TI

                registry = get_tool_registry()
                prep_tool = registry.get_tool("scene_continuity_preparation")
                if not prep_tool:
                    raise ToolError("scene_continuity_preparation not available", self.metadata.name)

                prep_params: Dict[str, Any] = {
                    "scene_number": int(scene_key),
                    "previous_scene_video_url": previous_video_url,
                }
                if image_url:
                    prep_params["fallback_image_url"] = image_url

                resp = await prep_tool.execute(TI(action="prepare_scene_input", parameters=prep_params))
                payload = getattr(resp, "result", resp)
                if isinstance(payload, dict):
                    continuity_frame = payload.get("image_url") or None
                    if continuity_frame:
                        params["image_from_continuity"] = bool(payload.get("continuity_used"))
            except Exception as e:
                try:
                    self.logger.warning(f"CONTINUITY_EXTRACT_FAILED: {e}")
                except Exception:
                    pass

        if not continuity_frame and not image_url and not previous_video_url:
            try:
                self.logger.info("CONTINUITY_DISABLED: no continuity or reference image; fallback to text")
            except Exception:
                pass

        # 数据URL/本地 → 上传成外链
        if isinstance(continuity_frame, str) and continuity_frame and not (continuity_frame.startswith("http://") or continuity_frame.startswith("https://")):
            try:
                continuity_frame = await self._ensure_remote_image_url(continuity_frame)
            except Exception as e:
                self.logger.warning(f"continuity frame not cloud-accessible, skipping continuity: {e}")
                continuity_frame = None

        next_params = dict(params)
        consistency_meta_snapshot = None
        if isinstance(next_params, dict) and "_consistency_meta" in next_params:
            consistency_meta_snapshot = next_params["_consistency_meta"]

        if continuity_frame:
            next_params["continuity_frame"] = continuity_frame
            # 若供应商支持首尾帧，可由上层按需注入 first/last；此处不强制策略，保持最小职责

        # 生成
        try:
            self.logger.info(
                "DISPATCH generate_with_continuity → vendor: "
                f"scene={params.get('scene_number')}, depends_on={prev_scene_no}, "
                f"continuity_applied={bool(continuity_frame)}, "
                f"first_last_injected={bool(next_params.get('first_frame_image') and next_params.get('last_frame_image'))}"
            )
        except Exception:
            pass
        # 记录风格注入诊断（若存在）与最小软兜底
        try:
            style_cons_gwc = params.get("style_constraints") or []
            if isinstance(style_cons_gwc, list) and style_cons_gwc:
                self.logger.info(f"STYLE_INJECT(generate_with_continuity): styles={len(style_cons_gwc)} source=fc")
        except Exception:
            pass
        if consistency_meta_snapshot is None and isinstance(next_params, dict):
            consistency_meta_snapshot = next_params.get("_consistency_meta")
        try:
            gen_res = await self._generate_video(next_params)
        except ToolError as err:
            should_rewrite = (
                prompt_safety_cfg
                and getattr(prompt_safety_cfg, "enable_rewrite_on_sensitive_error", False)
                and self._is_sensitive_error(err)
            )
            if should_rewrite:
                rewrite_prompt, rewrite_event = await self._rewrite_prompt_for_safety(
                    base_prompt,
                    locked_segments,
                    getattr(prompt_safety_cfg, "rewrite_model", None),
                    workflow_state_id,
                    scene_key,
                )
                original_prompt_text = (next_params.get("prompt") or "").strip()
                if rewrite_prompt and rewrite_prompt.strip() and rewrite_prompt.strip() != original_prompt_text:
                    if rewrite_event:
                        self._log_consistency_event("prompt_rewrite", workflow_state_id, scene_key, rewrite_event)
                    rewrite_params = dict(next_params)
                    if consistency_meta_snapshot is not None:
                        rewrite_params['_consistency_meta'] = consistency_meta_snapshot
                    rewrite_params["prompt"] = rewrite_prompt
                    rewrite_params["prompt_rewrite_reason"] = "sensitive_error"
                    gen_res = await self._generate_video(rewrite_params)
                    if isinstance(gen_res, dict):
                        rewrite_meta = dict(gen_res.get("prompt_safety_rewrite") or {})
                        rewrite_meta.update(
                            {
                                "applied": True,
                                "reason": "sensitive_error",
                                "model": getattr(prompt_safety_cfg, "rewrite_model", None),
                            }
                        )
                        gen_res["prompt_safety_rewrite"] = rewrite_meta
                else:
                    if rewrite_event:
                        if rewrite_event.get("result") == "success" and rewrite_prompt:
                            rewrite_event = dict(rewrite_event)
                            rewrite_event["result"] = "unchanged"
                        self._log_consistency_event("prompt_rewrite", workflow_state_id, scene_key, rewrite_event)
                    raise err
            else:
                raise

        # emit_last_frame（auto按出边）
        try:
            emit_mode = str(params.get("emit_last_frame") or "auto").strip().lower()
        except Exception:
            emit_mode = "auto"
        try:
            scene_no = params.get("scene_number")
            scene_no = int(scene_no) if scene_no is not None and str(scene_no).isdigit() else None
        except Exception:
            scene_no = None
        try:
            should_emit = False
            if emit_mode == "always":
                should_emit = True
            elif emit_mode == "never":
                should_emit = False
            else:
                if scene_no is not None:
                    out_deg = self._get_outdegree_from_wf_or_active(params.get("workflow_state_id"), scene_no)
                    should_emit = out_deg > 0
            if should_emit and isinstance(gen_res, dict) and gen_res.get("video_url"):
                last_url = await self._emit_last_frame(gen_res.get("video_url"), scene_no)
                if last_url:
                    # 存内存 + 写WF（尽力）
                    try:
                        from ....core.scene_continuity_memory import get_scene_continuity_memory
                        mem = get_scene_continuity_memory()
                        if scene_no is not None:
                            await mem.store_scene_final_frame(scene_no, last_url)
                    except Exception:
                        pass
                    try:
                        store_scene_reference(params.get("workflow_state_id"), scene_no, last_url)
                    except Exception:
                        pass
                    # 不再更新 WorkflowState；连续性帧已写入记忆工具/Shared WM 事实
                    cont = dict(gen_res.get("continuity", {}) or {})
                    cont.update({"last_frame_url": last_url})
                    gen_res["continuity"] = cont
        except Exception as e:
            try:
                self.logger.warning(f"emit_last_frame failed (soft): {e}")
            except Exception:
                pass
        return gen_res

    def _run_consistency_guard(
        self,
        workflow_state_id: Any,
        scene_number: Any,
        prompt: str,
        locked_style: List[str],
        locked_negative: List[str],
        char_struct: List[Dict[str, Any]],
        policy,
    ) -> None:
        guard_policy = getattr(policy, "guard", None)
        if not guard_policy:
            return

        issues: List[str] = []
        for text in locked_style:
            if text and text not in prompt:
                issues.append(f"missing_style:{text}")
        for text in locked_negative:
            if text and text not in prompt:
                issues.append(f"missing_negative:{text}")

        if getattr(guard_policy, 'require_signature_props', True):
            for struct in char_struct or []:
                props = struct.get('signature_outfit_or_props') or []
                display_name = struct.get('display_name') or struct.get('name') or '角色'
                for prop in props:
                    prop_text = str(prop).strip()
                    if prop_text and prop_text not in prompt:
                        issues.append(f"signature_prop_missing:{display_name}:{prop_text}")

        payload = {
            "mode": guard_policy.mode,
            "issues": issues,
            "result": "pass" if not issues else "violations",
        }
        self._log_consistency_event("tool_guard", workflow_state_id, scene_number, payload)

        if not issues:
            return

        mode = getattr(guard_policy, 'mode', 'advisory')
        summary = ", ".join(issues)
        if mode == 'enforce':
            raise ToolError(f"Consistency guard failed: {summary}", self.metadata.name, error_code="consistency_guard")
        try:
            self.logger.warning("Consistency guard advisory: %s", summary)
        except Exception:
            pass

    def _get_outdegree_from_wf_or_active(self, wf_id: Optional[str], scene_no: int) -> int:
        """估算某场景的出度（被多少场景依赖）。调用方应提供依赖信息，工具不再读取 shared_wm。"""
        try:
            deps = self.config.get("scene_dependencies") if isinstance(self.config, dict) else None
            if isinstance(deps, dict):
                return sum(1 for _, dep in deps.items() if dep is not None and int(dep) == int(scene_no))
        except Exception:
            return 0
        return 0

    async def _emit_last_frame(self, video_url: str, scene_no: Optional[int] = None) -> Optional[str]:
        if not video_url:
            return None
        try:
            from ..tool_registry import get_tool_registry
            from ..base_tool import ToolInput as TI
            registry = get_tool_registry()
            final_tool = registry.get_tool("final_frame_tool")
            params = {"video_url": video_url, "to_base64": False}
            try:
                if scene_no is not None:
                    params["scene_number"] = int(scene_no)
            except Exception:
                pass
            resp = await final_tool.execute(TI(action="extract_final_frame_from_video", parameters=params))
            payload = getattr(resp, 'result', resp)
            path = None
            if isinstance(payload, dict):
                path = payload.get("path") or payload.get("image_path") or None
            if not path:
                return None
            return await self._ensure_remote_image_url(path)
        except Exception as e:
            try:
                self.logger.warning(f"emit_last_frame internal failed: {e}")
            except Exception:
                pass
            return None

    async def _ensure_remote_image_url(self, image_input: str) -> str:
        """将本地路径或data-url转换为可公开访问的URL（通过已注册的OSS工具）。"""
        try:
            from ..tool_registry import get_tool_registry
            from ..base_tool import ToolInput
            registry = get_tool_registry()
            oss_tool = registry.get_tool("oss_storage")
            remote_root = getattr(settings, 'OSS_IMAGE_DIR', 'images').strip('/')
            staging_dir = getattr(settings, 'OSS_STAGING_DIR', 'staging').strip('/')
            prefix = getattr(settings, 'OSS_VIDEO_INPUT_PREFIX', 'video_generation_input')
            import time
            remote_path = f"{remote_root}/{staging_dir}/{prefix}_{int(time.time()*1000)}.jpg"
            params: Dict[str, Any] = {"remote_path": remote_path, "public_read": True, "content_type": "image/jpeg"}
            if image_input.startswith("data:image"):
                header, b64 = image_input.split(",", 1)
                import base64
                params["content"] = base64.b64decode(b64)
            else:
                params["local_path"] = image_input
            res = await oss_tool.execute(ToolInput(action="upload", parameters=params))
            payload = getattr(res, 'result', res)
            if isinstance(payload, dict) and payload.get("url"):
                return payload["url"]
            raise RuntimeError("OSS storage did not return url")
        except Exception as e:
            raise RuntimeError(str(e))
    
    async def _get_capabilities(self) -> Dict[str, Any]:
        """获取视频生成能力信息"""
        provider_config = self.video_config.get_current_provider_config()
        supported_models: List[str] = []
        provider_model = provider_config.model_name.strip() if isinstance(provider_config.model_name, str) else ""
        if provider_model:
            supported_models.append(provider_model)
        if self.video_service and hasattr(self.video_service, "get_supported_models"):
            try:
                service_models = self.video_service.get_supported_models()
                if isinstance(service_models, list) and service_models:
                    dedup: List[str] = []
                    seen = set()
                    for item in service_models:
                        if not isinstance(item, str):
                            continue
                        model = item.strip()
                        if not model or model in seen:
                            continue
                        seen.add(model)
                        dedup.append(model)
                    if dedup:
                        supported_models = dedup
            except Exception:
                pass
        if provider_model and provider_model not in supported_models:
            supported_models.append(provider_model)

        audio_capability = {
            "supports_native_audio": bool(getattr(provider_config, "supports_native_audio", False)),
            "native_audio_param_name": str(getattr(provider_config, "native_audio_param_name", "generate_audio") or "generate_audio"),
            "native_audio_default_enabled": getattr(provider_config, "native_audio_default_enabled", None),
            "audio_strategy": self._normalize_audio_strategy(getattr(settings, "VIDEO_AUDIO_STRATEGY", "adaptive")),
        }

        return {
            "provider": provider_config.provider_name,
            "supported_models": supported_models,
            "duration_options": provider_config.duration_capabilities,
            "max_duration": provider_config.max_duration,
            "default_duration": provider_config.default_duration,
            "supports_first_last_frame": provider_config.supports_first_last_frame,
            "resolution_options": provider_config.resolution_options,
            "frame_rate_options": provider_config.frame_rate_options,
            "audio_capability": audio_capability,
            "amplification_ratio": provider_config.amplification_ratio,
            "system_capability": self.video_config.get_system_duration_capability()
        }
    
    def _determine_generation_mode(
        self, 
        image_url: str, 
        first_frame: str, 
        last_frame: str
    ) -> str:
        """确定生成模式"""
        if first_frame and last_frame:
            return "first_last_frame"
        elif image_url:
            return "image_to_video"
        else:
            return "text_to_video"
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "generate_video":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for generate_video")
            
            duration = parameters.get("duration")
            if duration is None:
                raise ToolValidationError("duration is required for generate_video")
            
            # 验证duration是否在支持范围内
            provider_config = self.video_config.get_current_provider_config()
            if duration not in provider_config.duration_capabilities:
                raise ToolValidationError(
                    f"duration must be one of {provider_config.duration_capabilities}, got {duration}"
                )
            # 边界约束：只接受云端URL
            iu = parameters.get("image_url")
            if iu is not None:
                if not isinstance(iu, str) or iu.startswith("data:") or not (iu.startswith("http://") or iu.startswith("https://")):
                    raise ToolValidationError("image_url must be http/https cloud URL (no local path/base64)")

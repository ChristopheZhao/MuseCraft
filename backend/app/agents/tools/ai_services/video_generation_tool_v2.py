"""
视频生成工具 - 纯粹的执行器，不包含决策逻辑
"""

from typing import Dict, Any, List, Optional
import logging

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .service_interfaces import get_video_service
from ....core.video_config_manager import get_video_config
from ....core.config import settings


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

    def get_action_stage(self, action: str) -> str:
        """声明动作阶段：生成类为 act，查询类为 plan。"""
        if action in ("generate_video", "generate_with_continuity"):
            return "act"
        return "plan"
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        # 获取当前提供商配置用于动态schema
        provider_config = self.video_config.get_current_provider_config()
        
        resolution_enum: List[str] = []
        try:
            base_resolutions = list(provider_config.resolution_options or [])
            resolution_enum = list(base_resolutions)
            alias_candidates = {
                "480p": "720x480",
                "720p": "1280x720",
                "1080p": "1920x1080"
            }
            for alias, canonical in alias_candidates.items():
                if canonical in base_resolutions and alias not in resolution_enum:
                    resolution_enum.append(alias)
        except Exception:
            resolution_enum = []
        resolution_schema: Dict[str, Any] = {
            "type": "string",
            "description": "可选：视频分辨率（如720p/1080p），影响画质与成本"
        }
        if resolution_enum:
            resolution_schema["enum"] = resolution_enum
        resolution_alias_schema: Dict[str, Any] = dict(resolution_schema)
        resolution_alias_schema["description"] = "可选：分辨率简写（rs），含义同resolution"
        schemas = {
            "generate_video": {
                "type": "object",
                "properties": {
                    "scene_number": {
                        "type": ["integer", "string"],
                        "description": "可选：仅用于管道追踪，不影响生成API"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "视频生成提示词，描述期望的视频内容和动作"
                    },
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
                "required": ["prompt", "duration"]
            },
            "generate_with_continuity": {
                "type": "object",
                "properties": {
                    "scene_number": {"type": ["integer", "string"], "description": "可选：用于管道追踪与尾帧登记"},
                    "emit_last_frame": {"type": "string", "enum": ["auto", "always", "never"], "description": "生成成功后是否自动提取并上传尾帧（auto按DAG出边判断）"},
                    "workflow_state_id": {"type": "string", "description": "可选：在auto模式下用于出边计算"},
                    "prompt": {"type": "string", "description": "视频生成提示词"},
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

        prompt = params["prompt"]
        # 合并结构化角色/风格/负向约束为提示词附加段（供应商无关、集中处理）
        try:
            char_cons = params.get("character_constraints") or []
            char_struct = params.get("character_constraints_struct") or []
            style_cons = params.get("style_constraints") or []
            neg_cons = params.get("negative_constraints") or []
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
            # 风格约束（优先使用 FC 提供）
            if isinstance(style_cons, list) and style_cons:
                extra.append("风格指导：" + "；".join([str(x) for x in style_cons if isinstance(x, str) and x.strip()]))
            else:
                # 软兜底（非侵入）：FC 未提供风格、且当前缺少强视觉锚点（T2V场景）时，基于WF概念计划提炼极简风格短语
                try:
                    has_continuity = bool(params.get("continuity_frame"))
                    has_image = bool(params.get("image_url"))
                    wf_id_fb = params.get("workflow_state_id")
                    if (not has_continuity) and (not has_image) and wf_id_fb:
                        from ....core.workflow_state import workflow_manager
                        wf_fb = workflow_manager.get_workflow(wf_id_fb)
                        fb_styles: list = []
                        if wf_fb:
                            # 优先 concept_plan.intelligent_style_design；回退 WorkflowState.intelligent_style_design
                            isd = {}
                            try:
                                cp = getattr(wf_fb, 'concept_plan', {}) or {}
                                if isinstance(cp, dict):
                                    isd = cp.get('intelligent_style_design') or {}
                            except Exception:
                                isd = {}
                            if not isd:
                                try:
                                    isd = getattr(wf_fb, 'intelligent_style_design', {}) or {}
                                except Exception:
                                    isd = {}
                            if isinstance(isd, dict) and isd:
                                # 提取关键信息，去重去空，限制长度
                                cand = []
                                for k in ("visual_approach", "narrative_style", "production_taste", "emotional_tone", "style_name"):
                                    v = isd.get(k)
                                    if isinstance(v, str) and v.strip():
                                        cand.append(v.strip())
                                # 合成 1-2 条紧凑短语
                                if cand:
                                    line = "，".join(cand)
                                    if len(line) > 120:
                                        line = line[:120]
                                    fb_styles = [line]
                        if fb_styles:
                            params["style_constraints"] = fb_styles
                            extra.append("风格指导：" + "；".join(fb_styles))
                            try:
                                self.logger.info(
                                    f"STYLE_INJECT(generate_video): styles={len(fb_styles)} source=fallback reasons=no_fc_style+t2v"
                                )
                            except Exception:
                                pass
                except Exception:
                    pass
            # 负向约束
            if isinstance(neg_cons, list) and neg_cons:
                extra.append("避免：" + "；".join([str(x) for x in neg_cons if isinstance(x, str) and x.strip()]))
            # 合并追加段
            if extra:
                try:
                    self.logger.info(f"CHAR_INJECT(generate_video): chars={len(char_cons or [])} neg={len(neg_cons or [])}")
                    if char_struct:
                        self.logger.info(f"CHAR_INJECT_STRUCT(generate_video): items={len(char_struct or [])}")
                    if style_cons:
                        self.logger.info(f"STYLE_INJECT(generate_video): styles={len(style_cons or [])} source=fc")
                except Exception:
                    pass
                prompt = (prompt + "\n" + "\n".join(extra)) if prompt else "\n".join(extra)
                params["prompt"] = prompt
        except Exception:
            pass
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
                allowed_resolutions = list(provider_config.resolution_options or [])
                alias_candidates = {
                    "480p": "720x480",
                    "720p": "1280x720",
                    "1080p": "1920x1080"
                }
                alias_map = {
                    alias: canonical
                    for alias, canonical in alias_candidates.items()
                    if canonical in allowed_resolutions
                }
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
            result = await self.video_service.generate_video(
                prompt=prompt,
                model=model,
                duration=duration,
                image_url=final_image_input,
                first_frame_image=first_frame_image,
                last_frame_image=last_frame_image,
                resolution=resolution_applied or params.get("resolution")
            )
            
            # 增强返回结果
            result.update({
                "tool_used": self.metadata.name,
                "requested_resolution": resolution_requested,
                "applied_resolution": resolution_applied or params.get("resolution"),
                "execution_params": {
                    "prompt": prompt,
                    "duration": duration,
                    "model": model,
                    "resolution_requested": resolution_requested,
                    "resolution_applied": resolution_applied or params.get("resolution"),
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
            # 工具层最小验证：必须产生可访问 video_url，否则标记为失败并将 fallback_reason 透传为 error_type
            if not isinstance(result, dict) or not result.get('video_url'):
                status = (result or {}).get('status') if isinstance(result, dict) else None
                fb_reason = (result or {}).get('fallback_reason') if isinstance(result, dict) else None
                mdl = (result or {}).get('model') if isinstance(result, dict) else model
                err_type = str(fb_reason or (status or 'no_video_url'))
                # 使用 ToolError 的 error_code 让上层拿到明确错误类型（如 provider_timeout）
                raise ToolError(
                    message=f"video generation returned no url (status={status}, model={mdl}, fallback_reason={fb_reason})",
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
                    raise ToolError(f"Video generation failed: {str(e)}", self.metadata.name)
            # 非 image_url 类问题或重试失败：按原样抛出
            self.logger.error(f"Video generation failed: {str(e)}")
            raise ToolError(f"Video generation failed: {str(e)}", self.metadata.name)

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

    async def _generate_with_continuity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """合并连续性准备与生成（确定性）：解析上一场景尾帧 → 生成 → 可选存尾帧。"""
        prompt = params.get("prompt")
        # 合并结构化角色/负向约束
        try:
            char_cons = params.get("character_constraints") or []
            neg_cons = params.get("negative_constraints") or []
            extra = []
            if isinstance(char_cons, list) and char_cons:
                if not (isinstance(prompt, str) and ("角色设定" in prompt)):
                    extra.append("角色设定：" + "；".join([str(x) for x in char_cons if isinstance(x, str) and x.strip()]))
            if isinstance(neg_cons, list) and neg_cons:
                extra.append("避免：" + "；".join([str(x) for x in neg_cons if isinstance(x, str) and x.strip()]))
            if extra:
                try:
                    self.logger.info(f"CHAR_INJECT(generate_with_continuity): chars={len(char_cons or [])} neg={len(neg_cons or [])}")
                except Exception:
                    pass
                prompt = (prompt + "\n" + "\n".join(extra)) if prompt else "\n".join(extra)
                params["prompt"] = prompt
        except Exception:
            pass
        duration = params.get("duration")
        if not prompt or duration is None:
            raise ToolValidationError("prompt and duration are required", self.metadata.name)

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

        # 解析连续性帧：优先 continuity_frame > image_url > 内存/WF尾帧 > 上游视频抽帧
        continuity_frame: Optional[str] = params.get("continuity_frame")
        image_url: Optional[str] = params.get("image_url")

        prev_scene_no: Optional[int] = None
        try:
            dp = params.get("depends_on_scene")
            if isinstance(dp, (int, str)) and str(dp).isdigit():
                prev_scene_no = int(dp)
            if prev_scene_no is None:
                wf_id = params.get("workflow_state_id")
                if wf_id:
                    from ....core.workflow_state import workflow_manager
                    wf = workflow_manager.get_workflow(wf_id)
                    sn = params.get("scene_number")
                    sn = int(sn) if sn is not None and str(sn).isdigit() else None
                    if wf and sn is not None:
                        sc = wf.get_scene(sn)
                        if sc is not None:
                            dp2 = getattr(sc, 'depends_on_scene', None)
                            if isinstance(dp2, (int, str)) and str(dp2).isdigit():
                                prev_scene_no = int(dp2)
        except Exception:
            prev_scene_no = prev_scene_no or None

        if not continuity_frame and prev_scene_no is not None:
            # 1) 内存优先（URL更优）
            try:
                from ..tool_registry import get_tool_registry
                from ..base_tool import ToolInput as TI
                registry = get_tool_registry()
                final_tool = registry.get_tool("final_frame_tool")
                resp_mem = await final_tool.execute(TI(action="get_final_frame_from_memory", parameters={"scene_number": prev_scene_no, "prefer_url": True}))
                pay_mem = getattr(resp_mem, 'result', resp_mem)
                if isinstance(pay_mem, dict):
                    url = pay_mem.get("url") or pay_mem.get("data_url")
                    if isinstance(url, str) and url.startswith("http"):
                        continuity_frame = url
            except Exception:
                pass
            # 2) WF 尾帧字段
            if not continuity_frame:
                try:
                    wf_id = params.get("workflow_state_id")
                    if wf_id:
                        from ....core.workflow_state import workflow_manager
                        wf = workflow_manager.get_workflow(wf_id)
                        sc_prev = wf.get_scene(prev_scene_no) if wf else None
                        lf = getattr(sc_prev, 'last_frame_url', '') if sc_prev else ''
                        if isinstance(lf, str) and lf.startswith("http"):
                            continuity_frame = lf
                except Exception:
                    pass
            # 3) 上游视频抽帧（参数 > WF）
            if not continuity_frame:
                prev_url = params.get("previous_video_url")
                if not prev_url:
                    try:
                        wf_id = params.get("workflow_state_id")
                        if wf_id:
                            from ....core.workflow_state import workflow_manager
                            wf = workflow_manager.get_workflow(wf_id)
                            sc_prev = wf.get_scene(prev_scene_no) if wf else None
                            prev_url = getattr(sc_prev, 'video_url', '') or getattr(sc_prev, 'video_path', '') if sc_prev else ''
                    except Exception:
                        prev_url = None
                if prev_url:
                    try:
                        from ..tool_registry import get_tool_registry
                        from ..base_tool import ToolInput as TI
                        registry = get_tool_registry()
                        final_tool = registry.get_tool("final_frame_tool")
                        ff_params = {"video_url": prev_url, "to_base64": False}
                        try:
                            if prev_scene_no is not None:
                                ff_params["scene_number"] = int(prev_scene_no)
                        except Exception:
                            pass
                        resp = await final_tool.execute(TI(action="extract_final_frame_from_video", parameters=ff_params))
                        payload = getattr(resp, 'result', resp)
                        if isinstance(payload, dict):
                            continuity_frame = payload.get("path") or payload.get("data_url")
                    except Exception as e:
                        try:
                            self.logger.warning(f"continuity frame extraction failed: {e}")
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
            else:
                # 软兜底触发条件：无FC风格 + 无连续性帧 + 无参考图（T2V）
                try:
                    no_cont = not bool(continuity_frame)
                    no_img = not bool(params.get("image_url"))
                    wf_id_fb = params.get("workflow_state_id")
                    if no_cont and no_img and wf_id_fb:
                        from ....core.workflow_state import workflow_manager
                        wf_fb = workflow_manager.get_workflow(wf_id_fb)
                        fb_styles: list = []
                        if wf_fb:
                            isd = {}
                            try:
                                cp = getattr(wf_fb, 'concept_plan', {}) or {}
                                if isinstance(cp, dict):
                                    isd = cp.get('intelligent_style_design') or {}
                            except Exception:
                                isd = {}
                            if not isd:
                                try:
                                    isd = getattr(wf_fb, 'intelligent_style_design', {}) or {}
                                except Exception:
                                    isd = {}
                            if isinstance(isd, dict) and isd:
                                cand = []
                                for k in ("visual_approach", "narrative_style", "production_taste", "emotional_tone", "style_name"):
                                    v = isd.get(k)
                                    if isinstance(v, str) and v.strip():
                                        cand.append(v.strip())
                                if cand:
                                    line = "，".join(cand)
                                    if len(line) > 120:
                                        line = line[:120]
                                    fb_styles = [line]
                        if fb_styles:
                            params["style_constraints"] = fb_styles
                            next_params["style_constraints"] = fb_styles
                            self.logger.info(
                                f"STYLE_INJECT(generate_with_continuity): styles={len(fb_styles)} source=fallback reasons=no_fc_style+t2v"
                            )
                except Exception:
                    pass
        except Exception:
            pass
        gen_res = await self._generate_video(next_params)

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
                        wf_id = params.get("workflow_state_id")
                        if wf_id and scene_no is not None:
                            from ....core.workflow_state import workflow_manager
                            wf = workflow_manager.get_workflow(wf_id)
                            if wf:
                                wf.update_scene(scene_no, last_frame_url=last_url)
                    except Exception:
                        pass
                    cont = dict(gen_res.get("continuity", {}) or {})
                    cont.update({"last_frame_url": last_url})
                    gen_res["continuity"] = cont
        except Exception as e:
            try:
                self.logger.warning(f"emit_last_frame failed (soft): {e}")
            except Exception:
                pass
        return gen_res

    def _get_outdegree_from_wf_or_active(self, wf_id: Optional[str], scene_no: int) -> int:
        try:
            from ....core.workflow_state import workflow_manager
            workflows = []
            if wf_id:
                wf = workflow_manager.get_workflow(wf_id)
                if wf:
                    workflows.append(wf)
            if not workflows:
                workflows.extend(workflow_manager.get_active_workflows())
            outdeg = 0
            for wf in workflows:
                try:
                    for sc in getattr(wf, 'scenes', []) or []:
                        dep = getattr(sc, 'depends_on_scene', None)
                        if dep is not None and int(dep) == int(scene_no):
                            outdeg += 1
                    if outdeg > 0:
                        break
                except Exception:
                    continue
            return outdeg
        except Exception:
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
        
        return {
            "provider": provider_config.provider_name,
            "supported_models": [provider_config.model_name],
            "duration_options": provider_config.duration_capabilities,
            "max_duration": provider_config.max_duration,
            "default_duration": provider_config.default_duration,
            "supports_first_last_frame": provider_config.supports_first_last_frame,
            "resolution_options": provider_config.resolution_options,
            "frame_rate_options": provider_config.frame_rate_options,
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

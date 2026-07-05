"""
Image Generation Tool - 封装图像生成业务逻辑
"""

import asyncio
import json
import os
import re
import tempfile
from typing import Dict, Any, List, Optional

import httpx

from ....core.config import settings
from ....core.consistency_policy import get_consistency_policy

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolError
from .service_interfaces import get_vlm_service, get_vlm_capabilities
from ....services.prompt_safety import (
    apply_prompt_safety,
    SafetyContext,
    sanitize_with_locks,
)
from ....services.prompt_safety.rewrite import (
    is_sensitive_error as ps_is_sensitive_error,
    rewrite_prompt_preserving_locks as ps_rewrite_preserving_locks,
)


class ImageGenerationTool(AsyncTool):
    """
    图像生成工具 - 封装图像生成业务逻辑
    
    基于ZhipuClientTool，提供图像生成相关的业务功能
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="image_generation",
            version="1.0.0",
            description="使用AI服务生成图像，包括场景图像、视觉风格分析等",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["图像生成", "视觉分析", "AI图像"],
            capabilities=["图像生成", "图像风格分析", "提示词优化", "视觉特征提取"],
            dependencies=["zhipu_client"]
        )
    
    def __init__(self, **kwargs):
        # 从kwargs中移除metadata，使用classmethod获取
        kwargs.pop('metadata', None)
        metadata = self.get_metadata()
        super().__init__(metadata=metadata, **kwargs)
        self._vlm_service = None
    
    def get_available_actions(self) -> List[str]:
        return [
            "generate_image",
            "analyze_image_style",
            "extract_visual_features",
        ]
    
    def _initialize(self):
        """初始化工具"""
        pass

    def get_fc_visibility(self) -> Dict[str, Any]:
        """为业务级图像工具提供默认的 FC 暴露策略"""
        return {
            "expose": True,
            "allowed_actions": ["generate_image"]
        }
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """获取指定操作的参数架构"""
        base_schema = {
            "type": "object",
            "properties": {},
        }
        
        if action == "generate_image":
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "可选：用于对齐多场景批处理的标识"
                },
                "prompt": {
                    "type": "string",
                    "description": "图像生成提示词"
                },
                "style": {
                    "type": "string",
                    "description": "图像风格（例如 写实、艺术、电影感 等）"
                },
                "size": self._build_size_schema_property("图像尺寸；若不提供则由当前 provider 能力自动选择默认值"),
                "persist": {
                    "type": "boolean",
                    "description": "可选：将生成结果持久化到文件存储/OSS（若可用）并返回可访问 URL"
                },
                "destination_key": {
                    "type": "string",
                    "description": "可选：持久化时使用的目标路径/键名（例如 projects/<id>/characters/<cid>/avatar.jpg）"
                }
            }
            reference_schema = self._build_reference_image_schema_properties()
            if reference_schema:
                base_schema["properties"].update(reference_schema)
            base_schema["required"] = ["prompt"]
            base_schema["description"] = "根据用户提供的提示词直接生成图像，可选指定尺寸以及风格。"

        elif action == "analyze_image_style":
            base_schema["properties"] = {
                "image_url": {
                    "type": "string",
                    "description": "图像 URL"
                },
                "image_path": {
                    "type": "string", 
                    "description": "图像本地路径"
                }
            }
            base_schema["description"] = "分析指定图像的风格特征信息。"
            
        elif action == "extract_visual_features":
            base_schema["properties"] = {
                "image_url": {
                    "type": "string",
                    "description": "图像 URL"
                },
                "image_path": {
                    "type": "string",
                    "description": "图像本地路径"
                }
            }
            base_schema["description"] = "提取图像的视觉特征向量等信息。"
        
        return base_schema

    def _build_size_schema_property(self, description: str) -> Dict[str, Any]:
        prop: Dict[str, Any] = {
            "type": "string",
            "description": description,
        }
        try:
            caps = get_vlm_capabilities()
            size_cap = caps.size if caps else None
            if size_cap and size_cap.options:
                prop["enum"] = list(size_cap.options)
                notes: List[str] = []
                if size_cap.description_suffix:
                    notes.append(size_cap.description_suffix)
                if size_cap.note:
                    notes.append(size_cap.note)
                if notes:
                    prop["description"] = f"{description} {' '.join(notes)}"
        except Exception:
            pass
        return prop

    def _get_reference_image_capability(self):
        try:
            service = self._vlm_service
            if service is not None and hasattr(service, "get_capabilities"):
                caps = service.get_capabilities()
            else:
                caps = get_vlm_capabilities()
        except Exception:
            caps = None
        capability = getattr(caps, "reference_image", None) if caps else None
        if capability is not None and bool(getattr(capability, "supported", False)):
            return capability
        return None

    def _build_reference_image_schema_properties(self) -> Dict[str, Any]:
        capability = self._get_reference_image_capability()
        if capability is None:
            return {}
        notes: List[str] = []
        if getattr(capability, "description_suffix", None):
            notes.append(str(capability.description_suffix))
        if getattr(capability, "note", None):
            notes.append(str(capability.note))
        description = "可选：参考图像 URL，仅当当前 provider schema 声明支持时可用"
        if notes:
            description = f"{description} {' '.join(notes)}"
        return {
            "reference_image_url": {
                "type": "string",
                "description": description,
            }
        }

    def _validate_reference_image_request(self, reference_image_url: str) -> Optional[Dict[str, Any]]:
        reference_image_url = str(reference_image_url or "").strip()
        if not reference_image_url:
            return None
        capability = self._get_reference_image_capability()
        if capability is None:
            provider_name = "unknown"
            try:
                service = self._get_active_vlm_service()
                if hasattr(service, "get_provider_name"):
                    provider_name = service.get_provider_name() or provider_name
            except Exception:
                pass
            raise ToolError(
                (
                    "Image reference input is not supported by the active provider "
                    f"capability schema: provider={provider_name}"
                ),
                tool_name=self.metadata.name,
                error_code="image_reference_capability_missing",
                details={
                    "provider": provider_name,
                    "reference_image_requested": True,
                    "capability": "unsupported_or_missing",
                },
            )
        return {
            "reference_image_url": reference_image_url,
            "capability": capability.to_metadata()
            if hasattr(capability, "to_metadata")
            else {"supported": True},
        }

    def _get_active_vlm_service(self):
        if not self._vlm_service:
            self._vlm_service = get_vlm_service()
        return self._vlm_service

    def _normalize_image_size(self, requested_size: Any) -> str:
        service = self._get_active_vlm_service()
        provider_name = "unknown"
        try:
            provider_name = service.get_provider_name() or provider_name
        except Exception:
            pass

        caps = None
        if hasattr(service, "get_capabilities"):
            try:
                caps = service.get_capabilities()
            except Exception:
                caps = None
        if caps is None:
            try:
                caps = get_vlm_capabilities()
            except Exception:
                caps = None

        size_cap = caps.size if caps and getattr(caps, "size", None) else None
        requested = str(requested_size).strip() if requested_size is not None else ""

        if size_cap:
            if requested:
                normalized = size_cap.resolve(requested)
                if normalized:
                    return normalized
            else:
                default_size = size_cap.default_option()
                if default_size:
                    return default_size

            raise ToolError(
                (
                    f"Unsupported image size for provider '{provider_name}': "
                    f"requested={requested or '<missing>'}, allowed={list(size_cap.options or [])}"
                ),
                tool_name=self.metadata.name,
                error_code="invalid_image_size",
                details={
                    "provider": provider_name,
                    "requested_size": requested or None,
                    "allowed_sizes": list(size_cap.options or []),
                    "accepted_inputs": size_cap.expand_enum(),
                },
            )

        raise ToolError(
            f"Image size capability is unavailable for provider '{provider_name}'",
            tool_name=self.metadata.name,
            error_code="image_size_capability_missing",
            details={
                "provider": provider_name,
                "requested_size": requested or None,
            },
        )

    @staticmethod
    def _clip_text(value: Any, max_len: int = 240) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        if max_len <= 3:
            return text[:max_len]
        return text[: max_len - 3] + "..."

    def _extract_provider_error_details(
        self,
        exc: Exception,
        *,
        provider_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        message = str(exc or "").strip()
        details: Dict[str, Any] = {
            "provider": (provider_name or "").strip(),
            "provider_exception_type": type(exc).__name__,
            "provider_raw_message": self._clip_text(message, 800),
        }
        if isinstance(exc, ToolError):
            existing = getattr(exc, "details", None)
            if isinstance(existing, dict):
                details.update(existing)
            if getattr(exc, "error_code", None):
                details.setdefault("provider_error_code", str(exc.error_code))
            return details

        status_match = re.search(r"failed:\s*(\d+)", message)
        if status_match:
            try:
                details["provider_status_code"] = int(status_match.group(1))
            except Exception:
                pass

        json_start = message.find("{")
        if json_start >= 0:
            response_text = message[json_start:].strip()
            details["provider_response_text"] = self._clip_text(response_text, 800)
            try:
                payload = json.loads(response_text)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                err_payload = payload.get("error")
                if isinstance(err_payload, dict):
                    code = err_payload.get("code")
                    if code is not None:
                        details["provider_error_code"] = str(code)
                    err_msg = err_payload.get("message")
                    if err_msg is not None:
                        details["provider_error_message"] = self._clip_text(err_msg, 400)
                    err_param = err_payload.get("param")
                    if err_param is not None:
                        details["provider_error_param"] = str(err_param)

        if "provider_error_message" not in details and message:
            details["provider_error_message"] = self._clip_text(message, 400)
        return details

    def _normalize_generation_exception(
        self,
        exc: Exception,
        *,
        provider_name: Optional[str] = None,
        scene_number: Any = None,
        extra_details: Optional[Dict[str, Any]] = None,
    ) -> ToolError:
        if isinstance(exc, ToolError):
            if extra_details:
                merged = dict(getattr(exc, "details", None) or {})
                merged.update(extra_details)
                exc.details = merged
            return exc

        details = self._extract_provider_error_details(exc, provider_name=provider_name)
        if scene_number is not None:
            details["scene_number"] = scene_number
        if extra_details:
            details.update(extra_details)

        provider_message = details.get("provider_error_message") or str(exc)
        return ToolError(
            f"图像生成异常: {provider_message}",
            tool_name=self.metadata.name,
            error_code="image_generation_failed",
            details=details,
        )

    # 取消阶段语义：工具仅具有执行属性
    
    async def _execute_impl(self, tool_input) -> Dict[str, Any]:
        """执行图像生成相关操作"""
        
        action = tool_input.action
        parameters = tool_input.parameters
        
        if action == "generate_image":
            return await self._generate_image(parameters)
        elif action in {"gen_image_prompt", "generate_with_autoprompt"}:
            raise ToolError(
                "autoprompt actions were removed from image_generation; use image_prompt_composer.generate",
                tool_name=self.metadata.name,
                error_code="action_removed",
            )
        elif action == "analyze_image_style":
            return await self._analyze_image_style(parameters)
        elif action == "extract_visual_features":
            return await self._extract_visual_features(parameters)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _generate_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成图像"""
        
        prompt = (params.get("prompt", "") or "").strip()
        # 风格改为“按需透传”：无则不默认，避免硬编码偏置
        style = (params.get("style") or "").strip()
        size = self._normalize_image_size(params.get("size"))
        persist = bool(params.get("persist", False))
        destination_key = (params.get("destination_key") or "").strip()
        scene_number = params.get("scene_number")
        reference_image_url = str(params.get("reference_image_url") or "").strip()
        reference_request = self._validate_reference_image_request(reference_image_url)

        async def _maybe_persist(image_url: str) -> str:
            if not persist:
                return image_url
            if not image_url:
                return image_url

            dest_key = destination_key
            if not dest_key:
                safe_scene = str(scene_number) if scene_number is not None else "image"
                safe_scene = safe_scene.replace("/", "_").replace("\\", "_").replace(" ", "_")
                dest_key = f"images/scene_{safe_scene}_image.jpg"

            hosted_url = ""
            try:
                from ..tool_registry import get_tool_registry
                from ..base_tool import ToolInput as TI

                storage = get_tool_registry().get_tool("file_storage_tool")
                res = await storage.execute(
                    TI(
                        action="upload_from_url",
                        parameters={
                            "url": image_url,
                            "destination_key": dest_key,
                            "metadata": {"scene_number": scene_number, "source": "generate_image"},
                            "public": True,
                        },
                    )
                )
                payload = getattr(res, "result", res)
                if isinstance(payload, dict):
                    candidate = payload.get("url")
                    if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                        hosted_url = candidate
            except Exception:
                hosted_url = ""

            if not hosted_url:
                try:
                    oss_url = await self._mirror_image_url_to_oss(
                        image_url,
                        dest_key,
                        metadata={"scene_number": scene_number, "source": "generate_image", "original_url": image_url},
                    )
                    if isinstance(oss_url, str) and oss_url.startswith(("http://", "https://")):
                        hosted_url = oss_url
                except Exception:
                    hosted_url = ""

            if hosted_url:
                try:
                    self.logger.info("IMAGE_REHOST_RESULT(scene=%s) url=%s", scene_number, hosted_url)
                except Exception:
                    pass
                return hosted_url
            return image_url

        # 轻量提示词质量校验
        if self._is_prompt_weak(prompt):
            raise ToolError(
                "PROMPT_TOO_WEAK: 缺少或过短的图像生成提示词",
                error_code="prompt_too_weak",
            )
        
        advisor_meta: Dict[str, Any] = {}
        provider_name = None
        try:
            # 通过供应商无关的服务接口生成图像（当前默认Zhipu实现）
            self._get_active_vlm_service()

            if self._vlm_service and hasattr(self._vlm_service, "get_provider_name"):
                try:
                    provider_name = self._vlm_service.get_provider_name()
                except Exception:
                    provider_name = None

            safe_prompt, advice = apply_prompt_safety(
                prompt,
                SafetyContext(
                    modality="image",
                    provider=provider_name,
                    language="zh",
                    metadata={
                        "action": "generate_image",
                        "scene_number": params.get("scene_number"),
                    },
                ),
            )
            advisor_meta = advice.metadata
            # 锁定片段（可选）：若上层传入 consistency_locks/locked_segments，则在 sanitize 时保持不变
            try:
                locks = params.get("locked_segments") or params.get("consistency_locks")
                if not isinstance(locks, list):
                    locks = []
            except Exception:
                locks = []
            sanitized = sanitize_with_locks(
                safe_prompt,
                locks,
                {
                    "modality": "image",
                    "scene_number": params.get("scene_number"),
                    "tool": self.metadata.name,
                    "advisor_layers": advisor_meta.get("applied_layers"),
                },
            )
            prompt = sanitized.text or safe_prompt
            advisor_meta["sanitized_changed"] = sanitized.changed
            advisor_meta["sanitized_matches"] = sanitized.matches

            # 构造最小必需参数；仅当上层明确提供 style/quality 时才透传
            gen_args = {"prompt": prompt, "size": size}
            if style:
                gen_args["style"] = style
            if params.get("quality"):
                gen_args["quality"] = params["quality"]
            if reference_request:
                gen_args["reference_image_url"] = reference_request["reference_image_url"]
            # 调试期保留组合提示词日志
            try:
                prompt_bytes_len = len(prompt.encode("utf-8")) if isinstance(prompt, str) else 0
                self.logger.info(
                    "PROMPT_COMBINED(generate_image): len=%d bytes text=%s",
                    prompt_bytes_len,
                    prompt,
                )
            except Exception:
                pass

            try:
                res = await self._vlm_service.image_generation(**gen_args)
                image_url = res.get("image_url") or res.get("url") or ""
                if not image_url:
                    # 统一抛错，让下方敏感处理或上层 ReAct 接手
                    raise ToolError("image_generation returned no image_url", self.metadata.name)
                image_url = await _maybe_persist(image_url)
                return {
                    "image_url": image_url,
                    "generated_prompt": prompt,
                    "style": style,
                    "size": size,
                    "generation_metadata": res,
                    "prompt_safety": advisor_meta,
                    "reference_image": {
                        "applied": bool(reference_request),
                        "capability": reference_request.get("capability") if reference_request else None,
                    },
                }
            except Exception as exc:
                terr = self._normalize_generation_exception(
                    exc,
                    provider_name=provider_name,
                    scene_number=params.get("scene_number"),
                )
                # 仅当供应商明确返回“敏感/违规”错误时，触发一次轻量重写
                try:
                    policy = get_consistency_policy()
                    ps_cfg = getattr(policy, "prompt_safety", None)
                    enable_rewrite = bool(getattr(ps_cfg, "enable_rewrite_on_sensitive_error", False))
                except Exception:
                    ps_cfg = None
                    enable_rewrite = False

                if enable_rewrite and ps_is_sensitive_error(terr):
                    locked_segments = []
                    # 支持可选锁定片段透传：params["locked_segments"] 或 params["consistency_locks"]
                    try:
                        cand = params.get("locked_segments") or params.get("consistency_locks") or []
                        if isinstance(cand, list):
                            locked_segments = [str(x).strip() for x in cand if str(x).strip()]
                    except Exception:
                        locked_segments = []

                    rewrite_model = getattr(ps_cfg, "rewrite_model", None)
                    rewritten, telemetry = await ps_rewrite_preserving_locks(
                        prompt,
                        locked_segments,
                        model=rewrite_model,
                        language="zh",
                        metadata={"action": "generate_image", "scene_number": params.get("scene_number"), "tool": self.metadata.name},
                    )
                    provider_code = (
                        (getattr(terr, "details", None) or {}).get("provider_error_code")
                        if isinstance(getattr(terr, "details", None), dict)
                        else None
                    )
                    rewrite_meta = {
                        "applied": bool(rewritten and rewritten.strip() and rewritten.strip() != prompt),
                        "reason": "sensitive_error",
                        "model": rewrite_model,
                        "provider_error_code": provider_code,
                        "telemetry": telemetry,
                    }
                    # 记录事件
                    try:
                        self.logger.info(
                            "prompt_rewrite(image): applied=%s reason=sensitive_error model=%s tokens=%s provider_code=%s result=%s",
                            rewrite_meta["applied"],
                            telemetry.get("model"),
                            telemetry.get("tokens"),
                            provider_code,
                            telemetry.get("result"),
                        )
                    except Exception:
                        pass

                    if rewritten and rewritten.strip() and rewritten.strip() != prompt:
                        prompt = rewritten.strip()
                        # 调试日志：重写后的组合提示词
                        try:
                            self.logger.info(
                                "PROMPT_COMBINED(generate_image:rewrite): len=%d bytes text=%s",
                                len(prompt.encode("utf-8")),
                                prompt,
                            )
                        except Exception:
                            pass
                        # 重试一次
                        gen_args_retry = dict(gen_args)
                        gen_args_retry["prompt"] = prompt
                        try:
                            res2 = await self._vlm_service.image_generation(**gen_args_retry)
                            image_url2 = res2.get("image_url") or res2.get("url") or ""
                            if not image_url2:
                                raise ToolError("image_generation returned no image_url", self.metadata.name)
                        except Exception as retry_exc:
                            raise self._normalize_generation_exception(
                                retry_exc,
                                provider_name=provider_name,
                                scene_number=params.get("scene_number"),
                                extra_details={
                                    "prompt_safety_rewrite": {
                                        **rewrite_meta,
                                        "retry_outcome": "failed",
                                    }
                                },
                            ) from retry_exc
                        image_url2 = await _maybe_persist(image_url2)
                        return {
                            "image_url": image_url2,
                            "generated_prompt": prompt,
                            "style": style,
                            "size": size,
                            "generation_metadata": res2,
                            "prompt_safety": advisor_meta,
                            "reference_image": {
                                "applied": bool(reference_request),
                                "capability": reference_request.get("capability") if reference_request else None,
                            },
                            "prompt_safety_rewrite": {
                                **rewrite_meta,
                                "retry_outcome": "success",
                            },
                        }
                    terr = self._normalize_generation_exception(
                        terr,
                        provider_name=provider_name,
                        scene_number=params.get("scene_number"),
                        extra_details={
                            "prompt_safety_rewrite": {
                                **rewrite_meta,
                                "retry_outcome": "not_retried",
                            }
                        },
                    )
                # 非敏感或关闭重写：交由下方 except 统一返回失败
                raise terr
        except ToolError:
            raise
        except Exception as e:
            raise self._normalize_generation_exception(
                e,
                provider_name=provider_name,
                scene_number=params.get("scene_number"),
            )
    
    async def _create_image_prompt_from_scene(
        self,
        scene_data: Dict[str, Any],
        style: str,
        style_guidance: Dict[str, Any] | None = None,
    ) -> str:
        raise ToolError(
            "prompt synthesis was removed from image_generation; use image_prompt_composer.generate",
            tool_name=self.metadata.name,
            error_code="action_removed",
        )

    async def _generate_with_autoprompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        raise ToolError(
            "autoprompt execution was removed from image_generation; use image_prompt_composer.generate",
            tool_name=self.metadata.name,
            error_code="action_removed",
        )

    async def _upload_local_image_to_oss(self, local_path: str, remote_path: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """将本地图片上传到 OSS，返回可公开访问的 URL。"""
        if not local_path or not os.path.exists(local_path):
            return None

        try:
            self.logger.info(
                "OSS_UPLOAD_DEBUG(local) local_path=%s remote_path=%s key_id=%s endpoint=%s bucket=%s",
                local_path,
                remote_path,
                getattr(settings, "OSS_ACCESS_KEY_ID", None),
                getattr(settings, "OSS_ENDPOINT", None),
                getattr(settings, "OSS_BUCKET_NAME", None),
            )
            from ..tool_registry import get_tool_registry
            from ..base_tool import ToolInput as TI

            registry = get_tool_registry()
            oss_tool = registry.get_tool("oss_storage")
            if not oss_tool:
                return None

            params = {
                "local_path": local_path,
                "remote_path": remote_path,
                "public_read": True,
                "overwrite": True,
                "metadata": metadata or {},
            }

            res = await oss_tool.execute(TI(action="upload", parameters=params))
            payload = getattr(res, 'result', res)
            if isinstance(payload, dict):
                url = payload.get("url")
                if url:
                    return url
                if payload.get("skipped") and payload.get("url"):
                    return payload.get("url")
        except Exception as exc:
            try:
                self.logger.warning(f"OSS upload failed for {local_path}: {exc}")
            except Exception:
                pass
        return None

    async def _mirror_image_url_to_oss(self, source_url: str, remote_path: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """当没有本地文件时，尝试将远端图片镜像到 OSS。"""
        if not source_url:
            return None

        temp_file = None
        try:
            self.logger.info(
                "OSS_UPLOAD_DEBUG(remote) source_url=%s remote_path=%s key_id=%s endpoint=%s bucket=%s",
                source_url,
                remote_path,
                getattr(settings, "OSS_ACCESS_KEY_ID", None),
                getattr(settings, "OSS_ENDPOINT", None),
                getattr(settings, "OSS_BUCKET_NAME", None),
            )
            timeout_seconds = 30
            try:
                from ....core.config import settings as _cfg
                timeout_seconds = int(getattr(_cfg, 'FILE_STORAGE_HTTP_TIMEOUT', timeout_seconds))
            except Exception:
                pass

            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.get(source_url)
                response.raise_for_status()
                suffix = os.path.splitext(remote_path)[1] or ".jpg"
                fd, temp_file = tempfile.mkstemp(suffix=suffix)
                with os.fdopen(fd, "wb") as tmp:
                    tmp.write(response.content)

            url = await self._upload_local_image_to_oss(temp_file, remote_path, metadata=metadata)
            return url
        except Exception as exc:
            try:
                self.logger.warning(f"OSS mirror failed for {source_url}: {exc}")
            except Exception:
                pass
            return None
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass
    
    async def _analyze_image_style(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """分析图像风格"""
        
        image_url = params.get("image_url", "")
        image_path = params.get("image_path", "")
        
        if not image_url and not image_path:
            raise ToolError("需要提供图像URL或路径", error_code="missing_image_input")
        
        # 构建分析提示
        analysis_prompt = """分析这张图像的视觉风格特征：

请提供：
1. 主要风格类型（写实、艺术、卡通等）
2. 色彩特征
3. 构图特点
4. 光影效果
5. 情绪氛围

返回JSON格式的分析结果。"""
        
        try:
            if not self._vlm_service:
                self._vlm_service = get_vlm_service()

            target_image = image_url or image_path
            res = await self._vlm_service.image_understanding(
                image_input=target_image,
                prompt=analysis_prompt,
                model=None,
                temperature=0.3
            )

            analysis_content = res.get("analysis", "")
            try:
                style_analysis = json.loads(analysis_content)
                return {"style_analysis": style_analysis}
            except json.JSONDecodeError:
                return {
                    "style_analysis": {
                        "description": analysis_content,
                        "style_type": "mixed",
                        "confidence": 0.7,
                    }
                }
                
        except Exception as e:
            raise ToolError(f"图像风格分析异常: {str(e)}", error_code="style_analysis_failed")

    async def _gen_image_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        raise ToolError(
            "prompt generation was removed from image_generation; use image_prompt_composer.generate",
            tool_name=self.metadata.name,
            error_code="action_removed",
        )

    def _is_prompt_weak(self, prompt: str) -> bool:
        """极轻量提示词质量判断（读取配置）"""
        cfg = getattr(settings, "IMAGE_TOOL_PROMPT_RULES", {}) or {}
        min_length = int(cfg.get("min_length", 30))
        allow_weak = bool(cfg.get("allow_weak_prompt", False))
        p = (prompt or "").strip()
        if allow_weak:
            return False
        if len(p) < min_length:
            return True
        weak_markers = cfg.get("weak_markers")
        if not isinstance(weak_markers, list):
            weak_markers = ["高质量", "高清", "精美", "好看", "震撼", "唯美", "超清", "逼真"]
        near_limit = int(cfg.get("weak_marker_length_threshold", 50))
        if len(p) < near_limit:
            hits = sum(1 for w in weak_markers if isinstance(w, str) and w and w in p)
            threshold = int(cfg.get("weak_marker_threshold", 2))
            if hits >= threshold:
                return True
        return False
    
    async def _extract_visual_features(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """提取图像视觉特征"""
        
        image_url = params.get("image_url", "")
        image_path = params.get("image_path", "")
        
        if not image_url and not image_path:
            raise ToolError("需要提供图像URL或路径", error_code="missing_image_input")
        
        feature_prompt = """提取这张图像的关键视觉特征：

请识别：
1. 主要物体和元素
2. 颜色分布
3. 构图类型
4. 光照条件
5. 纹理特征
6. 空间关系

返回JSON格式的特征描述。"""
        
        try:
            # 供应商无关：统一 VLM 图像理解
            from .service_interfaces import get_vlm_service
            vlm = get_vlm_service()
            img_input = image_url or image_path
            res = await vlm.image_understanding(image_input=img_input, prompt=feature_prompt, model=None, temperature=0.2)
            content = (res.get("analysis") or res.get("content") or "").strip()
            if not content:
                raise ToolError("视觉特征提取为空", error_code="visual_feature_empty")
            try:
                visual_features = json.loads(content)
                return {"visual_features": visual_features}
            except json.JSONDecodeError:
                return {
                    "visual_features": {
                        "description": content,
                        "extraction_method": "vlm_analysis",
                        "confidence": 0.8
                    }
                }
        except Exception as e:
            raise ToolError(f"视觉特征提取异常: {str(e)}", error_code="visual_feature_failed")

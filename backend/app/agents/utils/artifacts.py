"""
通用产物规整与持久化工具。

目标：
- 将 Agent 内的通用落盘/规整逻辑下沉，便于复用与单测。
- 保持最小侵入：由调用方注入上传函数（uploader），utils 不感知 Agent/工具细节。
"""
from __future__ import annotations

import os
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..memory.short_term.working_memory import WorkingMemory
from ..memory.config.scene_output_schema import load_scene_output_schema
from ..adapters.memory_views import load_scene_overview, extract_failed_scenes
from .memory_helpers import get_mas_working_memory

if TYPE_CHECKING:
    from ..memory.short_term.service import WorkingMemoryService


def extract_tool_payload(result: Any) -> Any:
    """兼容 ToolOutput：若对象带有 result 属性，则返回该属性；否则原样返回。"""
    try:
        if hasattr(result, "result"):
            return getattr(result, "result")
    except Exception:
        pass
    return result


def coerce_scene_number(val: Any) -> Optional[int]:
    """尽力将任意值转为场景号 int，失败返回 None。"""
    try:
        if val is None:
            return None
        s = str(val)
        if s.isdigit():
            return int(s)
    except Exception:
        return None
    return None


async def ensure_persisted_videos(
    results: List[Dict[str, Any]],
    uploader: Callable[[str, Any], Any],
) -> List[Dict[str, Any]]:
    """确保成功的视频结果具有稳定的 file_path。

    - 对缺失路径但存在 video_url 的项，通过调用 uploader(url, scene_num) 进行上传补全；
    - 其他情况原样返回。

    uploader 由调用方提供，返回值期望包含 file_path 或 local_path。
    """
    if not results:
        return results

    def _attach_storage_diagnostic(
        item: Dict[str, Any],
        *,
        status: str,
        fallback_reason: str,
        **fields: Any,
    ) -> Dict[str, Any]:
        updated = dict(item or {})
        diagnostic: Dict[str, Any] = {
            "status": str(status or "failed"),
            "fallback_reason": str(fallback_reason or "artifact_storage_failed"),
        }
        for key, value in fields.items():
            if value not in (None, ""):
                diagnostic[key] = value
        metadata = dict(updated.get("metadata") or {})
        metadata["storage"] = diagnostic
        diagnostics = list(metadata.get("diagnostics") or [])
        diagnostics.append({"category": "storage", **diagnostic})
        metadata["diagnostics"] = diagnostics
        updated["metadata"] = metadata
        updated["storage"] = diagnostic
        fallback_reasons = list(updated.get("fallback_reasons") or [])
        if diagnostic["fallback_reason"] not in fallback_reasons:
            fallback_reasons.append(diagnostic["fallback_reason"])
        updated["fallback_reasons"] = fallback_reasons
        return updated

    updated: List[Dict[str, Any]] = []
    for r in results:
        try:
            if not r or not r.get("success"):
                updated.append(r)
                continue
            if r.get("video_path"):
                updated.append(r)
                continue
            video_url = r.get("video_url")
            scene_num = r.get("scene_number")
            if video_url:
                storage_result = await uploader(video_url, scene_num)
                file_path = ""
                if isinstance(storage_result, dict):
                    file_path = storage_result.get("file_path") or storage_result.get("local_path") or ""
                    storage_diag = storage_result.get("storage")
                    if isinstance(storage_diag, dict) and storage_diag.get("status") == "failed":
                        r = _attach_storage_diagnostic(
                            dict(r),
                            status="failed",
                            fallback_reason=str(storage_diag.get("fallback_reason") or "artifact_upload_failed"),
                            error_type=storage_diag.get("error_type"),
                            error=storage_diag.get("error"),
                            scene_number=scene_num,
                        )
                r = dict(r)
                r["video_path"] = file_path or r.get("video_path", "")
                if not file_path:
                    r = _attach_storage_diagnostic(
                        r,
                        status="failed",
                        fallback_reason="artifact_upload_no_path",
                        scene_number=scene_num,
                    )
            updated.append(r)
        except Exception as exc:
            updated.append(
                _attach_storage_diagnostic(
                    dict(r or {}),
                    status="failed",
                    fallback_reason="artifact_upload_failed",
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                    scene_number=(r or {}).get("scene_number") if isinstance(r, dict) else None,
                )
            )
    return updated


async def persist_scene_outputs(
    *,
    kind: str,
    agent_memory: Optional[WorkingMemory] = None,
    shared_memory: Optional[WorkingMemory],
    executed_calls: Optional[List[Dict[str, Any]]] = None,
    artifacts: Optional[List[Dict[str, Any]]] = None,
    include_prompt: bool = True,
) -> List[Dict[str, Any]]:
    """Standardize tool outputs and store them as scene_outputs facts."""
    results: List[Dict[str, Any]] = list(artifacts or [])
    if not results and executed_calls:
        results = normalize_executed_calls_to_artifacts(
            executed_calls,
            kind=kind,
            include_prompt=include_prompt,
        )
    if not results:
        return []

    schema = load_scene_output_schema(kind)
    fields = schema.get("fields", {})
    key = f"scene_outputs.{kind}"
    # Agent WM 不再存副本；只写共享 WM
    agent_bucket = {}
    shared_bucket = shared_memory.get(key, {}) if shared_memory is not None else {}
    if shared_memory is not None and not isinstance(shared_bucket, dict):
        shared_bucket = {}

    for item in results:
        if not isinstance(item, dict):
            continue
        mapped = _map_scene_output(fields, item)
        if not mapped:
            continue
        sn = mapped.get("scene_number")
        if sn is None:
            continue
        if shared_memory is not None:
            shared_bucket[sn] = dict(mapped)

    if shared_memory is not None:
        shared_memory.put(key, shared_bucket)
    return results


def collect_scene_outputs(
    *,
    kind: str,
    memory: Optional[WorkingMemory],
    return_fields: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Collect persisted scene outputs from WorkingMemory based on schema."""
    if memory is None:
        return []
    schema = load_scene_output_schema(kind)
    fields = schema.get("return_fields") or return_fields
    key = f"scene_outputs.{kind}"
    bucket = memory.get(key, {})
    if not isinstance(bucket, dict):
        return []
    results: List[Dict[str, Any]] = []
    for record in bucket.values():
        if not isinstance(record, dict):
            continue
        if fields:
            entry = {name: record.get(name) for name in fields if name in record}
        else:
            entry = dict(record)
        if not entry:
            continue
        results.append(entry)
    results.sort(key=lambda item: item.get("scene_number") or 0)
    return results


def finalize_scene_outputs(
    *,
    kind: str,
    workflow_id: Optional[str],
    agent_memory: Optional[WorkingMemory],
    shared_memory: Optional[WorkingMemory] = None,
    service: Optional["WorkingMemoryService"] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Collect completion/failure payloads for a given scene output kind."""
    wf_id = str(workflow_id) if workflow_id else None
    shared = shared_memory
    if shared is None and wf_id and service is not None:
        try:
            shared = get_mas_working_memory(wf_id, service=service)
        except Exception:
            shared = None
    completed = collect_scene_outputs(kind=kind, memory=shared or agent_memory)
    overview = load_scene_overview(wf_id, service=service) if wf_id and service is not None else None
    failed = extract_failed_scenes(overview)
    return completed, failed


def make_storage_uploader(
    use_tool: Callable[..., Awaitable[Any]],
    *,
    tool_name: str = "file_storage_tool",
    action: str = "upload_from_url",
    destination_prefix: str = "videos",
    file_extension: str = "mp4",
    source_tag: str = "agent_upload",
    metadata_extra: Optional[Dict[str, Any]] = None,
) -> Callable[[str, Any], Awaitable[Dict[str, Any]]]:
    """根据 use_tool 构造视频持久化 uploader。

    - destination_prefix: 目标存储前缀，如 videos/scene_xxx.mp4
    - file_extension: 扩展名；传入时可包含/不包含点号
    - source_tag: metadata 中的来源标签，便于审计
    - metadata_extra: 追加到 metadata 的自定义键值
    """
    prefix = (destination_prefix or "videos").strip("/")
    ext = (file_extension or "mp4").lstrip(".")

    async def _upload(url: str, scene_number: Any) -> Dict[str, Any]:
        if not url or not callable(use_tool):
            return {}
        scene_idx = coerce_scene_number(scene_number)
        filename_core = (
            f"scene_{scene_idx}"
            if scene_idx is not None
            else f"artifact_{int(time.time() * 1000)}"
        )
        destination_key = f"{prefix}/{filename_core}.{ext}"
        metadata: Dict[str, Any] = {
            "scene_number": scene_idx if scene_idx is not None else scene_number,
            "source": source_tag,
        }
        if scene_idx is None:
            metadata["raw_scene_number"] = scene_number
        if metadata_extra:
            metadata.update(metadata_extra)
        try:
            tool_result = await use_tool(
                tool_name=tool_name,
                action=action,
                parameters={
                    "url": url,
                    "destination_key": destination_key,
                    "metadata": metadata,
                },
            )
        except Exception as exc:
            return {
                "storage": {
                    "status": "failed",
                    "fallback_reason": "artifact_upload_failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:200],
                }
            }
        payload = extract_tool_payload(tool_result)
        if isinstance(payload, dict):
            if "file_path" not in payload and payload.get("local_path"):
                payload = dict(payload)
                payload["file_path"] = payload.get("local_path")
            return payload
        return {}

    return _upload


# --------- Unified artifact selection (shared) ---------

def _exts_for_kind(kind: str) -> List[str]:
    k = (kind or "").lower()
    if k == "video":
        return [".mp4", ".mov", ".mkv"]
    if k == "audio":
        return [".wav", ".mp3", ".aac", ".m4a", ".flac"]
    if k == "image":
        return [".jpg", ".jpeg", ".png", ".webp"]
    return []


def _pick_from_payload(payload: Dict[str, Any], kind: str, require_local: bool) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    # Prefer local path
    fp = (
        payload.get("file_path")
        or payload.get("output_path")
        or payload.get("output_file")
        or payload.get("local_path")
    )
    if isinstance(fp, str) and fp:
        if require_local and not os.path.exists(fp):
            # caller要求必须是本地存在的文件
            return None
        # 若声明了类型，尝试按后缀过滤；否则直接返回
        exts = _exts_for_kind(kind)
        if not exts or any(str(fp).lower().endswith(ext) for ext in exts):
            return fp
    # Fallback to URLs when本地非必需
    if not require_local:
        if kind == "video" and isinstance(payload.get("video_url"), str) and payload.get("video_url"):
            return payload.get("video_url")
        if kind == "audio" and isinstance(payload.get("audio_url"), str) and payload.get("audio_url"):
            return payload.get("audio_url")
        if kind == "image" and isinstance(payload.get("image_url"), str) and payload.get("image_url"):
            return payload.get("image_url")
    return None


def pick_artifact_path_from_results(
    entries: List[Dict[str, Any]],
    *,
    kind: str = "video",
    require_local: bool = False,
) -> Optional[str]:
    """从一组标准化或原始结果中选择符合期望类型的产物路径/URL。

    - entries 可为 BaseAgent 规范化的 last_round_results（含 file_path/video_url/audio_url 等），
      也可为 executed_calls 的结果列表（每项可能包含 result 对象/字典）。
    - kind: 'video' | 'audio' | 'image'
    - require_local: 若为 True，则仅返回存在的本地文件路径（优先 file_path/output_path/local_path）。
    """
    if not entries:
        return None
    for item in entries:
        if not isinstance(item, dict):
            continue
        # 规范化快照路径（last_round_results 风格）
        cand = _pick_from_payload(item, kind=kind, require_local=require_local)
        if cand:
            return cand
        # executed_calls 风格：result 可能为对象或字典
        payload = extract_tool_payload(item.get("result")) if item.get("result") is not None else None
        if isinstance(payload, dict):
            cand = _pick_from_payload(payload, kind=kind, require_local=require_local)
            if cand:
                return cand
    return None


def normalize_executed_calls_to_artifacts(
    executed_calls: List[Dict[str, Any]],
    *,
    kind: Optional[str] = None,
    include_prompt: bool = True,
) -> List[Dict[str, Any]]:
    """将 executed_calls 规范化为通用 artifacts 列表。

    返回项字段：success, scene_number, file_path(或image_path/video_path), url(根据kind映射), prompt_text。
    - kind: 限定 'image' | 'video' | 'audio'；为 None 时不过滤。
    - scene_number 来自 args.scene_number（优先）。
    """
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            if isinstance(value, bool):
                return None
            return int(value)
        except Exception:
            return None

    def _parse_scene_number_from_reference_id(reference_id: Any) -> Optional[int]:
        if not isinstance(reference_id, str) or not reference_id:
            return None
        # Contract-boundary normalization: accept common legacy reference_id patterns like:
        # - scene_1_voice_over / scene_1_narration / scene_1
        # - scene-1-xxx / scene1_xxx
        import re as _re

        m = _re.search(r"(?:^|[^0-9])scene[_-]?(?P<num>[0-9]{1,4})(?:[^0-9]|$)", reference_id.lower())
        if not m:
            return None
        return _coerce_int(m.group("num"))

    out: List[Dict[str, Any]] = []
    for call in executed_calls or []:
        if not isinstance(call, dict) or not call.get("success"):
            continue
        args = call.get("args") or {}
        payload = extract_tool_payload(call.get("result")) if call.get("result") is not None else None
        if not isinstance(payload, dict):
            continue
        # 选择路径与URL
        file_path = (
            payload.get("file_path")
            or payload.get("output_path")
            or payload.get("local_path")
            # common cross-tool aliases
            or payload.get("audio_path")
            or payload.get("video_path")
            or payload.get("image_path")
        )
        image_url = payload.get("image_url")
        video_url = payload.get("video_url")
        audio_url = payload.get("audio_url")
        audio_path = payload.get("audio_path")
        video_path = payload.get("video_path")
        image_path = payload.get("image_path")
        # kind 过滤
        if kind == "image" and not (image_url or file_path):
            continue
        if kind == "video" and not (video_url or file_path):
            continue
        if kind == "audio" and not (audio_url or audio_path or file_path):
            continue
        # 通用时长
        duration = (
            payload.get("duration_sec")
            or payload.get("final_duration")
            or payload.get("duration")
            or payload.get("audio_duration")
            or payload.get("video_duration")
        )
        try:
            if duration is not None:
                duration = float(duration)
        except Exception:
            duration = None
        # 场景号
        sn = _coerce_int(args.get("scene_number") if isinstance(args, dict) else None)
        if sn is None and isinstance(args, dict):
            md = args.get("metadata")
            if isinstance(md, dict):
                sn = _coerce_int(md.get("scene_number"))
        if sn is None and isinstance(args, dict):
            sn = _parse_scene_number_from_reference_id(args.get("reference_id"))
        # 构造结果
        item: Dict[str, Any] = {
            "success": True,
            "scene_number": sn,
            "file_path": file_path or "",
            "image_url": image_url or "",
            "video_url": video_url or "",
            "audio_url": audio_url or "",
        }
        if isinstance(audio_path, str) and audio_path:
            item["audio_path"] = audio_path
        if isinstance(video_path, str) and video_path:
            item["video_path"] = video_path
        if isinstance(image_path, str) and image_path:
            item["image_path"] = image_path
        if isinstance(payload.get("metadata"), dict) and payload.get("metadata"):
            item["metadata"] = dict(payload.get("metadata") or {})
        for extra_key in ("provider", "voice_id", "sample_rate", "audio_format", "reference_id"):
            if extra_key in payload and payload.get(extra_key) not in (None, ""):
                item[extra_key] = payload.get(extra_key)
        if duration is not None:
            item["duration_sec"] = duration
        if include_prompt:
            item["prompt_text"] = args.get("prompt") or payload.get("prompt_text") or payload.get("prompt") or ""
        out.append(item)
    return out


def _map_scene_output(fields: Dict[str, Dict[str, Any]], payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not fields:
        return {}
    result: Dict[str, Any] = {}
    for target, conf in fields.items():
        sources = conf.get("source")
        if not sources:
            continue
        if not isinstance(sources, (list, tuple)):
            sources = [sources]
        value = None
        for src in sources:
            if src in payload and payload[src] not in (None, ""):
                value = payload[src]
                break
        if value is None and conf.get("required"):
            return None
        if value is None:
            continue
        if conf.get("coerce") == "int":
            try:
                value = int(value)
            except Exception:
                return None
        result[target] = value
    return result

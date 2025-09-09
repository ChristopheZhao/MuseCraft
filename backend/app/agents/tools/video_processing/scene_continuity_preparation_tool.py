"""
场景连续性准备工具 - 组合工具，处理视频场景间的连续性准备
"""
import asyncio
from typing import Dict, Any, List, Optional
from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolOutput, ToolError


class SceneContinuityPreparationTool(AsyncTool):
    """
    场景连续性准备组合工具
    
    职责：
    - 根据是否需要连续性，自动处理连续性帧获取
    - 内部组合 final_frame_tool + oss_storage 
    - 简化VideoGenerator的工具选择复杂度
    - 返回统一的图像URL供video_generation使用
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="scene_continuity_preparation",
            version="1.0.0", 
            description="处理场景连续性准备，自动获取前一场景尾帧并上传获取URL",
            tool_type=ToolType.MEDIA_PROCESSING,
            author="MuseCraft MAS Team",
            tags=["scene", "continuity", "composition", "video"],
            capabilities=[
                "continuity_frame_extraction",
                "automatic_upload",
                "url_generation",
                "workflow_simplification"
            ],
            dependencies=["final_frame_tool", "oss_storage"]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
    
    def _initialize(self):
        """初始化场景连续性准备工具"""
        self.logger.info("🔗 场景连续性准备工具初始化...")
    
    def get_available_actions(self) -> List[str]:
        return ["prepare_scene_input"]

    def get_fc_visibility(self) -> Dict[str, Any]:
        """最小暴露：仅暴露准备动作，避免高风险操作。"""
        return {
            "expose": True,
            "allowed_actions": ["prepare_scene_input"]
        }
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "prepare_scene_input":
            # 最小必填：仅需 scene_number。其余参数为可选回退/覆盖。
            # - previous_scene_video_url: 可选，若提供则直接对该视频提帧（用于“当前场景生成后存尾帧”的复用路径）
            # - fallback_image_url: 可选，连续性缺失或失败时的兜底
            return {
                "type": "object",
                "properties": {
                    "scene_number": {
                        "type": "integer",
                        "description": "当前场景编号（用于解析依赖关系）"
                    },
                    "previous_scene_video_url": {
                        "type": "string",
                        "description": "可选：显式提供用于提帧的视频URL/路径（覆盖自动依赖解析）。常用于存储当前场景尾帧。"
                    },
                    "fallback_image_url": {
                        "type": "string",
                        "description": "可选：兜底图像URL（不需要连续性或连续性处理失败时使用）"
                    }
                },
                "required": ["scene_number"],
                "description": "准备场景输入图像：若场景需要连续性则从依赖场景尾帧获取，否则返回兜底图像。"
            }
        
        return {}
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行场景连续性准备"""
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "prepare_scene_input":
            return await self._prepare_scene_input(params)
        else:
            raise ToolError(f"Unknown action: {action}", self.metadata.name)
    
    async def _prepare_scene_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        准备场景输入图像
        
        根据连续性需求：
        - 连续：提取前一场景尾帧 → 上传OSS → 返回URL
        - 不连续：直接返回备用图像URL
        """
        scene_number = int(params["scene_number"])
        previous_video_url_override = params.get("previous_scene_video_url")
        fallback_image_url = params.get("fallback_image_url", "")

        # 复用路径：显式提供了上游URL
        if previous_video_url_override:
            try:
                url_in = str(previous_video_url_override).strip()
                # 更稳健的类型判定：以URL path为准（忽略查询串/签名）
                try:
                    from urllib.parse import urlparse
                    _p = urlparse(url_in).path or url_in
                except Exception:
                    _p = url_in
                low_path = _p.lower()
                is_image = low_path.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))
                is_video = low_path.endswith((".mp4", ".mov", ".mkv", ".avi", ".webm"))
                if is_image and not is_video:
                    # 直接复用图像URL作为连续性帧，避免误用ffmpeg处理图片
                    self.logger.info("♻️  覆盖URL判定为图像：直接复用为连续性帧（跳过上传/提帧）")
                    return {
                        "success": True,
                        "scene_number": scene_number,
                        "image_url": url_in,
                        "continuity_used": True,
                        "processing_type": "continuity_frame_reuse_from_override",
                        "message": f"场景 {scene_number} 复用提供的图像URL作为连续性帧"
                    }
                # 其余情况：按视频处理（无扩展名也尝试）
                self.logger.info(
                    f"🔗 场景 {scene_number}：从提供的视频提取尾帧（覆盖自动依赖解析）"
                )
                final_frame_result = await self._extract_final_frame(
                    video_url=url_in,
                    memory_scene_number=None
                )
                if not final_frame_result.get("success"):
                    raise ToolError(
                        f"Failed to extract final frame: {final_frame_result.get('error', 'Unknown error')}",
                        self.metadata.name
                    )
                frame_data = final_frame_result["frame_data"]
                upload_result = await self._upload_frame_to_oss(frame_data, scene_number)
                if not upload_result.get("success"):
                    raise ToolError(
                        f"Failed to upload frame to OSS: {upload_result.get('error', 'Unknown error')}",
                        self.metadata.name
                    )
                url = upload_result["url"]
                return {
                    "success": True,
                    "scene_number": scene_number,
                    "image_url": url,
                    "continuity_used": True,
                    "processing_type": "current_scene_last_frame",
                    "source_video_url": url_in,
                    "frame_extraction_info": final_frame_result.get("extraction_info", {}),
                    "upload_info": upload_result.get("upload_info", {}),
                    "message": f"场景 {scene_number} 已从给定视频提取尾帧并上传"
                }
            except Exception as e:
                self.logger.error(f"❌ 场景 {scene_number} 提取/上传当前场景尾帧失败: {e}")
                return {
                    "success": True,
                    "scene_number": scene_number,
                    "image_url": fallback_image_url,
                    "continuity_used": False,
                    "processing_type": "fallback_due_to_current_last_frame_error",
                    "error": str(e),
                    "warning": f"当前场景尾帧处理失败，使用兜底图像"
                }

        # 自动依赖解析：根据 WorkflowState 的 depends_on_scene 查找上游视频
        prev_scene_no: Optional[int] = None
        current_scene_image_url: str = ""
        try:
            from ....core.workflow_state import workflow_manager
            # 遍历活跃工作流，定位包含该场景的工作流
            candidate_wf = None
            for wf in workflow_manager.get_active_workflows():
                sc = wf.get_scene(scene_number)
                if sc is not None:
                    candidate_wf = wf
                    break
            if candidate_wf is not None:
                cur_sc = candidate_wf.get_scene(scene_number)
                current_scene_image_url = getattr(cur_sc, 'image_url', '') or ''
                dep = getattr(cur_sc, 'depends_on_scene', None)
                if isinstance(dep, (int, str)):
                    try:
                        dep = int(dep) if dep is not None else None
                    except Exception:
                        dep = None
                prev_scene_no = dep if (isinstance(dep, int) and dep > 0) else None
        except Exception:
            prev_scene_no = None

        is_continuous = prev_scene_no is not None
        self.logger.info(
            f"🔗 准备场景 {scene_number} 输入图像，连续性: {is_continuous}"
            + (f", previous_scene={prev_scene_no}" if is_continuous else "")
        )

        if not is_continuous:
            # 不需要连续性：直接返回兜底或该场景自身的 image_url
            fallback = fallback_image_url or current_scene_image_url
            return {
                "success": True,
                "scene_number": scene_number,
                "image_url": fallback,
                "continuity_used": False,
                "processing_type": "fallback_image",
                "message": f"场景 {scene_number} 无连续性依赖，返回兜底图像"
            }

        # 执行连续性处理：优先用内存/已存尾帧，其次回退到上游视频提帧
        try:
            # 1) 内存优先（data_url/URL）
            final_frame_result = await self._extract_final_frame(
                video_url=None,
                memory_scene_number=prev_scene_no
            )
            frame_data: Optional[str] = None
            if final_frame_result.get("success"):
                frame_data = final_frame_result.get("frame_data")
                # 若返回的是直链URL（非data_url），可直接复用，无需再次上传
                if isinstance(frame_data, str) and frame_data.startswith("http"):
                    self.logger.info("♻️  复用已存在的连续性帧URL（跳过上传）")
                    return {
                        "success": True,
                        "scene_number": scene_number,
                        "image_url": frame_data,
                        "continuity_used": True,
                        "processing_type": "continuity_frame_reuse",
                        "previous_scene": prev_scene_no,
                        "frame_extraction_info": final_frame_result.get("extraction_info", {}),
                        "message": f"场景 {scene_number} 复用上游已存连续性帧"
                    }
            # 2) 若内存无可用帧，则尝试从上游视频提帧
            if not frame_data:
                prev_video_url = None
                prev_video_path = None
                try:
                    # 再次获取workflow以查找上游视频产物
                    from ....core.workflow_state import workflow_manager
                    for wf in workflow_manager.get_active_workflows():
                        sc_prev = wf.get_scene(prev_scene_no) if prev_scene_no else None
                        if sc_prev is not None:
                            prev_video_url = getattr(sc_prev, 'video_url', '') or ''
                            prev_video_path = getattr(sc_prev, 'video_path', '') or ''
                            # 优先使用 URL；若无URL则使用本地路径
                            break
                except Exception:
                    prev_video_url, prev_video_path = None, None

                source = prev_video_url or prev_video_path
                if not source:
                    # 兜底：若上游无视频，也许已存 last_frame_url 可直接复用
                    try:
                        from ....core.workflow_state import workflow_manager
                        for wf in workflow_manager.get_active_workflows():
                            sc_prev = wf.get_scene(prev_scene_no) if prev_scene_no else None
                            if sc_prev is not None and getattr(sc_prev, 'last_frame_url', ''):
                                return {
                                    "success": True,
                                    "scene_number": scene_number,
                                    "image_url": getattr(sc_prev, 'last_frame_url'),
                                    "continuity_used": True,
                                    "processing_type": "continuity_frame_reuse",
                                    "previous_scene": prev_scene_no,
                                    "message": f"场景 {scene_number} 复用上游 last_frame_url"
                                }
                    except Exception:
                        pass
                    # 仍不可用：回退到兜底图像
                    fallback = fallback_image_url or current_scene_image_url
                    return {
                        "success": True,
                        "scene_number": scene_number,
                        "image_url": fallback,
                        "continuity_used": False,
                        "processing_type": "fallback_due_to_missing_previous_video",
                        "warning": "需要连续性但未找到上游视频或尾帧"
                    }

                # 有可用视频源：执行提帧
                final_frame_result = await self._extract_final_frame(
                    video_url=source,
                    memory_scene_number=prev_scene_no
                )
                if not final_frame_result.get("success"):
                    raise ToolError(
                        f"Failed to extract final frame: {final_frame_result.get('error', 'Unknown error')}",
                        self.metadata.name
                    )
                frame_data = final_frame_result["frame_data"]

            # 统一上传（当 frame_data 为 data_url/base64 或本地内容时）
            upload_result = await self._upload_frame_to_oss(frame_data, scene_number)
            if not upload_result.get("success"):
                raise ToolError(
                    f"Failed to upload frame to OSS: {upload_result.get('error', 'Unknown error')}",
                    self.metadata.name
                )
            continuity_image_url = upload_result["url"]
            self.logger.info(f"✅ 场景 {scene_number} 连续性处理完成，获得URL: {continuity_image_url}")
            return {
                "success": True,
                "scene_number": scene_number,
                "image_url": continuity_image_url,
                "continuity_used": True,
                "processing_type": "continuity_frame",
                "previous_scene": prev_scene_no,
                "frame_extraction_info": final_frame_result.get("extraction_info", {}),
                "upload_info": upload_result.get("upload_info", {}),
                "message": f"场景 {scene_number} 连续性处理成功"
            }
        except Exception as e:
            self.logger.error(f"❌ 场景 {scene_number} 连续性处理失败: {e}")
            fallback = fallback_image_url or current_scene_image_url
            return {
                "success": True,  # 整体仍然成功，只是使用了备用方案
                "scene_number": scene_number,
                "image_url": fallback,
                "continuity_used": False,
                "processing_type": "fallback_due_to_continuity_error",
                "error": str(e),
                "warning": f"连续性处理失败，回退到备用图像: {e}"
            }
    
    async def _extract_final_frame(self, video_url: Optional[str], memory_scene_number: Optional[int] = None) -> Dict[str, Any]:
        """
        提取视频最后一帧
        
        内部调用 final_frame_tool
        """
        try:
            from ..tool_registry import get_tool_registry
            from ..base_tool import ToolInput
            
            registry = get_tool_registry()
            final_frame_tool = registry.get_tool("final_frame_tool")
            
            if not final_frame_tool:
                raise ToolError("final_frame_tool not available", self.metadata.name)

            # 1) 优先从记忆读取（仅当为 data_url/直链时直接使用）
            if memory_scene_number and int(memory_scene_number) > 0:
                try:
                    mem_res = await final_frame_tool.execute(ToolInput(
                        action="get_final_frame_from_memory",
                        parameters={"scene_number": int(memory_scene_number)}
                    ))
                    if getattr(mem_res, 'success', False):
                        payload = getattr(mem_res, 'result', mem_res)
                        if isinstance(payload, dict):
                            if payload.get("format") == "data_url" and payload.get("data_url"):
                                return {
                                    "success": True,
                                    "frame_data": payload.get("data_url"),  # 直接返回data_url，便于上传
                                    "extraction_info": {
                                        "source": "memory",
                                        "from_scene": int(memory_scene_number),
                                        "extraction_method": "final_frame_tool:get_final_frame_from_memory"
                                    }
                                }
                            if payload.get("format") == "url" and payload.get("url"):
                                # 若内存记录的是直链URL，可以直接返回（无需再上传）
                                return {
                                    "success": True,
                                    "frame_data": payload.get("url"),
                                    "extraction_info": {
                                        "source": "memory",
                                        "from_scene": int(memory_scene_number),
                                        "extraction_method": "final_frame_tool:get_final_frame_from_memory"
                                    }
                                }
                except Exception:
                    # 读取失败则回退到视频提取
                    pass

            # 2) 回退：从视频中提取最后一帧并以 data_url 形式返回
            if not video_url:
                return {"success": False, "error": "No video_url provided for extraction"}
            result = await final_frame_tool.execute(ToolInput(
                action="extract_final_frame_from_video",
                parameters={
                    "video_url": video_url,
                    "to_base64": True
                }
            ))

            if getattr(result, 'success', False):
                payload = getattr(result, 'result', result)
                frame_data: Optional[str] = None
                if isinstance(payload, dict):
                    if payload.get("format") == "data_url" and payload.get("data_url"):
                        frame_data = payload.get("data_url")
                    elif payload.get("format") == "path" and payload.get("path"):
                        # 此分支理论上不应出现（已请求 to_base64=True），但为稳健性保留
                        # 若将来需要支持本地路径上传，可在 _upload_frame_to_oss 中扩展 local_path 处理
                        frame_data = None
                if frame_data:
                    return {
                        "success": True,
                        "frame_data": frame_data,
                        "extraction_info": {
                            "source_video": video_url,
                            "extraction_method": "final_frame_tool:extract_final_frame_from_video"
                        }
                    }
                return {"success": False, "error": "Extraction returned no data_url"}
            else:
                error_msg = getattr(result, 'error', "Unknown extraction error")
                return {"success": False, "error": error_msg}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _upload_frame_to_oss(self, frame_data: Any, scene_number: int) -> Dict[str, Any]:
        """
        上传帧数据到OSS
        
        内部调用 oss_storage
        """
        try:
            from ..tool_registry import get_tool_registry 
            from ..base_tool import ToolInput
            
            registry = get_tool_registry()
            oss_tool = registry.get_tool("oss_storage")
            
            if not oss_tool:
                raise ToolError("oss_storage tool not available", self.metadata.name)
            
            # 构建OSS上传参数
            # 归类到 OSS_IMAGE_DIR 下
            try:
                from ....core.config import settings as _app_settings
                _image_root = getattr(_app_settings, 'OSS_IMAGE_DIR', 'images').strip('/')
                _cont_dir = getattr(_app_settings, 'OSS_CONTINUITY_DIR', 'continuity_frames').strip('/')
            except Exception:
                _image_root = 'images'
                _cont_dir = 'continuity_frames'
            remote_path = f"{_image_root}/{_cont_dir}/scene_{scene_number}_continuity_frame.jpg"
            
            upload_params = {
                "remote_path": remote_path,
                "content_type": "image/jpeg",
                "public_read": True
            }
            
            # 处理不同格式的frame_data
            if isinstance(frame_data, str):
                # data URL 格式：data:image/jpeg;base64,<b64>
                if frame_data.startswith("data:image"):
                    try:
                        header, b64 = frame_data.split(",", 1)
                        import base64
                        upload_params["content"] = base64.b64decode(b64)
                        # 可从头部解析 mime，但本工具固定按 jpeg 输出
                    except Exception:
                        # 兜底：直接按原样作为内容（不理想），但避免中断
                        upload_params["content"] = frame_data.encode("utf-8")
                else:
                    # 视为纯base64（无头部）
                    try:
                        import base64
                        upload_params["content"] = base64.b64decode(frame_data)
                    except Exception:
                        upload_params["content"] = frame_data.encode("utf-8")
            else:
                # 二进制数据
                upload_params["content"] = frame_data
            
            result = await oss_tool.execute(ToolInput(
                action="upload",
                parameters=upload_params
            ))
            
            # 处理ToolOutput格式
            if hasattr(result, 'success') and result.success:
                upload_result = result.result
                return {
                    "success": True,
                    "url": upload_result.get("url"),
                    "upload_info": {
                        "remote_path": remote_path,
                        "content_type": "image/jpeg",
                        "public_read": True
                    }
                }
            else:
                error_msg = result.error if hasattr(result, 'error') else "Unknown upload error"
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            from ..tool_registry import get_tool_registry
            
            registry = get_tool_registry()
            final_frame_available = bool(registry.get_tool("final_frame_tool"))
            oss_available = bool(registry.get_tool("oss_storage"))
            
            return {
                "healthy": final_frame_available and oss_available,
                "service": "scene_continuity_preparation",
                "dependencies": {
                    "final_frame_tool": final_frame_available,
                    "oss_storage": oss_available
                },
                "capabilities": self.metadata.capabilities
            }
        except Exception as e:
            return {
                "healthy": False, 
                "error": str(e),
                "service": "scene_continuity_preparation"
            }

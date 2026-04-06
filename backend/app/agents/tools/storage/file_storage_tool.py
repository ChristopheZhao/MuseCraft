"""
File Storage Management Tool - 文件存储管理工具
支持本地存储、MinIO、AWS S3等存储方式
"""

import os
import shutil
import uuid
import hashlib
import mimetypes
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urlparse
import httpx
import base64
import asyncio
from importlib.util import find_spec

# Lazy dependency checks: avoid importing heavy SDKs at module import time.
BOTO3_AVAILABLE = find_spec("boto3") is not None
MINIO_AVAILABLE = find_spec("minio") is not None

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
try:
    # Prefer project config for local storage path
    from ....core.config import settings as _app_settings
except Exception:
    _app_settings = None


class FileStorageTool(AsyncTool):
    """
    文件存储管理工具
    
    支持功能：
    - 本地文件存储
    - MinIO对象存储
    - AWS S3存储
    - 文件上传下载
    - 文件元数据管理
    - 文件URL生成
    - 存储空间管理
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="file_storage_tool",
            version="1.0.0",
            description="文件存储管理工具，支持本地、MinIO、S3等存储方式",
            tool_type=ToolType.STORAGE,
            author="system",
            tags=["storage", "file", "s3", "minio", "upload", "download"],
            capabilities=[
                "local_storage",
                "s3_storage",
                "minio_storage",
                "file_upload",
                "file_download",
                "url_generation",
                "metadata_management",
                "storage_cleanup"
            ],
            limitations=[
                "storage_space_limits",
                "file_size_limits",
                "network_dependent",
                "credentials_required"
            ]
        )
    
    def _initialize(self):
        """初始化文件存储工具"""
        self.storage_type = self.config.get("storage_type", "local")  # local, s3, minio
        
        # 本地存储配置：默认使用应用配置的 TEMP_PATH（更贴合项目目录），可被工具config覆盖
        default_local_dir = None
        try:
            if _app_settings is not None and getattr(_app_settings, 'TEMP_PATH', None):
                default_local_dir = _app_settings.TEMP_PATH
        except Exception:
            default_local_dir = None
        if not default_local_dir:
            default_local_dir = "/tmp/video_storage"
        self.local_storage_dir = self.config.get("local_storage_dir", default_local_dir)
        self.max_file_size = self.config.get("max_file_size", 500 * 1024 * 1024)  # 500MB
        
        # 创建本地存储目录
        os.makedirs(self.local_storage_dir, exist_ok=True)
        
        # 初始化存储客户端
        if self.storage_type == "s3":
            self._init_s3_client()
        elif self.storage_type == "minio":
            self._init_minio_client()
        
        self.logger.info(f"Initialized file storage tool with type: {self.storage_type}")
    
    def _init_s3_client(self):
        """初始化S3客户端"""
        if not BOTO3_AVAILABLE:
            raise ToolError("boto3 not installed, required for S3 storage", self.metadata.name)

        try:
            import boto3  # type: ignore
            from botocore.exceptions import ClientError  # type: ignore
        except Exception as exc:
            raise ToolError("boto3 not installed, required for S3 storage", self.metadata.name) from exc
        self._s3_client_error = ClientError
        
        self.s3_bucket = self.config.get("s3_bucket")
        self.s3_region = self.config.get("s3_region", "us-east-1")
        self.s3_access_key = self.config.get("s3_access_key")
        self.s3_secret_key = self.config.get("s3_secret_key")
        
        if not all([self.s3_bucket, self.s3_access_key, self.s3_secret_key]):
            raise ToolError("S3 credentials not properly configured", self.metadata.name)
        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.s3_access_key,
            aws_secret_access_key=self.s3_secret_key,
            region_name=self.s3_region
        )
    
    def _init_minio_client(self):
        """初始化MinIO客户端"""
        if not MINIO_AVAILABLE:
            raise ToolError("minio not installed, required for MinIO storage", self.metadata.name)

        try:
            from minio import Minio  # type: ignore
            from minio.error import S3Error  # type: ignore
        except Exception as exc:
            raise ToolError("minio not installed, required for MinIO storage", self.metadata.name) from exc
        self._minio_error = S3Error
        
        self.minio_endpoint = self.config.get("minio_endpoint")
        self.minio_access_key = self.config.get("minio_access_key")
        self.minio_secret_key = self.config.get("minio_secret_key")
        self.minio_bucket = self.config.get("minio_bucket")
        self.minio_secure = self.config.get("minio_secure", True)
        
        if not all([self.minio_endpoint, self.minio_access_key, self.minio_secret_key, self.minio_bucket]):
            raise ToolError("MinIO credentials not properly configured", self.metadata.name)
        
        self.minio_client = Minio(
            self.minio_endpoint,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            secure=self.minio_secure
        )

    def get_fc_visibility(self) -> Dict[str, Any]:
        """存储工具不对 FC 暴露，避免模型直接操作存储。
        调用应由业务复合工具或Agent代码内注入。
        """
        return {"expose": False, "allowed_actions": []}
    
    def get_available_actions(self) -> List[str]:
        return [
            "upload_file",
            "download_file",
            "download_from_url",
            "upload_from_url",
            "upload_base64",
            "generate_download_url",
            "generate_upload_url",
            "delete_file",
            "list_files",
            "get_file_info",
            "copy_file",
            "move_file",
            "cleanup_old_files"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
            "upload_file": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "本地文件路径"},
                    "destination_key": {"type": "string", "description": "存储键名"},
                    "content_type": {"type": "string", "description": "文件MIME类型"},
                    "metadata": {"type": "object", "description": "文件元数据"},
                    "public": {"type": "boolean", "description": "是否公开访问"}
                },
                "required": ["file_path"]
            },
            "download_file": {
                "type": "object",
                "properties": {
                    "file_key": {"type": "string", "description": "文件存储键名"},
                    "local_path": {"type": "string", "description": "本地保存路径"}
                },
                "required": ["file_key"]
            },
            "upload_from_url": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "源文件URL"},
                    "destination_key": {"type": "string", "description": "存储键名"},
                    "metadata": {"type": "object", "description": "文件元数据"}
                },
                "required": ["url"]
            },
            "download_from_url": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "源文件URL"},
                    "destination_key": {"type": "string", "description": "本地保存相对路径（相对于local_storage_dir）"},
                    "overwrite": {"type": "boolean", "description": "若目标已存在是否覆盖"},
                    "metadata": {"type": "object", "description": "附加元数据（可选）"},
                },
                "required": ["url"],
            },
            "upload_base64": {
                "type": "object",
                "properties": {
                    "base64_data": {"type": "string", "description": "Base64编码的文件数据"},
                    "filename": {"type": "string", "description": "文件名"},
                    "content_type": {"type": "string", "description": "文件MIME类型"}
                },
                "required": ["base64_data", "filename"]
            },
            "generate_download_url": {
                "type": "object",
                "properties": {
                    "file_key": {"type": "string", "description": "文件存储键名"},
                    "expiration": {"type": "integer", "description": "URL过期时间(秒)"}
                },
                "required": ["file_key"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行文件存储操作"""
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "upload_file":
            return await self._upload_file(params)
        elif action == "download_file":
            return await self._download_file(params)
        elif action == "download_from_url":
            return await self._download_from_url(params)
        elif action == "upload_from_url":
            return await self._upload_from_url(params)
        elif action == "upload_base64":
            return await self._upload_base64(params)
        elif action == "generate_download_url":
            return await self._generate_download_url(params)
        elif action == "generate_upload_url":
            return await self._generate_upload_url(params)
        elif action == "delete_file":
            return await self._delete_file(params)
        elif action == "list_files":
            return await self._list_files(params)
        elif action == "get_file_info":
            return await self._get_file_info(params)
        elif action == "copy_file":
            return await self._copy_file(params)
        elif action == "move_file":
            return await self._move_file(params)
        elif action == "cleanup_old_files":
            return await self._cleanup_old_files(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _upload_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """上传文件"""
        try:
            file_path = params["file_path"]
            destination_key = params.get("destination_key")
            content_type = params.get("content_type")
            metadata = params.get("metadata", {})
            public = params.get("public", False)
            
            if not os.path.exists(file_path):
                raise ToolError(f"File not found: {file_path}", self.metadata.name)
            
            file_size = os.path.getsize(file_path)
            if file_size > self.max_file_size:
                raise ToolError(f"File too large: {file_size} bytes (max: {self.max_file_size})", self.metadata.name)
            
            # 生成存储键名
            if not destination_key:
                filename = os.path.basename(file_path)
                file_id = str(uuid.uuid4())
                destination_key = f"{file_id}/{filename}"
            
            # 确定内容类型
            if not content_type:
                content_type, _ = mimetypes.guess_type(file_path)
                content_type = content_type or "application/octet-stream"
            
            # 计算文件哈希
            file_hash = self._calculate_file_hash(file_path)
            
            # 添加元数据
            metadata.update({
                "original_filename": os.path.basename(file_path),
                "file_size": str(file_size),
                "file_hash": file_hash,
                "content_type": content_type
            })
            
            # 根据存储类型上传
            if self.storage_type == "local":
                result = await self._upload_to_local(file_path, destination_key, metadata)
            elif self.storage_type == "s3":
                result = await self._upload_to_s3(file_path, destination_key, content_type, metadata, public)
            elif self.storage_type == "minio":
                result = await self._upload_to_minio(file_path, destination_key, content_type, metadata)
            else:
                raise ToolError(f"Unsupported storage type: {self.storage_type}", self.metadata.name)
            
            result.update({
                "file_key": destination_key,
                "file_size": file_size,
                "content_type": content_type,
                "file_hash": file_hash,
                "metadata": metadata
            })
            
            return result
            
        except Exception as e:
            raise ToolError(f"File upload failed: {str(e)}", self.metadata.name)
    
    async def _upload_to_local(self, file_path: str, destination_key: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """上传到本地存储"""
        destination_path = os.path.join(self.local_storage_dir, destination_key)
        destination_dir = os.path.dirname(destination_path)
        
        # 创建目录
        os.makedirs(destination_dir, exist_ok=True)
        
        # 复制文件
        shutil.copy2(file_path, destination_path)
        
        # 保存元数据
        metadata_path = destination_path + ".metadata"
        import json
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f)
        
        return {
            "storage_type": "local",
            "local_path": destination_path,
            "url": f"file://{destination_path}"
        }
    
    async def _upload_to_s3(self, file_path: str, destination_key: str, content_type: str, metadata: Dict[str, Any], public: bool) -> Dict[str, Any]:
        """上传到S3"""
        try:
            ClientError = getattr(self, "_s3_client_error", Exception)
            extra_args = {
                "ContentType": content_type,
                "Metadata": {k: str(v) for k, v in metadata.items()}
            }
            
            if public:
                extra_args["ACL"] = "public-read"
            
            self.s3_client.upload_file(
                file_path,
                self.s3_bucket,
                destination_key,
                ExtraArgs=extra_args
            )
            
            if public:
                url = f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com/{destination_key}"
            else:
                # 生成预签名URL（1小时有效）
                url = self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.s3_bucket, 'Key': destination_key},
                    ExpiresIn=3600
                )
            
            return {
                "storage_type": "s3",
                "bucket": self.s3_bucket,
                "url": url,
                "public": public
            }
            
        except ClientError as e:
            raise ToolError(f"S3 upload failed: {str(e)}", self.metadata.name)
    
    async def _upload_to_minio(self, file_path: str, destination_key: str, content_type: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """上传到MinIO"""
        try:
            S3Error = getattr(self, "_minio_error", Exception)
            self.minio_client.fput_object(
                self.minio_bucket,
                destination_key,
                file_path,
                content_type=content_type,
                metadata=metadata
            )
            
            # 生成预签名URL（1小时有效）
            url = self.minio_client.presigned_get_object(
                self.minio_bucket,
                destination_key,
                expires=3600
            )
            
            return {
                "storage_type": "minio",
                "bucket": self.minio_bucket,
                "url": url
            }
            
        except S3Error as e:
            raise ToolError(f"MinIO upload failed: {str(e)}", self.metadata.name)
    
    async def _upload_from_url(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """从URL上传文件"""
        try:
            url = params["url"]
            destination_key = params.get("destination_key")
            metadata = params.get("metadata", {})
            public = bool(params.get("public", False))
            
            # 下载文件到临时位置
            # 可配置超时：默认120s，避免大文件或慢速网络超时报错
            try:
                from ....core.config import settings as _app_settings
                http_timeout = int(getattr(_app_settings, 'FILE_STORAGE_HTTP_TIMEOUT', 120))
            except Exception:
                http_timeout = 120

            timeout = httpx.Timeout(timeout=http_timeout)
            # 下载重试设置
            try:
                from ....core.config import settings as _dl_settings
                max_retries = int(getattr(_dl_settings, 'FILE_STORAGE_DOWNLOAD_RETRIES', 3))
            except Exception:
                max_retries = 3

            attempt = 0
            last_err = None
            while attempt < max_retries:
                try:
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                        # 流式下载，边下边写，防止一次性读入内存
                        async with client.stream("GET", url) as response:
                            response.raise_for_status()
                            content_type = response.headers.get("content-type", "application/octet-stream")
                            content_length = response.headers.get("content-length")
                            if content_length and int(content_length) > self.max_file_size:
                                raise ToolError(f"File too large: {content_length} bytes", self.metadata.name)

                            temp_file = os.path.join(self.local_storage_dir, f"temp_{uuid.uuid4()}")
                            try:
                                with open(temp_file, 'wb') as f:
                                    async for chunk in response.aiter_bytes():
                                        f.write(chunk)
                                upload_params = {
                                    "file_path": temp_file,
                                    "destination_key": destination_key,
                                    "content_type": content_type,
                                    "metadata": {**metadata, "source_url": url},
                                    "public": public,
                                }
                                result = await self._upload_file(upload_params)
                            finally:
                                if os.path.exists(temp_file):
                                    os.unlink(temp_file)
                    return result
                except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError) as e:
                    # 远端关闭/超时等网络波动，退避重试
                    last_err = e
                    attempt += 1
                    backoff = min(3.0, 0.5 * (2 ** (attempt - 1)))
                    self.logger.warning(f"Download failed (attempt {attempt}/{max_retries}) for URL {url}: {e}")
                    await asyncio.sleep(backoff)
                except Exception as e:
                    raise ToolError(f"URL upload failed: {str(e)}", self.metadata.name)

            raise ToolError(f"URL upload failed after {max_retries} retries: {last_err}", self.metadata.name)
                
        except Exception as e:
            raise ToolError(f"URL upload failed: {str(e)}", self.metadata.name)

    def _safe_local_path(self, destination_key: str) -> str:
        """Build a safe local path within local_storage_dir, preventing path traversal."""
        key = (destination_key or "").lstrip("/").strip()
        if not key:
            raise ToolValidationError("destination_key cannot be empty", self.metadata.name)
        # Prevent traversal
        if ".." in key.replace("\\", "/").split("/"):
            raise ToolValidationError("destination_key contains invalid path traversal", self.metadata.name)
        base = Path(self.local_storage_dir).resolve()
        target = (base / key).resolve()
        if not str(target).startswith(str(base)):
            raise ToolValidationError("destination_key resolves outside local_storage_dir", self.metadata.name)
        return str(target)

    def _infer_file_extension(self, content_type: str, url: str) -> str:
        """Infer file extension from content-type or URL path. Best-effort and safe."""
        ctype = (content_type or "").split(";")[0].strip().lower()
        mapping = {
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/aac": ".aac",
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
            "audio/flac": ".flac",
            "audio/ogg": ".ogg",
            "audio/opus": ".opus",
            "video/mp4": ".mp4",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }
        ext = mapping.get(ctype)
        if ext:
            return ext
        try:
            path = urlparse(url).path
            suffix = Path(path).suffix
            if suffix and len(suffix) <= 6:
                return suffix
        except Exception:
            pass
        return ".bin"

    async def _download_from_url(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Download a remote URL to local storage and return a local file path.

        This action is intentionally storage-backend agnostic: it always produces a
        local file (for downstream ffmpeg mixing) and does not upload to S3/MinIO.
        """
        try:
            url = params["url"]
            destination_key = params.get("destination_key")
            overwrite = bool(params.get("overwrite", False))
            metadata = params.get("metadata", {}) or {}

            if not isinstance(url, str) or not url.strip():
                raise ToolValidationError("url is required for download_from_url", self.metadata.name)
            url = url.strip()
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                raise ToolValidationError("url must be http/https for download_from_url", self.metadata.name)

            # Configurable timeout / retries
            try:
                from ....core.config import settings as _app_settings
                http_timeout = int(getattr(_app_settings, "FILE_STORAGE_HTTP_TIMEOUT", 120))
            except Exception:
                http_timeout = 120
            timeout = httpx.Timeout(timeout=http_timeout)
            try:
                from ....core.config import settings as _dl_settings
                max_retries = int(getattr(_dl_settings, "FILE_STORAGE_DOWNLOAD_RETRIES", 3))
            except Exception:
                max_retries = 3

            # Prepare destination path
            if destination_key:
                final_path = self._safe_local_path(str(destination_key))
                os.makedirs(os.path.dirname(final_path), exist_ok=True)
                if os.path.exists(final_path) and not overwrite:
                    return {
                        "storage_type": "local_cache",
                        "local_path": final_path,
                        "file_path": final_path,
                        "url": f"file://{final_path}",
                        "source_url": url,
                        "metadata": dict(metadata),
                        "cached": True,
                    }
            else:
                os.makedirs(os.path.join(self.local_storage_dir, "downloads"), exist_ok=True)
                url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
                base_no_ext = os.path.join(self.local_storage_dir, "downloads", f"url_{url_hash}")
                final_path = base_no_ext + ".bin"

            attempt = 0
            last_err: Optional[Exception] = None
            while attempt < max_retries:
                try:
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                        async with client.stream("GET", url) as response:
                            response.raise_for_status()
                            content_type = response.headers.get("content-type", "application/octet-stream")
                            content_length = response.headers.get("content-length")
                            if content_length and int(content_length) > self.max_file_size:
                                raise ToolError(f"File too large: {content_length} bytes", self.metadata.name)

                            # If destination_key not provided, infer extension from headers/url.
                            if not destination_key:
                                ext = self._infer_file_extension(content_type, url)
                                final_path = base_no_ext + ext
                                if os.path.exists(final_path) and not overwrite:
                                    return {
                                        "storage_type": "local_cache",
                                        "local_path": final_path,
                                        "file_path": final_path,
                                        "url": f"file://{final_path}",
                                        "source_url": url,
                                        "metadata": dict(metadata),
                                        "cached": True,
                                    }

                            temp_path = os.path.join(self.local_storage_dir, f"temp_{uuid.uuid4()}")
                            hash_sha256 = hashlib.sha256()
                            size = 0
                            try:
                                with open(temp_path, "wb") as f:
                                    async for chunk in response.aiter_bytes():
                                        if not chunk:
                                            continue
                                        size += len(chunk)
                                        if size > self.max_file_size:
                                            raise ToolError(
                                                f"File too large: {size} bytes (max: {self.max_file_size})",
                                                self.metadata.name,
                                            )
                                        hash_sha256.update(chunk)
                                        f.write(chunk)
                                # Atomic move into place
                                os.makedirs(os.path.dirname(final_path), exist_ok=True)
                                if os.path.exists(final_path) and overwrite:
                                    os.unlink(final_path)
                                shutil.move(temp_path, final_path)
                            finally:
                                if os.path.exists(temp_path):
                                    try:
                                        os.unlink(temp_path)
                                    except Exception:
                                        pass

                            return {
                                "storage_type": "local_cache",
                                "local_path": final_path,
                                "file_path": final_path,
                                "url": f"file://{final_path}",
                                "source_url": url,
                                "content_type": content_type,
                                "file_size": int(size),
                                "file_hash": hash_sha256.hexdigest(),
                                "metadata": dict(metadata),
                                "cached": False,
                            }
                except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError) as e:
                    last_err = e
                    attempt += 1
                    backoff = min(3.0, 0.5 * (2 ** (attempt - 1)))
                    self.logger.warning(f"Download failed (attempt {attempt}/{max_retries}) for URL {url}: {e}")
                    await asyncio.sleep(backoff)
                except Exception as e:
                    raise ToolError(f"URL download failed: {str(e)}", self.metadata.name)

            raise ToolError(f"URL download failed after {max_retries} retries: {last_err}", self.metadata.name)
        except Exception as e:
            raise ToolError(f"URL download failed: {str(e)}", self.metadata.name)
    
    async def _upload_base64(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """上传Base64编码的文件"""
        try:
            base64_data = params["base64_data"]
            filename = params["filename"]
            content_type = params.get("content_type")
            
            # 解码Base64数据
            if base64_data.startswith("data:"):
                # 处理Data URL格式
                header, data = base64_data.split(",", 1)
                if not content_type:
                    content_type = header.split(";")[0].split(":")[1]
                base64_data = data
            
            try:
                file_data = base64.b64decode(base64_data)
            except Exception as e:
                raise ToolError(f"Invalid base64 data: {str(e)}", self.metadata.name)
            
            if len(file_data) > self.max_file_size:
                raise ToolError(f"File too large: {len(file_data)} bytes", self.metadata.name)
            
            # 写入临时文件
            temp_file = os.path.join(self.local_storage_dir, f"temp_{uuid.uuid4()}")
            
            try:
                with open(temp_file, 'wb') as f:
                    f.write(file_data)
                
                # 上传临时文件
                upload_params = {
                    "file_path": temp_file,
                    "content_type": content_type,
                    "metadata": {"original_filename": filename, "source": "base64"}
                }
                
                result = await self._upload_file(upload_params)
                
            finally:
                # 清理临时文件
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            
            return result
            
        except Exception as e:
            raise ToolError(f"Base64 upload failed: {str(e)}", self.metadata.name)
    
    async def _generate_download_url(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成下载URL"""
        try:
            file_key = params["file_key"]
            expiration = params.get("expiration", 3600)  # 默认1小时
            
            if self.storage_type == "local":
                file_path = os.path.join(self.local_storage_dir, file_key)
                if not os.path.exists(file_path):
                    raise ToolError(f"File not found: {file_key}", self.metadata.name)
                url = f"file://{file_path}"
                
            elif self.storage_type == "s3":
                url = self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.s3_bucket, 'Key': file_key},
                    ExpiresIn=expiration
                )
                
            elif self.storage_type == "minio":
                url = self.minio_client.presigned_get_object(
                    self.minio_bucket,
                    file_key,
                    expires=expiration
                )
                
            else:
                raise ToolError(f"Unsupported storage type: {self.storage_type}", self.metadata.name)
            
            return {
                "file_key": file_key,
                "download_url": url,
                "expiration": expiration,
                "storage_type": self.storage_type
            }
            
        except Exception as e:
            raise ToolError(f"URL generation failed: {str(e)}", self.metadata.name)
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件SHA256哈希"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "upload_file":
            if not parameters.get("file_path"):
                raise ToolValidationError("file_path is required for upload_file")
        
        elif action == "download_file":
            if not parameters.get("file_key"):
                raise ToolValidationError("file_key is required for download_file")
        
        elif action == "upload_from_url":
            if not parameters.get("url"):
                raise ToolValidationError("url is required for upload_from_url")

        elif action == "download_from_url":
            if not parameters.get("url"):
                raise ToolValidationError("url is required for download_from_url")
        
        elif action == "upload_base64":
            if not parameters.get("base64_data"):
                raise ToolValidationError("base64_data is required for upload_base64")
            if not parameters.get("filename"):
                raise ToolValidationError("filename is required for upload_base64")
        
        elif action == "generate_download_url":
            if not parameters.get("file_key"):
                raise ToolValidationError("file_key is required for generate_download_url")

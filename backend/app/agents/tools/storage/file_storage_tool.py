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

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError


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
        
        # 本地存储配置
        self.local_storage_dir = self.config.get("local_storage_dir", "/tmp/video_storage")
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
    
    def get_available_actions(self) -> List[str]:
        return [
            "upload_file",
            "download_file",
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
            
            # 下载文件到临时位置
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                
                # 获取文件信息
                content_type = response.headers.get("content-type", "application/octet-stream")
                content_length = response.headers.get("content-length")
                
                if content_length and int(content_length) > self.max_file_size:
                    raise ToolError(f"File too large: {content_length} bytes", self.metadata.name)
                
                # 生成临时文件
                temp_file = os.path.join(self.local_storage_dir, f"temp_{uuid.uuid4()}")
                
                try:
                    with open(temp_file, 'wb') as f:
                        f.write(response.content)
                    
                    # 上传临时文件
                    upload_params = {
                        "file_path": temp_file,
                        "destination_key": destination_key,
                        "content_type": content_type,
                        "metadata": {**metadata, "source_url": url}
                    }
                    
                    result = await self._upload_file(upload_params)
                    
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                
                return result
                
        except Exception as e:
            raise ToolError(f"URL upload failed: {str(e)}", self.metadata.name)
    
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
        
        elif action == "upload_base64":
            if not parameters.get("base64_data"):
                raise ToolValidationError("base64_data is required for upload_base64")
            if not parameters.get("filename"):
                raise ToolValidationError("filename is required for upload_base64")
        
        elif action == "generate_download_url":
            if not parameters.get("file_key"):
                raise ToolValidationError("file_key is required for generate_download_url")
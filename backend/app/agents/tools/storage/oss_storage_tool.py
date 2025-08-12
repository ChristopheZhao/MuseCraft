"""
阿里云OSS存储工具
"""

import os
import asyncio
import aiofiles
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from urllib.parse import urlparse
import mimetypes

try:
    import oss2
    from oss2.exceptions import OssError
except ImportError:
    oss2 = None
    OssError = Exception

from ..base_tool import AsyncTool, ToolInput, ToolError, ToolValidationError, ToolMetadata, ToolType
from ....core.config import settings


class OSSStorageTool(AsyncTool):
    """阿里云OSS对象存储工具"""
    
    @classmethod 
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="oss_storage",
            version="1.0.0",
            description="阿里云OSS对象存储工具，支持文件上传、下载、删除等操作",
            tool_type=ToolType.STORAGE,  # 使用正确的类型
            author="system",
            tags=["storage", "oss", "aliyun", "file-management"],
            capabilities=["upload", "download", "delete", "list", "get_url", "copy", "move"],
            limitations=["requires_api_key", "requires_oss2_library"]
        )
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(self.get_metadata(), config)
    
    def _initialize(self):
        """Initialize tool-specific resources"""
        if not oss2:
            self.logger.warning("oss2 library not installed, tool will not be functional")
            self._functional = False
            return
            
        # 配置检查 
        self.access_key_id = getattr(settings, 'OSS_ACCESS_KEY_ID', None)
        self.access_key_secret = getattr(settings, 'OSS_ACCESS_KEY_SECRET', None)
        self.endpoint = getattr(settings, 'OSS_ENDPOINT', None)
        self.bucket_name = getattr(settings, 'OSS_BUCKET_NAME', None)
        
        # 工具可以在没有配置时创建，但在使用时会检查
        self._functional = all([self.access_key_id, self.access_key_secret, self.endpoint, self.bucket_name])
        
        if not self._functional:
            self.logger.warning("OSS configuration incomplete, tool will not be functional")
            return
            
        # 初始化OSS客户端
        try:
            self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)
            self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)
        except Exception as e:
            self.logger.warning(f"Failed to initialize OSS client: {e}")
            
        # 默认配置
        self.default_expiry = 3600  # URL有效期1小时
        self.max_file_size = getattr(settings, 'MAX_FILE_SIZE', 100) * 1024 * 1024  # MB转字节
    
    def get_available_actions(self) -> List[str]:
        """Get list of available actions"""
        return ["upload", "download", "delete", "list", "get_url", "copy", "move"]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """Get input schema for a specific action"""
        schemas = {
            "upload": {
                "type": "object",
                "properties": {
                    "local_path": {"type": "string"},
                    "remote_path": {"type": "string"},
                    "content": {"type": "string"},
                    "content_type": {"type": "string"}
                },
                "required": ["remote_path"]
            },
            "download": {
                "type": "object", 
                "properties": {
                    "remote_path": {"type": "string"},
                    "local_path": {"type": "string"}
                },
                "required": ["remote_path"]
            }
        }
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行OSS存储操作"""
        # 检查工具是否功能可用
        if not self._functional:
            raise ToolError("OSSStorageTool not functional - configuration incomplete", self.metadata.name)
        
        if not hasattr(self, 'bucket'):
            raise ToolError("OSS not properly configured", self.metadata.name)
            
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "upload":
            return await self._upload_file(params)
        elif action == "download":
            return await self._download_file(params)
        elif action == "delete":
            return await self._delete_file(params)
        elif action == "list":
            return await self._list_files(params)
        elif action == "get_url":
            return await self._get_url(params)
        elif action == "copy":
            return await self._copy_file(params)
        elif action == "move":
            return await self._move_file(params)
        else:
            raise ToolValidationError(f"Unsupported action: {action}", self.metadata.name)
    
    async def _upload_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """上传文件到OSS"""
        local_path = params.get("local_path")
        remote_path = params.get("remote_path")
        content = params.get("content")  # 直接上传内容
        content_type = params.get("content_type")
        metadata = params.get("metadata", {})
        public_read = params.get("public_read", False)
        
        if not remote_path:
            raise ValueError("remote_path is required for upload")
        
        if not local_path and not content:
            raise ValueError("Either local_path or content is required for upload")
        
        try:
            # 运行在线程池中的同步操作
            def _sync_upload():
                # 设置对象ACL
                headers = {}
                if public_read:
                    headers['x-oss-object-acl'] = 'public-read'
                
                # 设置Content-Type
                if content_type:
                    headers['Content-Type'] = content_type
                elif local_path:
                    # 自动检测MIME类型
                    mime_type, _ = mimetypes.guess_type(local_path)
                    if mime_type:
                        headers['Content-Type'] = mime_type
                
                # 设置自定义元数据
                for key, value in metadata.items():
                    headers[f'x-oss-meta-{key}'] = str(value)
                
                if content:
                    # 上传内容
                    if isinstance(content, str):
                        content = content.encode('utf-8')
                    result = self.bucket.put_object(remote_path, content, headers=headers)
                else:
                    # 上传文件
                    with open(local_path, 'rb') as f:
                        result = self.bucket.put_object(remote_path, f, headers=headers)
                
                return result
            
            # 在线程池中执行同步操作
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync_upload)
            
            # 构造返回URL
            if public_read:
                url = f"https://{self.bucket_name}.{self.endpoint.replace('https://', '').replace('http://', '')}/{remote_path}"
            else:
                # 生成签名URL
                url = self.bucket.sign_url('GET', remote_path, self.default_expiry)
            
            return {
                "remote_path": remote_path,
                "url": url,
                "etag": result.etag,
                "public_read": public_read,
                "size": len(content) if content else os.path.getsize(local_path)
            }
            
        except OssError as e:
            raise Exception(f"OSS upload error: {e}")
    
    async def _download_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """从OSS下载文件"""
        remote_path = params.get("remote_path")
        local_path = params.get("local_path")
        
        if not remote_path:
            raise ValueError("remote_path is required for download")
        
        try:
            def _sync_download():
                if local_path:
                    # 下载到本地文件
                    result = self.bucket.get_object_to_file(remote_path, local_path)
                    return {
                        "local_path": local_path,
                        "content": None,
                        "size": os.path.getsize(local_path)
                    }
                else:
                    # 下载到内存
                    result = self.bucket.get_object(remote_path)
                    content = result.read()
                    return {
                        "local_path": None,
                        "content": content,
                        "size": len(content)
                    }
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync_download)
            
            result.update({
                "remote_path": remote_path,
                "success": True
            })
            
            return result
            
        except OssError as e:
            raise Exception(f"OSS download error: {e}")
    
    async def _delete_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """删除OSS文件"""
        remote_path = params.get("remote_path")
        
        if not remote_path:
            raise ValueError("remote_path is required for delete")
        
        try:
            def _sync_delete():
                result = self.bucket.delete_object(remote_path)
                return result
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _sync_delete)
            
            return {
                "remote_path": remote_path,
                "deleted": True
            }
            
        except OssError as e:
            raise Exception(f"OSS delete error: {e}")
    
    async def _list_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出OSS文件"""
        prefix = params.get("prefix", "")
        delimiter = params.get("delimiter", "")
        max_keys = params.get("max_keys", 100)
        marker = params.get("marker", "")
        
        try:
            def _sync_list():
                result = self.bucket.list_objects_v2(
                    prefix=prefix,
                    delimiter=delimiter,
                    max_keys=max_keys,
                    continuation_token=marker
                )
                
                files = []
                for obj in result.object_list:
                    files.append({
                        "name": obj.key,
                        "size": obj.size,
                        "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                        "etag": obj.etag,
                        "type": obj.type,
                        "storage_class": obj.storage_class
                    })
                
                folders = []
                for prefix_info in result.prefix_list:
                    folders.append({
                        "name": prefix_info.prefix,
                        "type": "folder"
                    })
                
                return {
                    "files": files,
                    "folders": folders,
                    "is_truncated": result.is_truncated,
                    "next_marker": result.next_continuation_token,
                    "total": len(files) + len(folders)
                }
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync_list)
            
            return result
            
        except OssError as e:
            raise Exception(f"OSS list error: {e}")
    
    async def _get_url(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取文件访问URL"""
        remote_path = params.get("remote_path")
        expiry = params.get("expiry", self.default_expiry)
        method = params.get("method", "GET")
        
        if not remote_path:
            raise ValueError("remote_path is required for get_url")
        
        try:
            def _sync_get_url():
                # 检查文件是否存在
                exists = self.bucket.object_exists(remote_path)
                if not exists:
                    return {
                        "exists": False,
                        "url": None,
                        "error": "File not found"
                    }
                
                # 生成签名URL
                url = self.bucket.sign_url(method, remote_path, expiry)
                
                # 获取文件信息
                meta = self.bucket.head_object(remote_path)
                
                return {
                    "exists": True,
                    "url": url,
                    "expiry": expiry,
                    "size": meta.content_length,
                    "content_type": meta.content_type,
                    "last_modified": meta.last_modified.isoformat() if meta.last_modified else None,
                    "etag": meta.etag
                }
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync_get_url)
            
            result["remote_path"] = remote_path
            return result
            
        except OssError as e:
            raise Exception(f"OSS get_url error: {e}")
    
    async def _copy_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """复制文件"""
        source_path = params.get("source_path")
        dest_path = params.get("dest_path")
        
        if not source_path or not dest_path:
            raise ValueError("source_path and dest_path are required for copy")
        
        try:
            def _sync_copy():
                # 构建源对象名称
                source_object = f"{self.bucket_name}/{source_path}"
                result = self.bucket.copy_object(source_object, dest_path)
                return result
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync_copy)
            
            return {
                "source_path": source_path,
                "dest_path": dest_path,
                "etag": result.etag,
                "copied": True
            }
            
        except OssError as e:
            raise Exception(f"OSS copy error: {e}")
    
    async def _move_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """移动文件（复制后删除）"""
        source_path = params.get("source_path")
        dest_path = params.get("dest_path")
        
        if not source_path or not dest_path:
            raise ValueError("source_path and dest_path are required for move")
        
        try:
            # 先复制
            copy_result = await self._copy_file({
                "source_path": source_path,
                "dest_path": dest_path
            })
            
            # 再删除源文件
            await self._delete_file({
                "remote_path": source_path
            })
            
            return {
                "source_path": source_path,
                "dest_path": dest_path,
                "etag": copy_result["etag"],
                "moved": True
            }
            
        except Exception as e:
            raise Exception(f"OSS move error: {e}")
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            def _sync_health_check():
                # 尝试列出bucket信息
                result = self.bucket.get_bucket_info()
                return result is not None
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync_health_check)
            
        except:
            return False
    
    def get_public_url(self, remote_path: str) -> str:
        """获取公开访问URL（不带签名）"""
        return f"https://{self.bucket_name}.{self.endpoint.replace('https://', '').replace('http://', '')}/{remote_path}"
    
    def estimate_cost(self, operations: int, storage_gb: float, traffic_gb: float = 0) -> Dict[str, float]:
        """估算OSS使用成本（人民币）"""
        # 阿里云OSS标准存储定价（2025年1月，华北2区域）
        pricing = {
            "storage_per_gb_month": 0.12,      # 标准存储每GB每月
            "request_per_10k": 0.01,           # 每万次请求
            "traffic_per_gb": 0.50,            # 外网流出流量每GB
        }
        
        storage_cost = storage_gb * pricing["storage_per_gb_month"]
        request_cost = (operations / 10000) * pricing["request_per_10k"]
        traffic_cost = traffic_gb * pricing["traffic_per_gb"]
        
        total_cost = storage_cost + request_cost + traffic_cost
        
        return {
            "storage_cost": storage_cost,
            "request_cost": request_cost,
            "traffic_cost": traffic_cost,
            "total_cost": total_cost,
            "currency": "CNY"
        }


# 导出工具实例
try:
    oss_storage = OSSStorageTool()
except Exception as e:
    # 如果配置不完整，创建一个占位符
    oss_storage = None
    print(f"OSS Storage Tool initialization failed: {e}")
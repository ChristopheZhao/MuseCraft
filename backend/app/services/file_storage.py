"""
File Storage Service for managing uploads and generated files
"""
import os
import aiofiles
import aiohttp
import hashlib
import base64
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image
import logging

from ..core.config import settings


class FileStorageError(Exception):
    """Base exception for file storage errors"""
    pass


class FileStorageService:
    """Service for handling file storage operations"""
    
    def __init__(self):
        self.logger = logging.getLogger("file_storage")
        
        # Create storage directories
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure all storage directories exist"""
        directories = {
            settings.UPLOAD_PATH,
            settings.GENERATED_PATH,
            settings.TEMP_PATH,
            settings.FINAL_OUTPUT_ROOT,
            settings.FINAL_VIDEO_OUTPUT_PATH,
            settings.FINAL_AUDIO_OUTPUT_PATH,
        }

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
            try:
                # Ensure directories are writable while their contents can later be
                # tightened (e.g. final assets set as read-only).
                Path(directory).chmod(0o755)
            except Exception:
                # Permission adjustments are best-effort only; ignore failures on
                # non-POSIX filesystems.
                pass

    def get_final_output_dir(self, asset_type: str = "video") -> Path:
        """Return the directory reserved for immutable final deliverables."""

        if asset_type == "audio":
            target = Path(settings.FINAL_AUDIO_OUTPUT_PATH)
        else:
            target = Path(settings.FINAL_VIDEO_OUTPUT_PATH)

        target.mkdir(parents=True, exist_ok=True)
        return target
    
    async def save_uploaded_file(
        self, 
        file_content: bytes, 
        filename: str,
        subfolder: str = "uploads"
    ) -> str:
        """Save uploaded file to storage"""
        
        try:
            # Generate safe filename
            safe_filename = self._sanitize_filename(filename)
            
            # Determine storage path
            if subfolder == "uploads":
                storage_dir = settings.UPLOAD_PATH
            elif subfolder == "generated":
                storage_dir = settings.GENERATED_PATH
            else:
                storage_dir = settings.TEMP_PATH
            
            file_path = os.path.join(storage_dir, safe_filename)
            
            # Save file
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(file_content)
            
            self.logger.info(f"Saved file: {file_path}")
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to save file {filename}: {str(e)}")
            raise FileStorageError(f"Failed to save file: {str(e)}") from e
    
    async def download_and_save_image(
        self, 
        image_url: str, 
        filename: str
    ) -> str:
        """Download image from URL and save to storage"""
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        raise FileStorageError(f"Failed to download image: HTTP {response.status}")
                    
                    image_data = await response.read()
            
            # Save to generated files directory
            file_path = await self.save_uploaded_file(
                image_data, filename, subfolder="generated"
            )
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to download and save image {image_url}: {str(e)}")
            raise FileStorageError(f"Failed to download image: {str(e)}") from e
    
    async def download_and_save_video(
        self, 
        video_url: str, 
        filename: str
    ) -> str:
        """Download video from URL and save to storage"""
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url) as response:
                    if response.status != 200:
                        raise FileStorageError(f"Failed to download video: HTTP {response.status}")
                    
                    video_data = await response.read()
            
            # Save to generated files directory
            file_path = await self.save_uploaded_file(
                video_data, filename, subfolder="generated"
            )
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to download and save video {video_url}: {str(e)}")
            raise FileStorageError(f"Failed to download video: {str(e)}") from e
    
    async def download_and_save_audio(
        self, 
        audio_url: str, 
        filename: str
    ) -> str:
        """Download audio from URL and save to storage"""
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_url) as response:
                    if response.status != 200:
                        raise FileStorageError(f"Failed to download audio: HTTP {response.status}")
                    
                    audio_data = await response.read()
            
            # Save to generated files directory
            file_path = await self.save_uploaded_file(
                audio_data, filename, subfolder="generated"
            )
            
            self.logger.info(f"Downloaded and saved audio: {filename} ({len(audio_data)} bytes)")
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to download and save audio {audio_url}: {str(e)}")
            raise FileStorageError(f"Failed to download audio: {str(e)}") from e
    
    async def save_video_data(
        self, 
        video_data: bytes, 
        filename: str
    ) -> str:
        """Save video data to storage"""
        
        try:
            file_path = await self.save_uploaded_file(
                video_data, filename, subfolder="generated"
            )
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to save video data: {str(e)}")
            raise FileStorageError(f"Failed to save video data: {str(e)}") from e
    
    async def save_base64_image(
        self, 
        base64_data: str, 
        filename: str
    ) -> str:
        """Save base64 encoded image to storage"""
        
        try:
            # Decode base64 data
            image_data = base64.b64decode(base64_data)
            
            # Save to generated files directory
            file_path = await self.save_uploaded_file(
                image_data, filename, subfolder="generated"
            )
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to save base64 image {filename}: {str(e)}")
            raise FileStorageError(f"Failed to save base64 image: {str(e)}") from e
    
    async def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get file information including size, type, dimensions for images"""
        
        try:
            if not os.path.exists(file_path):
                raise FileStorageError(f"File not found: {file_path}")
            
            file_stats = os.stat(file_path)
            file_info = {
                "size": file_stats.st_size,
                "mime_type": self._get_mime_type(file_path),
                "created_at": file_stats.st_ctime,
                "modified_at": file_stats.st_mtime
            }
            
            # Add image dimensions if it's an image
            if self._is_image(file_path):
                try:
                    with Image.open(file_path) as img:
                        file_info["width"] = img.width
                        file_info["height"] = img.height
                        file_info["format"] = img.format
                except Exception as e:
                    self.logger.warning(f"Failed to get image dimensions: {str(e)}")
            
            return file_info
            
        except Exception as e:
            self.logger.error(f"Failed to get file info for {file_path}: {str(e)}")
            raise FileStorageError(f"Failed to get file info: {str(e)}") from e
    
    async def calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of file"""
        
        try:
            hash_sha256 = hashlib.sha256()
            
            async with aiofiles.open(file_path, 'rb') as f:
                while chunk := await f.read(8192):
                    hash_sha256.update(chunk)
            
            return hash_sha256.hexdigest()
            
        except Exception as e:
            self.logger.error(f"Failed to calculate checksum for {file_path}: {str(e)}")
            raise FileStorageError(f"Failed to calculate checksum: {str(e)}") from e
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from storage"""
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.info(f"Deleted file: {file_path}")
                return True
            else:
                self.logger.warning(f"File not found for deletion: {file_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to delete file {file_path}: {str(e)}")
            raise FileStorageError(f"Failed to delete file: {str(e)}") from e
    
    async def move_file(self, source_path: str, destination_path: str) -> str:
        """Move file from source to destination"""
        
        try:
            # Ensure destination directory exists
            destination_dir = os.path.dirname(destination_path)
            Path(destination_dir).mkdir(parents=True, exist_ok=True)
            
            # Move file
            os.rename(source_path, destination_path)
            
            self.logger.info(f"Moved file from {source_path} to {destination_path}")
            return destination_path
            
        except Exception as e:
            self.logger.error(f"Failed to move file from {source_path} to {destination_path}: {str(e)}")
            raise FileStorageError(f"Failed to move file: {str(e)}") from e
    
    async def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """Clean up temporary files older than specified age"""
        
        import time
        
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            deleted_count = 0
            
            temp_dir = Path(settings.TEMP_PATH)
            
            for file_path in temp_dir.glob("*"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    
                    if file_age > max_age_seconds:
                        try:
                            file_path.unlink()
                            deleted_count += 1
                            self.logger.info(f"Cleaned up temp file: {file_path}")
                        except Exception as e:
                            self.logger.warning(f"Failed to delete temp file {file_path}: {str(e)}")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup temp files: {str(e)}")
            return 0
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent security issues"""
        
        # Remove path components
        filename = os.path.basename(filename)
        
        # Replace potentially dangerous characters
        dangerous_chars = ['..', '/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in dangerous_chars:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[:255-len(ext)] + ext
        
        return filename
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type based on file extension"""
        
        extension = os.path.splitext(file_path)[1].lower()
        
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.webm': 'video/webm',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.pdf': 'application/pdf'
        }
        
        return mime_types.get(extension, 'application/octet-stream')
    
    def _is_image(self, file_path: str) -> bool:
        """Check if file is an image based on extension"""
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}
        extension = os.path.splitext(file_path)[1].lower()
        return extension in image_extensions
    
    def get_public_url(self, file_path: str, base_url: str = "") -> str:
        """Get public URL for a file"""
        
        # Extract filename from path
        filename = os.path.basename(file_path)
        
        # Determine subfolder based on path
        if settings.UPLOAD_PATH in file_path:
            subfolder = "uploads"
        elif settings.GENERATED_PATH in file_path:
            subfolder = "generated"
        else:
            subfolder = "temp"
        
        if base_url:
            return f"{base_url.rstrip('/')}/files/{subfolder}/{filename}"
        
        return f"/files/{subfolder}/{filename}"
    
    async def download_and_save_file(
        self,
        file_url: str,
        output_path: str
    ) -> str:
        """Download file from URL and save to specified path"""
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status != 200:
                        raise FileStorageError(f"Failed to download file: HTTP {response.status}")
                    
                    file_data = await response.read()
            
            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # Save file
            async with aiofiles.open(output_path, 'wb') as f:
                await f.write(file_data)
            
            self.logger.info(f"Downloaded and saved file: {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"Failed to download and save file {file_url}: {str(e)}")
            raise FileStorageError(f"Failed to download file: {str(e)}") from e
    
    def get_output_path(self, filename: str, subfolder: str = "generated") -> str:
        """Get output file path for generated content"""
        
        # Generate safe filename
        safe_filename = self._sanitize_filename(filename)
        
        # Determine storage directory
        if subfolder == "uploads":
            storage_dir = settings.UPLOAD_PATH
        elif subfolder == "generated":
            storage_dir = settings.GENERATED_PATH
        elif subfolder == "temp":
            storage_dir = settings.TEMP_PATH
        else:
            storage_dir = settings.GENERATED_PATH  # Default to generated
        
        # Ensure directory exists
        Path(storage_dir).mkdir(parents=True, exist_ok=True)
        
        file_path = os.path.join(storage_dir, safe_filename)
        return file_path

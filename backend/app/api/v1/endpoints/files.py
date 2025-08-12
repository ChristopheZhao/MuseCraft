"""
File management API endpoints
"""
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ....core.database import get_db
from ....models import Resource, Task
from ....services.file_storage import FileStorageService, FileStorageError
from ....core.config import settings


router = APIRouter()


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    task_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Upload a file"""
    
    file_storage = FileStorageService()
    
    try:
        # Validate file size
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)
        
        if file_size_mb > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"File size ({file_size_mb:.1f}MB) exceeds maximum allowed size ({settings.MAX_FILE_SIZE}MB)"
            )
        
        # Save file
        file_path = await file_storage.save_uploaded_file(
            content, file.filename, subfolder="uploads"
        )
        
        # Get file info
        file_info = await file_storage.get_file_info(file_path)
        
        # Create resource record if task_id provided
        resource = None
        if task_id:
            # Verify task exists
            task_query = select(Task).where(Task.task_id == task_id)
            task_result = await db.execute(task_query)
            task = task_result.scalar_one_or_none()
            
            if task:
                from ....models import ResourceType
                
                # Determine resource type
                resource_type = ResourceType.IMAGE
                if file_info["mime_type"].startswith("video/"):
                    resource_type = ResourceType.VIDEO
                elif file_info["mime_type"].startswith("audio/"):
                    resource_type = ResourceType.AUDIO
                elif file_info["mime_type"].startswith("text/"):
                    resource_type = ResourceType.TEXT
                
                # Create resource record
                resource = Resource(
                    task_id=task.id,
                    filename=os.path.basename(file_path),
                    original_filename=file.filename,
                    file_path=file_path,
                    resource_type=resource_type,
                    mime_type=file_info["mime_type"],
                    file_size=file_info["size"],
                    width=file_info.get("width"),
                    height=file_info.get("height"),
                    processing_status="completed",
                    is_generated=False
                )
                
                db.add(resource)
                await db.commit()
                await db.refresh(resource)
        
        return {
            "message": "File uploaded successfully",
            "filename": os.path.basename(file_path),
            "file_size": file_info["size"],
            "mime_type": file_info["mime_type"],
            "file_path": file_path,
            "resource_id": resource.id if resource else None,
            "public_url": file_storage.get_public_url(file_path)
        }
        
    except FileStorageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/uploads/{filename}")
async def get_uploaded_file(filename: str):
    """Serve uploaded files"""
    
    file_path = os.path.join(settings.UPLOAD_PATH, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.get("/generated/{filename}")
async def get_generated_file(filename: str):
    """Serve generated files"""
    
    file_path = os.path.join(settings.GENERATED_PATH, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.get("/temp/{filename}")
async def get_temp_file(filename: str):
    """Serve temporary files"""
    
    file_path = os.path.join(settings.TEMP_PATH, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.get("/resource/{resource_id}")
async def get_resource_file(
    resource_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Serve file by resource ID"""
    
    # Get resource
    query = select(Resource).where(Resource.id == resource_id)
    result = await db.execute(query)
    resource = result.scalar_one_or_none()
    
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    if not os.path.exists(resource.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Update access tracking
    resource.mark_as_accessed()
    await db.commit()
    
    return FileResponse(
        path=resource.file_path,
        filename=resource.filename,
        media_type=resource.mime_type or "application/octet-stream"
    )


@router.delete("/resource/{resource_id}")
async def delete_resource_file(
    resource_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a resource and its file"""
    
    # Get resource
    query = select(Resource).where(Resource.id == resource_id)
    result = await db.execute(query)
    resource = result.scalar_one_or_none()
    
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    # Delete file
    file_storage = FileStorageService()
    
    try:
        await file_storage.delete_file(resource.file_path)
    except FileStorageError as e:
        # Log error but continue with database deletion
        pass
    
    # Delete resource record
    await db.delete(resource)
    await db.commit()
    
    return {"message": "Resource deleted successfully"}


@router.get("/storage/stats")
async def get_storage_stats():
    """Get storage statistics"""
    
    def get_directory_size(path: str) -> int:
        """Calculate total size of directory"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
        except OSError:
            pass
        return total_size
    
    def get_file_count(path: str) -> int:
        """Count files in directory"""
        count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                count += len(filenames)
        except OSError:
            pass
        return count
    
    uploads_size = get_directory_size(settings.UPLOAD_PATH)
    generated_size = get_directory_size(settings.GENERATED_PATH)
    temp_size = get_directory_size(settings.TEMP_PATH)
    
    uploads_count = get_file_count(settings.UPLOAD_PATH)
    generated_count = get_file_count(settings.GENERATED_PATH)
    temp_count = get_file_count(settings.TEMP_PATH)
    
    return {
        "uploads": {
            "size_bytes": uploads_size,
            "size_mb": round(uploads_size / (1024 * 1024), 2),
            "file_count": uploads_count
        },
        "generated": {
            "size_bytes": generated_size,
            "size_mb": round(generated_size / (1024 * 1024), 2),
            "file_count": generated_count
        },
        "temp": {
            "size_bytes": temp_size,
            "size_mb": round(temp_size / (1024 * 1024), 2),
            "file_count": temp_count
        },
        "total": {
            "size_bytes": uploads_size + generated_size + temp_size,
            "size_mb": round((uploads_size + generated_size + temp_size) / (1024 * 1024), 2),
            "file_count": uploads_count + generated_count + temp_count
        }
    }


@router.post("/cleanup/temp")
async def cleanup_temp_files():
    """Clean up temporary files"""
    
    file_storage = FileStorageService()
    
    try:
        deleted_count = await file_storage.cleanup_temp_files()
        return {
            "message": f"Cleaned up {deleted_count} temporary files",
            "deleted_count": deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")
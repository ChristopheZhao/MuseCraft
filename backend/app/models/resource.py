"""
Resource model for managing generated and uploaded files
"""
import enum
from sqlalchemy import Column, String, Text, JSON, Enum, Integer, ForeignKey, BigInteger, Boolean
from sqlalchemy.orm import relationship

from .base import BaseModel


class ResourceType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE_OVER = "voice_over"
    TEXT = "text"
    SCRIPT = "script"
    THUMBNAIL = "thumbnail"
    TEMP_FILE = "temp_file"


class Resource(BaseModel):
    __tablename__ = "resources"
    
    # Relationships
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    task = relationship("Task", back_populates="resources")
    
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=True)
    scene = relationship("Scene", back_populates="resources")
    
    # File information
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255))
    file_path = Column(String(500), nullable=False)
    file_url = Column(String(500))  # For external URLs or CDN
    
    # File metadata
    resource_type = Column(Enum(ResourceType), nullable=False)
    mime_type = Column(String(100))
    file_size = Column(BigInteger)  # in bytes
    checksum = Column(String(64))  # SHA256 hash
    
    # Media metadata
    width = Column(Integer)  # for images/videos
    height = Column(Integer)  # for images/videos
    duration = Column(Integer)  # for videos/audio in seconds
    frame_rate = Column(Integer)  # for videos
    bit_rate = Column(Integer)  # for videos/audio
    
    # Generation metadata
    generation_parameters = Column(JSON, default=dict)  # AI generation params
    generation_model = Column(String(100))  # Which AI model was used
    generation_prompt = Column(Text)  # Original prompt used
    generation_seed = Column(Integer)  # For reproducibility
    
    # Quality and processing
    quality_score = Column(Integer)  # 1-10 scale
    processing_status = Column(String(50), default="pending")  # pending, processing, completed, failed
    processing_metadata = Column(JSON, default=dict)  # Processing information
    
    # Storage and access
    storage_provider = Column(String(50), default="local")  # local, s3, etc.
    access_permissions = Column(String(50), default="private")  # private, public, shared
    expiry_date = Column(Integer)  # Unix timestamp for temporary files
    
    # Usage tracking
    download_count = Column(Integer, default=0)
    last_accessed = Column(Integer)  # Unix timestamp
    
    # Flags
    is_temporary = Column(Boolean, default=False)
    is_generated = Column(Boolean, default=True)  # vs uploaded
    is_final_output = Column(Boolean, default=False)
    
    # Relationships and dependencies
    parent_resource_id = Column(Integer, ForeignKey("resources.id"), nullable=True)
    children = relationship("Resource", remote_side="Resource.parent_resource_id")
    
    def __repr__(self):
        return f"<Resource(id={self.id}, filename={self.filename}, type={self.resource_type})>"
    
    @property
    def file_size_mb(self) -> float:
        """File size in megabytes"""
        if self.file_size:
            return self.file_size / (1024 * 1024)
        return 0.0
    
    @property
    def is_image(self) -> bool:
        return self.resource_type == ResourceType.IMAGE
    
    @property
    def is_video(self) -> bool:
        return self.resource_type == ResourceType.VIDEO
    
    @property
    def is_audio(self) -> bool:
        return self.resource_type in {ResourceType.AUDIO, ResourceType.VOICE_OVER}

    @property
    def is_voice_over(self) -> bool:
        if self.resource_type == ResourceType.VOICE_OVER:
            return True
        params = self.generation_parameters or {}
        if isinstance(params, dict) and params.get("audio_role") == "voice_over":
            return True
        return False
    
    def update_processing_status(self, status: str, metadata: dict = None):
        """Update processing status and metadata"""
        self.processing_status = status
        if metadata:
            if not self.processing_metadata:
                self.processing_metadata = {}
            self.processing_metadata.update(metadata)
    
    def mark_as_accessed(self):
        """Update access tracking"""
        import time
        self.last_accessed = int(time.time())
        self.download_count += 1
    
    def get_public_url(self, base_url: str = "") -> str:
        """Get public URL for the resource"""
        if self.file_url:
            return self.file_url
        
        if base_url:
            return f"{base_url.rstrip('/')}/files/{self.filename}"
        
        return f"/files/{self.filename}"

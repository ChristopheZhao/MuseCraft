"""
Scene model for video scenes and segments
"""
import enum
from sqlalchemy import Column, String, Text, JSON, Enum, Integer, ForeignKey, Float
from sqlalchemy.orm import relationship

from .base import BaseModel


class SceneType(str, enum.Enum):
    INTRO = "intro"
    MAIN_CONTENT = "main_content"
    TRANSITION = "transition" 
    OUTRO = "outro"
    BACKGROUND = "background"


class Scene(BaseModel):
    __tablename__ = "scenes"
    
    # Task relationship
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    task = relationship("Task", back_populates="scenes")
    
    # Scene basic information
    scene_number = Column(Integer, nullable=False)  # Order in video
    scene_type = Column(Enum(SceneType), nullable=False)
    title = Column(String(255))
    description = Column(Text)
    
    # Content information
    script_text = Column(Text)
    narrative_description = Column(Text)
    visual_description = Column(Text)
    
    # Timing information
    duration = Column(Float)  # in seconds
    start_time = Column(Float, default=0.0)  # in seconds from video start
    end_time = Column(Float)  # in seconds from video start
    
    # Visual elements
    background_prompt = Column(Text)  # AI prompt for background
    character_descriptions = Column(JSON, default=list)  # List of characters
    props_and_objects = Column(JSON, default=list)  # List of props/objects
    mood_and_atmosphere = Column(String(100))  # Overall mood
    
    # Audio elements
    voice_over_text = Column(Text)
    background_music_style = Column(String(100))
    sound_effects = Column(JSON, default=list)  # List of sound effects
    
    # Camera and cinematography
    camera_angle = Column(String(50))  # close-up, wide shot, etc.
    camera_movement = Column(String(50))  # static, pan, zoom, etc.
    lighting_style = Column(String(50))  # natural, dramatic, soft, etc.
    
    # Style and aesthetics
    art_style = Column(String(100))  # realistic, cartoon, anime, etc.
    color_palette = Column(JSON, default=list)  # List of dominant colors
    visual_effects = Column(JSON, default=list)  # List of VFX needed
    
    # Generation metadata
    generation_parameters = Column(JSON, default=dict)  # AI generation params
    quality_metrics = Column(JSON, default=dict)  # Quality assessment
    
    # Relationships
    resources = relationship("Resource", back_populates="scene")
    
    def __repr__(self):
        return f"<Scene(id={self.id}, scene_number={self.scene_number}, type={self.scene_type})>"
    
    @property
    def calculated_end_time(self) -> float:
        """Calculate end time based on start time and duration"""
        if self.start_time is not None and self.duration is not None:
            return self.start_time + self.duration
        return self.end_time or 0.0
    
    def update_timing(self, start_time: float, duration: float):
        """Update scene timing"""
        self.start_time = start_time
        self.duration = duration
        self.end_time = start_time + duration
    
    def to_generation_prompt(self) -> str:
        """Generate AI prompt for this scene"""
        prompt_parts = []
        
        if self.visual_description:
            prompt_parts.append(f"Visual: {self.visual_description}")
        
        if self.background_prompt:
            prompt_parts.append(f"Background: {self.background_prompt}")
        
        if self.mood_and_atmosphere:
            prompt_parts.append(f"Mood: {self.mood_and_atmosphere}")
        
        if self.art_style:
            prompt_parts.append(f"Style: {self.art_style}")
        
        if self.camera_angle:
            prompt_parts.append(f"Camera: {self.camera_angle}")
        
        if self.lighting_style:
            prompt_parts.append(f"Lighting: {self.lighting_style}")
        
        return ". ".join(prompt_parts)
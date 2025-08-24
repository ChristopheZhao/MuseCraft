"""
Application configuration settings
"""
from typing import Optional, List
from pydantic import field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os
import pathlib

# IMPORTANT: Load environment variables BEFORE importing anything else
# Load from project root directory (the only .env file)
root_env_path = pathlib.Path(__file__).parent.parent.parent.parent / '.env'
if root_env_path.exists():
    load_dotenv(root_env_path, override=True)
    # print(f"Loaded .env from: {root_env_path}")  # Remove print in production
else:
    # Fallback: try current working directory
    load_dotenv(override=True)

# Now import decouple after env vars are loaded
from decouple import config


class Settings(BaseSettings):
    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Short Video Maker API"
    VERSION: str = "1.0.0"
    DEBUG: bool = config("DEBUG", default=False, cast=bool)
    SECRET_KEY: str = config("SECRET_KEY", default="your-secret-key-here")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=30, cast=int)
    
    # CORS Settings
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://127.0.0.1:3000",
    ]
    
    # Database Settings
    DATABASE_URL: str = config("DATABASE_URL", default="postgresql://user:password@localhost:5432/short_video_maker")
    DATABASE_HOST: str = config("DATABASE_HOST", default="localhost")
    DATABASE_PORT: int = config("DATABASE_PORT", default=5432, cast=int)
    DATABASE_NAME: str = config("DATABASE_NAME", default="short_video_maker")
    DATABASE_USER: str = config("DATABASE_USER", default="user")
    DATABASE_PASSWORD: str = config("DATABASE_PASSWORD", default="password")
    
    # Redis Settings
    REDIS_URL: str = config("REDIS_URL", default="redis://localhost:6379/0")
    REDIS_HOST: str = config("REDIS_HOST", default="localhost")
    REDIS_PORT: int = config("REDIS_PORT", default=6379, cast=int)
    REDIS_DB: int = config("REDIS_DB", default=0, cast=int)
    
    # File Storage Settings
    STORAGE_TYPE: str = config("STORAGE_TYPE", default="local")  # local or s3
    UPLOAD_PATH: str = config("UPLOAD_PATH", default="./storage/uploads")
    GENERATED_PATH: str = config("GENERATED_PATH", default="./storage/generated")
    TEMP_PATH: str = config("TEMP_PATH", default="./storage/temp")
    MAX_FILE_SIZE: int = config("MAX_FILE_SIZE", default=100, cast=int)  # MB
    
    # AWS S3 Settings
    AWS_ACCESS_KEY_ID: Optional[str] = config("AWS_ACCESS_KEY_ID", default=None)
    AWS_SECRET_ACCESS_KEY: Optional[str] = config("AWS_SECRET_ACCESS_KEY", default=None)
    AWS_REGION: str = config("AWS_REGION", default="us-east-1")
    S3_BUCKET_NAME: Optional[str] = config("S3_BUCKET_NAME", default=None)
    
    # Alibaba Cloud OSS Settings
    OSS_ACCESS_KEY_ID: Optional[str] = config("OSS_ACCESS_KEY_ID", default=None)
    OSS_ACCESS_KEY_SECRET: Optional[str] = config("OSS_ACCESS_KEY_SECRET", default=None)
    OSS_ENDPOINT: str = config("OSS_ENDPOINT", default="https://oss-cn-beijing.aliyuncs.com")
    OSS_BUCKET_NAME: Optional[str] = config("OSS_BUCKET_NAME", default=None)
    OSS_REGION: str = config("OSS_REGION", default="cn-beijing")
    
    # AI Service APIs - International
    OPENAI_API_KEY: Optional[str] = config("OPENAI_API_KEY", default=None)
    ANTHROPIC_API_KEY: Optional[str] = config("ANTHROPIC_API_KEY", default=None)
    STABILITY_API_KEY: Optional[str] = config("STABILITY_API_KEY", default=None)
    RUNWAY_API_KEY: Optional[str] = config("RUNWAY_API_KEY", default=None)
    PIKA_LABS_API_KEY: Optional[str] = config("PIKA_LABS_API_KEY", default=None)
    
    # AI Service APIs - China Domestic
    KIMI_API_KEY: Optional[str] = config("KIMI_API_KEY", default=None)
    KIMI_BASE_URL: str = config("KIMI_BASE_URL", default="https://api.moonshot.cn/v1")
    GLM_API_KEY: Optional[str] = config("GLM_API_KEY", default=None)
    GLM_BASE_URL: str = config("GLM_BASE_URL", default="https://open.bigmodel.cn/api/paas/v4")
    GLM_DEFAULT_MODEL: str = config("GLM_DEFAULT_MODEL", default="glm-4-plus")
    DOUBAO_API_KEY: Optional[str] = config("DOUBAO_API_KEY", default=None)
    DOUBAO_BASE_URL: str = config("DOUBAO_BASE_URL", default="https://ark.cn-beijing.volces.com")
    
    # Image Generation APIs
    MIDJOURNEY_API_KEY: Optional[str] = config("MIDJOURNEY_API_KEY", default=None)
    JIMENG_API_KEY: Optional[str] = config("JIMENG_API_KEY", default=None)
    JIMENG_BASE_URL: str = config("JIMENG_BASE_URL", default="https://api.302.ai/doubao/drawing")
    
    # Video Generation APIs
    MINIMAX_API_KEY: Optional[str] = config("MINIMAX_API_KEY", default=None)
    MINIMAX_BASE_URL: str = config("MINIMAX_BASE_URL", default="https://api.minimaxi.com/v1")
    HUNYUAN_VIDEO_API_KEY: Optional[str] = config("HUNYUAN_VIDEO_API_KEY", default=None)
    HUNYUAN_VIDEO_BASE_URL: str = config("HUNYUAN_VIDEO_BASE_URL", default="https://api.hunyuan.cloud.tencent.com/v1")
    DOUBAO_VIDEO_API_KEY: Optional[str] = config("DOUBAO_VIDEO_API_KEY", default=None)
    DOUBAO_VIDEO_BASE_URL: str = config("DOUBAO_VIDEO_BASE_URL", default="https://ark.cn-beijing.volces.com")
    
    # Audio Generation APIs
    SUNO_API_KEY: Optional[str] = config("SUNO_API_KEY", default=None)
    SUNO_BASE_URL: str = config("SUNO_BASE_URL", default="https://api.sunoapi.org")
    
    # Enhanced AI Service Settings
    AI_SERVICE_TIMEOUT: int = config("AI_SERVICE_TIMEOUT", default=120, cast=int)
    AI_SERVICE_MAX_RETRIES: int = config("AI_SERVICE_MAX_RETRIES", default=3, cast=int)
    AI_CACHE_TTL: int = config("AI_CACHE_TTL", default=3600, cast=int)  # 1 hour
    
    # Workflow Optimization Settings
    WORKFLOW_OPTIMIZATION_LEVEL: str = config("WORKFLOW_OPTIMIZATION_LEVEL", default="balanced")  # conservative, balanced, aggressive
    WORKFLOW_EXECUTION_STRATEGY: str = config("WORKFLOW_EXECUTION_STRATEGY", default="adaptive")  # sequential, parallel, adaptive, pipeline
    MAX_CONCURRENT_AGENTS: int = config("MAX_CONCURRENT_AGENTS", default=4, cast=int)
    ENABLE_WORKFLOW_CACHING: bool = config("ENABLE_WORKFLOW_CACHING", default=True, cast=bool)
    
    # Quality Control Settings
    ENABLE_QUALITY_CONTROL: bool = config("ENABLE_QUALITY_CONTROL", default=True, cast=bool)
    QUALITY_CONTROL_THRESHOLD: float = config("QUALITY_CONTROL_THRESHOLD", default=5.0, cast=float)
    CONTENT_SAFETY_LEVEL: str = config("CONTENT_SAFETY_LEVEL", default="moderate")  # strict, moderate, permissive
    ENABLE_HUMAN_REVIEW: bool = config("ENABLE_HUMAN_REVIEW", default=True, cast=bool)
    
    # Monitoring and Analytics Settings
    ENABLE_PERFORMANCE_MONITORING: bool = config("ENABLE_PERFORMANCE_MONITORING", default=True, cast=bool)
    METRICS_RETENTION_DAYS: int = config("METRICS_RETENTION_DAYS", default=30, cast=int)
    ENABLE_COST_TRACKING: bool = config("ENABLE_COST_TRACKING", default=True, cast=bool)
    COST_ALERT_THRESHOLD: float = config("COST_ALERT_THRESHOLD", default=10.0, cast=float)  # USD per hour
    
    # Error Recovery Settings
    ENABLE_ERROR_RECOVERY: bool = config("ENABLE_ERROR_RECOVERY", default=True, cast=bool)
    ERROR_RECOVERY_MAX_ATTEMPTS: int = config("ERROR_RECOVERY_MAX_ATTEMPTS", default=3, cast=int)
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = config("CIRCUIT_BREAKER_FAILURE_THRESHOLD", default=5, cast=int)
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = config("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", default=60, cast=int)  # seconds
    
    # Resource Management Settings
    MAX_MEMORY_USAGE_PERCENT: int = config("MAX_MEMORY_USAGE_PERCENT", default=85, cast=int)
    MAX_CPU_USAGE_PERCENT: int = config("MAX_CPU_USAGE_PERCENT", default=80, cast=int)
    MAX_DISK_USAGE_PERCENT: int = config("MAX_DISK_USAGE_PERCENT", default=90, cast=int)
    
    # Celery Settings
    CELERY_BROKER_URL: str = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
    
    # WebSocket Settings
    WEBSOCKET_PATH: str = config("WEBSOCKET_PATH", default="/ws")
    
    # Public API URL for callbacks
    PUBLIC_API_URL: str = config("PUBLIC_API_URL", default="http://localhost:8000")
    
    # Logging Settings
    LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")
    LOG_FORMAT: str = config("LOG_FORMAT", default="json")
    
    # Video Generation System Configuration
    VIDEO_GENERATION_PROVIDER: str = config("VIDEO_GENERATION_PROVIDER", default="cogvideox-3")
    VIDEO_DURATION_CAPABILITIES: List[int] = [5, 10]  # Available duration options for current provider
    VIDEO_AMPLIFICATION_RATIO: int = config("VIDEO_AMPLIFICATION_RATIO", default=4, cast=int)  # 4x to create 20-40s videos
    SYSTEM_DURATION_CAPABILITY_MIN: int = config("SYSTEM_DURATION_CAPABILITY_MIN", default=20, cast=int)  # seconds
    SYSTEM_DURATION_CAPABILITY_MAX: int = config("SYSTEM_DURATION_CAPABILITY_MAX", default=60, cast=int)  # seconds
    # Scene Planning Configuration - MAS系统场景数量约束
    SCENE_COUNT_RANGE_MIN: int = config("SCENE_COUNT_RANGE_MIN", default=3, cast=int)  # MAS最小价值体现
    SCENE_COUNT_RANGE_MAX: int = config("SCENE_COUNT_RANGE_MAX", default=7, cast=int)  # 成本控制考虑
    
    # Frame Generation Configuration
    FIRST_FRAME_GENERATION_MODE: str = config("FIRST_FRAME_GENERATION_MODE", default="static_snapshot")
    LAST_FRAME_GENERATION_MODE: str = config("LAST_FRAME_GENERATION_MODE", default="static_snapshot")
    ENABLE_FRAME_CONSISTENCY_CHECK: bool = config("ENABLE_FRAME_CONSISTENCY_CHECK", default=True, cast=bool)
    FRAME_DIFFERENCE_THRESHOLD: float = config("FRAME_DIFFERENCE_THRESHOLD", default=0.3, cast=float)  # Minimum difference between first/last frames
    
    # Scene Duration Configuration - 替换所有硬编码duration
    # Scene Duration Configuration - 基于当前视频生成API能力
    AVAILABLE_SCENE_DURATIONS: List[int] = [5, 10]  # CogVideoX-3支持的离散时长选项
    DEFAULT_SCENE_DURATION: int = config("DEFAULT_SCENE_DURATION", default=5, cast=int)  # 默认场景时长
    # 废弃连续范围配置，改为离散选项约束
    # MIN_SCENE_DURATION: float = config("MIN_SCENE_DURATION", default=2.0, cast=float)  # 已废弃
    # MAX_SCENE_DURATION: float = config("MAX_SCENE_DURATION", default=15.0, cast=float)  # 已废弃
    TRANSITION_DURATION: float = config("TRANSITION_DURATION", default=0.5, cast=float)  # 过渡时长
    
    # Audio Configuration - 替换硬编码音频参数
    DEFAULT_AUDIO_DURATION: float = config("DEFAULT_AUDIO_DURATION", default=30.0, cast=float)  # 默认音频时长
    MIN_AUDIO_DURATION: float = config("MIN_AUDIO_DURATION", default=10.0, cast=float)  # 最小音频时长
    MAX_AUDIO_DURATION: float = config("MAX_AUDIO_DURATION", default=300.0, cast=float)  # 最大音频时长
    AUDIO_FADE_IN_DURATION: float = config("AUDIO_FADE_IN_DURATION", default=1.0, cast=float)  # 音频淡入时长
    AUDIO_FADE_OUT_DURATION: float = config("AUDIO_FADE_OUT_DURATION", default=1.0, cast=float)  # 音频淡出时长
    
    # Video Provider Specific Configuration
    COGVIDEOX_DEFAULT_DURATION: int = config("COGVIDEOX_DEFAULT_DURATION", default=5, cast=int)  # CogVideoX默认时长
    COGVIDEOX_MAX_DURATION: int = config("COGVIDEOX_MAX_DURATION", default=10, cast=int)  # CogVideoX最大时长
    
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True
    }


settings = Settings()
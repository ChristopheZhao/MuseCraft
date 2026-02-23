"""
Application configuration settings
"""
from typing import Optional, List, Dict, Any
import json
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

    # API Server Configuration
    API_HOST: str = config("API_HOST", default="0.0.0.0")
    API_PORT: int = config("API_PORT", default=8000, cast=int)
    
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
    FINAL_OUTPUT_ROOT: str = config("FINAL_OUTPUT_ROOT", default="./storage/outputs")
    FINAL_VIDEO_OUTPUT_PATH: str = config(
        "FINAL_VIDEO_OUTPUT_PATH",
        default="./storage/outputs/videos"
    )
    FINAL_AUDIO_OUTPUT_PATH: str = config(
        "FINAL_AUDIO_OUTPUT_PATH",
        default="./storage/outputs/audio"
    )
    MAX_FILE_SIZE: int = config("MAX_FILE_SIZE", default=100, cast=int)  # MB
    # File download/upload robustness
    FILE_STORAGE_HTTP_TIMEOUT: int = config("FILE_STORAGE_HTTP_TIMEOUT", default=120, cast=int)
    FILE_STORAGE_TOOL_TIMEOUT: int = config("FILE_STORAGE_TOOL_TIMEOUT", default=240, cast=int)
    FILE_STORAGE_DOWNLOAD_RETRIES: int = config("FILE_STORAGE_DOWNLOAD_RETRIES", default=3, cast=int)
    
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
    # OSS logical directories for categorization
    OSS_IMAGE_DIR: str = config("OSS_IMAGE_DIR", default="images")
    OSS_AUDIO_DIR: str = config("OSS_AUDIO_DIR", default="audio")
    OSS_CONTINUITY_DIR: str = config("OSS_CONTINUITY_DIR", default="continuity_frames")
    OSS_STAGING_DIR: str = config("OSS_STAGING_DIR", default="staging")
    OSS_VIDEO_INPUT_PREFIX: str = config("OSS_VIDEO_INPUT_PREFIX", default="video_generation_input")
    
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
    GLM_LIGHT_MODEL: str = config("GLM_LIGHT_MODEL", default="glm-4.5-air")
    DOUBAO_API_KEY: Optional[str] = config("DOUBAO_API_KEY", default=None)
    DOUBAO_BASE_URL: str = config("DOUBAO_BASE_URL", default="https://ark.cn-beijing.volces.com")
    # Doubao (Volcengine) Video/Image API path overrides (tenant-specific gateways)
    # For contents-based task gateway (recommended for Seedance video):
    #   DOUBAO_VIDEO_CREATE_PATH=/api/v3/contents/generations/tasks
    #   DOUBAO_VIDEO_QUERY_PATH=/api/v3/contents/generations/tasks/{task_id}
    # For legacy videos gateway (if your tenant uses it):
    #   DOUBAO_VIDEO_CREATE_PATH=/api/v3/videos/generations
    #   DOUBAO_VIDEO_QUERY_PATH=/api/v3/videos/generations/{task_id}
    DOUBAO_VIDEO_CREATE_PATH: str = config(
        "DOUBAO_VIDEO_CREATE_PATH",
        default="/api/v3/contents/generations/tasks",
    )
    DOUBAO_VIDEO_QUERY_PATH: str = config(
        "DOUBAO_VIDEO_QUERY_PATH",
        default="/api/v3/contents/generations/tasks/{task_id}",
    )
    # Optional: model overrides per mode (text-to-video, single image-to-video, first/last frame)
    # NOTE: model ids are configured only via env/config; code should not hardcode version strings.
    DOUBAO_T2V_MODEL: str = config("DOUBAO_T2V_MODEL", default="")
    DOUBAO_I2V_SINGLE_MODEL: str = config("DOUBAO_I2V_SINGLE_MODEL", default="")
    DOUBAO_I2V_SINGLE_ALTER_MODEL: str = config("DOUBAO_I2V_SINGLE_ALTER_MODEL", default="")
    DOUBAO_I2V_FLF_MODEL: str = config("DOUBAO_I2V_FLF_MODEL", default="")
    # Doubao image generation model id (configured via env/config)
    DOUBAO_IMAGE_MODEL: str = config("DOUBAO_IMAGE_MODEL", default="")

    # Orchestration defaults
    DEFAULT_GENERATION_MODE: str = config("DEFAULT_GENERATION_MODE", default="quick")
    VIDEO_COMPOSER_MAX_ITERATIONS: int = config("VIDEO_COMPOSER_MAX_ITERATIONS", default=6, cast=int)
    VIDEO_COMPOSER_TIMEOUT_SECONDS: int = config("VIDEO_COMPOSER_TIMEOUT_SECONDS", default=600, cast=int)
    # 轨迹事件日志：是否启用 episodic 事件落文件
    EPISODIC_EVENT_ENABLED: bool = config("EPISODIC_EVENT_ENABLED", default=True, cast=bool)
    EPISODIC_EVENT_LOG_PATH: str = config("EPISODIC_EVENT_LOG_PATH", default="./logs/episodic_events.log")

    # Image Generation APIs
    MIDJOURNEY_API_KEY: Optional[str] = config("MIDJOURNEY_API_KEY", default=None)
    JIMENG_API_KEY: Optional[str] = config("JIMENG_API_KEY", default=None)
    JIMENG_BASE_URL: str = config("JIMENG_BASE_URL", default="https://api.302.ai/doubao/drawing")
    
    # Video Generation APIs
    MINIMAX_API_KEY: Optional[str] = config("MINIMAX_API_KEY", default=None)
    MINIMAX_BASE_URL: str = config("MINIMAX_BASE_URL", default="https://api.minimaxi.com/v1")
    # Video model ids are configured via env/config only; do not hardcode versioned defaults in code.
    MINIMAX_VIDEO_MODEL: str = config("MINIMAX_VIDEO_MODEL", default="")
    HUNYUAN_VIDEO_API_KEY: Optional[str] = config("HUNYUAN_VIDEO_API_KEY", default=None)
    HUNYUAN_VIDEO_BASE_URL: str = config("HUNYUAN_VIDEO_BASE_URL", default="https://api.hunyuan.cloud.tencent.com/v1")
    DOUBAO_VIDEO_API_KEY: Optional[str] = config("DOUBAO_VIDEO_API_KEY", default=None)
    DOUBAO_VIDEO_BASE_URL: str = config("DOUBAO_VIDEO_BASE_URL", default="https://ark.cn-beijing.volces.com")
    COGVIDEOX3_MODEL: str = config("COGVIDEOX3_MODEL", default="")
    COGVIDEOX2_MODEL: str = config("COGVIDEOX2_MODEL", default="")
    RUNWAY_VIDEO_MODEL: str = config("RUNWAY_VIDEO_MODEL", default="")
    PIKA_VIDEO_MODEL: str = config("PIKA_VIDEO_MODEL", default="")
    
    # Audio Generation APIs
    SUNO_API_KEY: Optional[str] = config("SUNO_API_KEY", default=None)
    SUNO_BASE_URL: str = config("SUNO_BASE_URL", default="https://api.sunoapi.org")
    AUDIO_SFX_REQUIRED_DEFAULT: bool = config("AUDIO_SFX_REQUIRED_DEFAULT", default=False, cast=bool)

    # Voice Synthesis configuration
    VOICE_PRIMARY_PROVIDER: str = config("VOICE_PRIMARY_PROVIDER", default="aliyun")
    VOICE_PROVIDER_FALLBACKS: List[str] = config("VOICE_PROVIDER_FALLBACKS", default="")
    VOICE_PROVIDER_CONFIG: Dict[str, Any] = config("VOICE_PROVIDER_CONFIG", default="{}")
    VOICE_DEFAULT_SAMPLE_RATE: int = config("VOICE_DEFAULT_SAMPLE_RATE", default=16000, cast=int)
    VOICE_DEFAULT_FORMAT: str = config("VOICE_DEFAULT_FORMAT", default="wav")
    VOICE_DEFAULT_VOICE_ID: str = config("VOICE_DEFAULT_VOICE_ID", default="zhiyu")
    VOICE_HTTP_TIMEOUT: int = config("VOICE_HTTP_TIMEOUT", default=30, cast=int)
    VOICE_OUTPUT_DIR: str = config("VOICE_OUTPUT_DIR", default="./storage/generated/voices")
    VOICE_MAX_CHARS_PER_REQUEST: int = config("VOICE_MAX_CHARS_PER_REQUEST", default=300, cast=int)
    VOICE_SYNTHESIZER_MAX_ITERATIONS: int = config(
        "VOICE_SYNTHESIZER_MAX_ITERATIONS", default=9, cast=int
    )
    VOICE_CATALOG_PATH: Optional[str] = config("VOICE_CATALOG_PATH", default=None)
    VOICE_AUTO_SPEED_MATCH: bool = config("VOICE_AUTO_SPEED_MATCH", default=False, cast=bool)
    VOICE_MIN_AUTO_SPEED: float = config("VOICE_MIN_AUTO_SPEED", default=0.85, cast=float)
    VOICE_MAX_AUTO_SPEED: float = config("VOICE_MAX_AUTO_SPEED", default=1.15, cast=float)
    VOICE_PACE_CHAR_RATES: Dict[str, Any] = config(
        "VOICE_PACE_CHAR_RATES", default='{"slow":3.0,"medium":4.0,"fast":5.0}'
    )
    VOICE_PACE_SPEED_MAP: Dict[str, Any] = config(
        "VOICE_PACE_SPEED_MAP", default='{"slow":0.9,"medium":1.0,"fast":1.1}'
    )
    ALIYUN_TTS_APP_KEY: Optional[str] = config("ALIYUN_TTS_APP_KEY", default=None)
    ALIYUN_TTS_ACCESS_KEY_ID: Optional[str] = config("ALIYUN_TTS_ACCESS_KEY_ID", default=None)
    ALIYUN_TTS_ACCESS_KEY_SECRET: Optional[str] = config("ALIYUN_TTS_ACCESS_KEY_SECRET", default=None)
    ALIYUN_TTS_REGION: str = config("ALIYUN_TTS_REGION", default="cn-shanghai")

    @field_validator("VOICE_PROVIDER_FALLBACKS", mode="before")
    @classmethod
    def _parse_voice_provider_fallbacks(cls, value):
        if not value:
            return []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    @field_validator("VOICE_PROVIDER_CONFIG", mode="before")
    @classmethod
    def _parse_voice_provider_config(cls, value):
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return {}
        return {}

    @field_validator("VOICE_PACE_CHAR_RATES", mode="before")
    @classmethod
    def _parse_voice_char_rates(cls, value):
        if not value:
            return {}
        if isinstance(value, dict):
            return {str(k).lower(): float(v) for k, v in value.items() if cls._is_positive_number(v)}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return {
                str(k).lower(): float(v)
                for k, v in parsed.items()
                if cls._is_positive_number(v)
            }
        return {}

    @field_validator("VOICE_PACE_SPEED_MAP", mode="before")
    @classmethod
    def _parse_voice_speed_map(cls, value):
        if not value:
            return {}
        if isinstance(value, dict):
            return {str(k).lower(): float(v) for k, v in value.items() if cls._is_positive_number(v)}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return {
                str(k).lower(): float(v)
                for k, v in parsed.items()
                if cls._is_positive_number(v)
            }
        return {}

    @staticmethod
    def _is_positive_number(value: Any) -> bool:
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False
    
    # Enhanced AI Service Settings
    AI_SERVICE_TIMEOUT: int = config("AI_SERVICE_TIMEOUT", default=120, cast=int)
    AI_SERVICE_MAX_RETRIES: int = config("AI_SERVICE_MAX_RETRIES", default=3, cast=int)
    AI_CACHE_TTL: int = config("AI_CACHE_TTL", default=3600, cast=int)  # 1 hour
    
    # Workflow Optimization Settings
    WORKFLOW_OPTIMIZATION_LEVEL: str = config("WORKFLOW_OPTIMIZATION_LEVEL", default="balanced")  # conservative, balanced, aggressive
    WORKFLOW_EXECUTION_STRATEGY: str = config("WORKFLOW_EXECUTION_STRATEGY", default="adaptive")  # sequential, parallel, adaptive, pipeline
    MAX_CONCURRENT_AGENTS: int = config("MAX_CONCURRENT_AGENTS", default=4, cast=int)
    SCRIPT_GENERATION_MAX_CONCURRENCY: int = config("SCRIPT_GENERATION_MAX_CONCURRENCY", default=3, cast=int)
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

    # Memory backend settings
    MEMORY_WORKFLOW_BACKEND: str = config("MEMORY_WORKFLOW_BACKEND", default="slot")
    MEMORY_FACTS_BACKEND: str = config("MEMORY_FACTS_BACKEND", default="slot")
    MEMORY_SLOTS_PATH: str = config(
        "MEMORY_SLOTS_PATH",
        default=str(pathlib.Path(__file__).resolve().parent.parent / "agents" / "memory" / "config" / "memory_slots.yaml"),
    )
    MEMORY_FACT_ALIASES_PATH: str = config(
        "MEMORY_FACT_ALIASES_PATH",
        default=str(pathlib.Path(__file__).resolve().parent.parent / "agents" / "memory" / "config" / "fact_aliases.yaml"),
    )
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
    # LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")
    LOG_LEVEL: str = config("LOG_LEVEL", default="DEBUG")
    MAS_LOG_DIR: str = config("MAS_LOG_DIR", default="./backend/logs/mas")
    MAS_LOG_LEVEL: str = config("MAS_LOG_LEVEL", default="INFO")
    MAS_LOG_MAX_BYTES: int = config("MAS_LOG_MAX_BYTES", default=10_485_760, cast=int)
    MAS_LOG_BACKUP_COUNT: int = config("MAS_LOG_BACKUP_COUNT", default=5, cast=int)
    LOG_FORMAT: str = config("LOG_FORMAT", default="json")
    
    # Video Generation System Configuration,support cogvideox-3, doubao
    VIDEO_GENERATION_PROVIDER: str = config("VIDEO_GENERATION_PROVIDER", default="doubao")
    # Image Generation System Configuration,support zhipu, doubao
    IMAGE_GENERATION_PROVIDER: str = config("IMAGE_GENERATION_PROVIDER", default="doubao")
    VIDEO_DURATION_CAPABILITIES: List[int] = [5, 10]  # Available duration options for current provider
    DEFAULT_VIDEO_RESOLUTION: str = config("DEFAULT_VIDEO_RESOLUTION", default="1280x720")
    VIDEO_AMPLIFICATION_RATIO: int = config("VIDEO_AMPLIFICATION_RATIO", default=4, cast=int)  # 4x to create 20-40s videos
    VIDEO_GENERATOR_MAX_BATCH: int = config("VIDEO_GENERATOR_MAX_BATCH", default=2, cast=int)  # 兜底批量上限；设为0可禁用裁剪
    SYSTEM_DURATION_CAPABILITY_MIN: int = config("SYSTEM_DURATION_CAPABILITY_MIN", default=15, cast=int)  # seconds
    SYSTEM_DURATION_CAPABILITY_MAX: int = config("SYSTEM_DURATION_CAPABILITY_MAX", default=80, cast=int)  # seconds
    # Scene Planning Configuration - MAS系统场景数量约束
    SCENE_COUNT_RANGE_MIN: int = config("SCENE_COUNT_RANGE_MIN", default=3, cast=int)  # MAS最小价值体现
    SCENE_COUNT_RANGE_MAX: int = config("SCENE_COUNT_RANGE_MAX", default=10, cast=int)  # 成本控制考虑
    
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

    # Prompt Enhancement Configuration
    ENHANCE_PROMPT_MAX_TOKENS: int = config("ENHANCE_PROMPT_MAX_TOKENS", default=10240, cast=int)
    ENHANCE_PROMPT_RETRY_MAX_TOKENS: int = config("ENHANCE_PROMPT_RETRY_MAX_TOKENS", default=2048, cast=int)
    
    # Global LLM token tiers (standard vs thinking)
    LLM_MAX_TOKENS_STANDARD: int = config("LLM_MAX_TOKENS_STANDARD", default=12800, cast=int)
    LLM_MAX_TOKENS_THINKING: int = config("LLM_MAX_TOKENS_THINKING", default=20000, cast=int)
    # LLM回退超时策略（配置优先，避免代码常量）
    LLM_PRIMARY_TIMEOUT_RATIO: float = config("LLM_PRIMARY_TIMEOUT_RATIO", default=0.5, cast=float)  # 主调占Agent超时比例
    LLM_FALLBACK_TIMEOUT_MIN: int = config("LLM_FALLBACK_TIMEOUT_MIN", default=20, cast=int)
    LLM_FALLBACK_TIMEOUT_MAX: int = config("LLM_FALLBACK_TIMEOUT_MAX", default=90, cast=int)
    LLM_REQUEST_SAFETY_MARGIN: int = config("LLM_REQUEST_SAFETY_MARGIN", default=5, cast=int)
    # 结构化输出温度（response_format=json_object 等）：优先稳定性，避免格式漂移
    LLM_JSON_TEMPERATURE: float = config("LLM_JSON_TEMPERATURE", default=0.2, cast=float)
    LLM_JSON_TEMPERATURE_FALLBACK: float = config("LLM_JSON_TEMPERATURE_FALLBACK", default=0.2, cast=float)

    # Audio mixing strategy
    AUDIO_MIXING_MODE: str = config("AUDIO_MIXING_MODE", default="composer")  # composer | agent
    # Video-audio orchestration strategy (capability-adaptive):
    # - adaptive: provider supports native audio -> skip AUDIO_GENERATOR; otherwise run AUDIO_GENERATOR
    # - mas_only: always run AUDIO_GENERATOR and disable provider native audio path
    # - provider_only: prefer provider native audio; if provider doesn't support it, fallback to MAS audio agent
    VIDEO_AUDIO_STRATEGY: str = config("VIDEO_AUDIO_STRATEGY", default="adaptive")
    AUDIO_FADE_IN_DURATION: float = config("AUDIO_FADE_IN_DURATION", default=1.0, cast=float)
    AUDIO_FADE_OUT_DURATION: float = config("AUDIO_FADE_OUT_DURATION", default=1.0, cast=float)
    # Image/Video analysis + prompt generation token budgets
    IMAGE_PROMPT_FROM_SCENE_MAX_TOKENS: int = config("IMAGE_PROMPT_FROM_SCENE_MAX_TOKENS", default=7168, cast=int)
    IMAGE_STYLE_ANALYSIS_MAX_TOKENS: int = config("IMAGE_STYLE_ANALYSIS_MAX_TOKENS", default=7168, cast=int)
    VISUAL_FEATURES_EXTRACTION_MAX_TOKENS: int = config("VISUAL_FEATURES_EXTRACTION_MAX_TOKENS", default=12800, cast=int)
    IMAGE_GENERATOR_TEMPLATE_MAX_TOKENS: int = config("IMAGE_GENERATOR_TEMPLATE_MAX_TOKENS", default=12800, cast=int)
    VIDEO_ANALYSIS_MAX_TOKENS: int = config("VIDEO_ANALYSIS_MAX_TOKENS", default=4096, cast=int)
    # MIN_SCENE_DURATION: float = config("MIN_SCENE_DURATION", default=2.0, cast=float)  # 已废弃
    # MAX_SCENE_DURATION: float = config("MAX_SCENE_DURATION", default=15.0, cast=float)  # 已废弃
    TRANSITION_DURATION: float = config("TRANSITION_DURATION", default=0.5, cast=float)  # 过渡时长

    # Strictness and degrade controls for image prompt generation
    IMAGE_PROMPT_STRICT_MODE: bool = config("IMAGE_PROMPT_STRICT_MODE", default=False, cast=bool)
    IMAGE_PROMPT_ALLOW_DEGRADE: bool = config("IMAGE_PROMPT_ALLOW_DEGRADE", default=True, cast=bool)

    # Script Writer dynamic timeout configuration
    SCRIPT_WRITER_TIMEOUT_BASE: int = config("SCRIPT_WRITER_TIMEOUT_BASE", default=180, cast=int)
    SCRIPT_WRITER_TIMEOUT_PER_SCENE: int = config("SCRIPT_WRITER_TIMEOUT_PER_SCENE", default=30, cast=int)
    SCRIPT_WRITER_TIMEOUT_MAX: int = config("SCRIPT_WRITER_TIMEOUT_MAX", default=900, cast=int)
    
    # Audio Configuration - 替换硬编码音频参数
    DEFAULT_AUDIO_DURATION: float = config("DEFAULT_AUDIO_DURATION", default=30.0, cast=float)  # 默认音频时长
    MIN_AUDIO_DURATION: float = config("MIN_AUDIO_DURATION", default=10.0, cast=float)  # 最小音频时长
    MAX_AUDIO_DURATION: float = config("MAX_AUDIO_DURATION", default=300.0, cast=float)  # 最大音频时长
    AUDIO_FADE_IN_DURATION: float = config("AUDIO_FADE_IN_DURATION", default=1.0, cast=float)  # 音频淡入时长
    AUDIO_FADE_OUT_DURATION: float = config("AUDIO_FADE_OUT_DURATION", default=1.0, cast=float)  # 音频淡出时长
    SUNO_POLL_INTERVAL_SECONDS: int = config("SUNO_POLL_INTERVAL_SECONDS", default=30, cast=int)
    SUNO_POLL_MAX_ATTEMPTS: int = config("SUNO_POLL_MAX_ATTEMPTS", default=20, cast=int)
    
    # Video Provider Specific Configuration
    COGVIDEOX_DEFAULT_DURATION: int = config("COGVIDEOX_DEFAULT_DURATION", default=5, cast=int)  # CogVideoX默认时长
    COGVIDEOX_MAX_DURATION: int = config("COGVIDEOX_MAX_DURATION", default=10, cast=int)  # CogVideoX最大时长

    # Composer options
    COMPOSER_INJECT_SILENT_AUDIO: bool = config("COMPOSER_INJECT_SILENT_AUDIO", default=True, cast=bool)
    COMPOSER_SILENT_AUDIO_SAMPLE_RATE: int = config("COMPOSER_SILENT_AUDIO_SAMPLE_RATE", default=48000, cast=int)
    COMPOSER_SILENT_AUDIO_CHANNELS: int = config("COMPOSER_SILENT_AUDIO_CHANNELS", default=2, cast=int)
    COMPOSER_PRESERVE_SOURCE_AUDIO_DEFAULT: bool = config(
        "COMPOSER_PRESERVE_SOURCE_AUDIO_DEFAULT",
        default=False,
        cast=bool,
    )
    COMPOSER_HIDE_SCENE_AUDIO_ON_REF: bool = config(
        "COMPOSER_HIDE_SCENE_AUDIO_ON_REF",
        default=True,
        cast=bool,
    )
    
    # Agent ReAct Configuration - ReAct循环最大迭代次数配置（业务逻辑配置，不放在.env）
    VIDEO_GENERATOR_MAX_ITERATIONS: int = 14   # 视频生成Agent最大迭代次数
    CONCEPT_PLANNER_MAX_ITERATIONS: int = 4  # 概念规划Agent最大迭代次数
    IMAGE_GENERATOR_MAX_ITERATIONS: int = 14   # 图像生成Agent最大迭代次数
    ORCHESTRATOR_MAX_ITERATIONS: int = 10     # 编排Agent最大迭代次数
    ORCHESTRATOR_TIMEOUT_SECONDS: int = config("ORCHESTRATOR_TIMEOUT_SECONDS", default=3600, cast=int)
    # Concept Planner agent-level timeout（配置化，避免代码常量）
    CONCEPT_PLANNER_TIMEOUT_SECONDS: int = config("CONCEPT_PLANNER_TIMEOUT_SECONDS", default=360, cast=int)
    
    # Video continuity persistence (domain policy)
    VIDEO_PERSIST_LAST_FRAME: bool = config("VIDEO_PERSIST_LAST_FRAME", default=False, cast=bool)

    # ReAct execution tuning (configurable via .env)
    REACT_NO_PROGRESS_MAX_ROUNDS: int = config("REACT_NO_PROGRESS_MAX_ROUNDS", default=2, cast=int)
    REACT_VIDEO_BATCH_SIZE: int = config("REACT_VIDEO_BATCH_SIZE", default=2, cast=int)
    REACT_IMAGE_BATCH_SIZE: int = config("REACT_IMAGE_BATCH_SIZE", default=3, cast=int)
    ORCHESTRATOR_MAX_REPEAT_PER_STEP: int = config("ORCHESTRATOR_MAX_REPEAT_PER_STEP", default=1, cast=int)
    ORCHESTRATOR_DECISION_MODEL: str = config("ORCHESTRATOR_DECISION_MODEL", default="glm-4.5-air")
    # 当为 True 时，编排层在汇总/输出时优先读取 SharedWM.artifacts（最新记录）
    ORCHESTRATOR_READS_ARTIFACTS: bool = config("ORCHESTRATOR_READS_ARTIFACTS", default=False, cast=bool)
    # 单写模式：仅写 artifacts，停止更新 facts（逐步收敛到 artifacts 为单一真实来源）
    ARTIFACTS_SINGLE_WRITE_MODE: bool = config("ARTIFACTS_SINGLE_WRITE_MODE", default=True, cast=bool)

    # ReAct WF observation/commit policy
    # internal: 仅使用inner_react_state判断完成；wf: 合并WorkflowState中的已完成资产（用于超时/重试后的断点续跑）
    REACT_OBSERVE_COMPLETION_SOURCE: str = config("REACT_OBSERVE_COMPLETION_SOURCE", default="internal")
    # True: 仅在任务完成时一次性写入WF；False: 每轮生成成功后即刻写入WF（便于断点续跑）
    # 默认关闭“仅完成时写入”，启用实时写回，避免中途产物丢失
    REACT_WRITE_WF_ON_COMPLETE_ONLY: bool = config("REACT_WRITE_WF_ON_COMPLETE_ONLY", default=False, cast=bool)
    # 是否启用首轮 plan-only（tools=[]）回合；默认关闭，采用“单段式纯 ReAct”
    REACT_PLAN_ONLY_ENABLED: bool = config("REACT_PLAN_ONLY_ENABLED", default=False, cast=bool)
    # OBS 压缩与契约校验（Config over Constants）
    REACT_OBS_SCENE_THRESHOLD: int = config("REACT_OBS_SCENE_THRESHOLD", default=8, cast=int)
    REACT_OBS_SIZE_THRESHOLD: int = config("REACT_OBS_SIZE_THRESHOLD", default=2000, cast=int)
    REACT_OBS_SCHEMA_STRICT: bool = config("REACT_OBS_SCHEMA_STRICT", default=True, cast=bool)
    # 是否启用观察压缩（基于 LLM 的结构化概览）。默认关闭，保持 OBS 仅包含事实。
    REACT_OBS_AUGMENT_ENABLED: bool = config("REACT_OBS_AUGMENT_ENABLED", default=False, cast=bool)
    REACT_EPISODIC_LOG_ENABLED: bool = config("REACT_EPISODIC_LOG_ENABLED", default=False, cast=bool)
    REACT_CONTEXT_INCLUDE_RECENT_STEPS: bool = config("REACT_CONTEXT_INCLUDE_RECENT_STEPS", default=True, cast=bool)
    REACT_CONTEXT_RECENT_STEPS_K: int = config("REACT_CONTEXT_RECENT_STEPS_K", default=3, cast=int)
    REACT_CONTEXT_INCLUDE_NOTES: bool = config("REACT_CONTEXT_INCLUDE_NOTES", default=False, cast=bool)
    REACT_CONTEXT_NOTES_LIMIT: int = config("REACT_CONTEXT_NOTES_LIMIT", default=5, cast=int)
    REACT_CONTEXT_INCLUDE_ARTIFACT_PREVIEW: bool = config("REACT_CONTEXT_INCLUDE_ARTIFACT_PREVIEW", default=False, cast=bool)
    # WorkingMemory 中“最近步骤摘要”的窗口大小（k≈3–5）。
    REACT_WM_RECENT_STEPS_K: int = config("REACT_WM_RECENT_STEPS_K", default=3, cast=int)
    # 事件标签映射（仅用于日志标签，不驱动控制流）：JSON 字符串或 dict
    REACT_ACTION_LABEL_MAP: Dict[str, Any] = config("REACT_ACTION_LABEL_MAP", default='{}')
    
    
    # Content preview configuration for ReAct text observations
    CONTENT_PREVIEW_CHARS: int = config("CONTENT_PREVIEW_CHARS", default=600, cast=int)
    # Whether to include a verbose tools overview block in system messages for FC (usually unnecessary and may distract)
    FC_INCLUDE_TOOLS_OVERVIEW: bool = config("FC_INCLUDE_TOOLS_OVERVIEW", default=False, cast=bool)

    # ReAct scratchpad/summary injection (Agent-level, not Base)
    REACT_INJECT_SCRATCHPAD: bool = config("REACT_INJECT_SCRATCHPAD", default=True, cast=bool)
    REACT_SCRATCHPAD_STEPS: int = config("REACT_SCRATCHPAD_STEPS", default=2, cast=int)
    REACT_SCRATCHPAD_MAX_CHARS: int = config("REACT_SCRATCHPAD_MAX_CHARS", default=800, cast=int)

    # Progress snapshot (agent-internal, per-iteration reference records)
    ENABLE_PROGRESS_SNAPSHOT: bool = config("ENABLE_PROGRESS_SNAPSHOT", default=True, cast=bool)

    # Tool/runtime timeouts (config over constants)
    DEFAULT_TOOL_TIMEOUT: int = config("DEFAULT_TOOL_TIMEOUT", default=120, cast=int)  # 默认工具超时
    VIDEO_GENERATION_TOOL_TIMEOUT: int = config("VIDEO_GENERATION_TOOL_TIMEOUT", default=300, cast=int)
    IMAGE_GENERATION_TOOL_TIMEOUT: int = config("IMAGE_GENERATION_TOOL_TIMEOUT", default=180, cast=int)
    # Project character reference images (avatar/full-body) for cross-episode reuse
    PROJECT_CHARACTER_REFERENCE_IMAGES_ENABLED: bool = config(
        "PROJECT_CHARACTER_REFERENCE_IMAGES_ENABLED", default=False, cast=bool
    )
    PROJECT_CHARACTER_REFERENCE_AVATAR_SIZE: str = config(
        "PROJECT_CHARACTER_REFERENCE_AVATAR_SIZE", default="1024x1024"
    )
    PROJECT_CHARACTER_REFERENCE_FULL_BODY_SIZE: str = config(
        "PROJECT_CHARACTER_REFERENCE_FULL_BODY_SIZE", default="1024x1792"
    )
    IMAGE_TOOL_PROMPT_RULES: Dict[str, Any] = config(
        "IMAGE_TOOL_PROMPT_RULES",
        default='{"min_length": 30, "allow_weak_prompt": false, "weak_marker_length_threshold": 50, "weak_marker_threshold": 2, "weak_markers": ["高质量", "高清", "精美", "好看", "震撼", "唯美", "超清", "逼真"]}'
    )
    AUDIO_GENERATION_TOOL_TIMEOUT: int = config("AUDIO_GENERATION_TOOL_TIMEOUT", default=240, cast=int)
    # HTTP下载类（如从第三方拉取音频/视频到本地）超时，供 file_storage_tool 使用
    FILE_STORAGE_HTTP_TIMEOUT: int = config("FILE_STORAGE_HTTP_TIMEOUT", default=300, cast=int)
    # 保持网络通用性：不增加客户端网络相关配置，统一遵循系统/进程代理
    NETWORK_DIRECT_FALLBACK_ON_TIMEOUT: bool = config(
        "NETWORK_DIRECT_FALLBACK_ON_TIMEOUT", default=True, cast=bool
    )  # 超时后是否做一次“绕过系统代理”的直连重试（默认关闭，保持供应商/环境无关）
    # Agent-level end-to-end timeouts
    VIDEO_GENERATOR_TIMEOUT_SECONDS: int = config("VIDEO_GENERATOR_TIMEOUT_SECONDS", default=1800, cast=int)
    SCENE_JOURNAL_MAX_EVENTS: int = config("SCENE_JOURNAL_MAX_EVENTS", default=5, cast=int)
    # LLM context budgets (model-driven)
    LLM_CONTEXT_TOKENS_DEFAULT: int = config("LLM_CONTEXT_TOKENS_DEFAULT", default=128000, cast=int)
    # JSON string mapping or dict; e.g. {"zhipu/glm-4.5": 128000}
    LLM_MODEL_CONTEXT_TOKENS: Dict[str, Any] = config("LLM_MODEL_CONTEXT_TOKENS", default='{}')
    CONTEXT_INPUT_BUDGET_RATIO: float = config("CONTEXT_INPUT_BUDGET_RATIO", default=0.6, cast=float)
    CONTEXT_OUTPUT_RESERVE_TOKENS: int = config("CONTEXT_OUTPUT_RESERVE_TOKENS", default=4000, cast=int)

    # OBS observables (Iter -> OBS attachments) configuration
    REACT_OBS_INCLUDE_OBSERVABLES: bool = config("REACT_OBS_INCLUDE_OBSERVABLES", default=True, cast=bool)
    # At most K scenes to inject full assets payloads into OBS per round
    REACT_OBS_ASSETS_MAX_SCENES: int = config("REACT_OBS_ASSETS_MAX_SCENES", default=2, cast=int)
    # Soft cap for total chars of one scene's assets payload injected into OBS
    REACT_OBS_ASSETS_MAX_CHARS: int = config("REACT_OBS_ASSETS_MAX_CHARS", default=1024, cast=int)
    # MemRef 严格模式：当 memref.scene_number 与调用参数不一致，或场景未知时，直接报错；默认关闭（宽松为跳过）
    REACT_MEMREF_STRICT: bool = config("REACT_MEMREF_STRICT", default=False, cast=bool)
    
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    @field_validator("IMAGE_TOOL_PROMPT_RULES", mode="before")
    @classmethod
    def parse_image_tool_rules(cls, v):
        if isinstance(v, str):
            import json
            try:
                parsed = json.loads(v or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError("IMAGE_TOOL_PROMPT_RULES must be JSON string") from exc
            if not isinstance(parsed, dict):
                raise ValueError("IMAGE_TOOL_PROMPT_RULES must be dict")
            return parsed
        return v or {}
    
    @field_validator("LLM_MODEL_CONTEXT_TOKENS", mode="before")
    @classmethod
    def parse_llm_model_context_tokens(cls, v):
        if isinstance(v, str):
            text = (v or "").strip()
            if not text:
                return {}
            import json
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("LLM_MODEL_CONTEXT_TOKENS must be JSON string") from exc
            if not isinstance(parsed, dict):
                raise ValueError("LLM_MODEL_CONTEXT_TOKENS must be dict")
            return parsed
        return v or {}

    @field_validator("REACT_ACTION_LABEL_MAP", mode="before")
    @classmethod
    def parse_action_label_map(cls, v):
        if isinstance(v, str):
            text = (v or "").strip()
            if not text:
                return {}
            import json
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("REACT_ACTION_LABEL_MAP must be JSON string") from exc
            if not isinstance(parsed, dict):
                raise ValueError("REACT_ACTION_LABEL_MAP must be dict")
            return parsed
        return v or {}
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True
    }


settings = Settings()

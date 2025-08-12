# 🛠️ 工具配置指南

本文档详细说明了短视频生成平台中各个工具的配置方法和使用说明。

## 📋 工具概览

### 已实现的工具类别

| 工具类别 | 工具名称 | 主要功能 | 状态 |
|---------|---------|----------|------|
| **AI服务** | OpenAI Client | GPT系列模型调用 | ✅ 完成 |
| **AI服务** | Kimi Client | 月之暗面长文本模型 | ✅ 完成 |
| **AI服务** | 智谱AI Client | GLM-4.5、CogView、CogVideoX | ✅ 完成 |
| **AI服务** | 图像生成客户端 | 多平台图像生成 | ✅ 完成 |
| **视频处理** | FFmpeg工具 | 视频编辑、格式转换 | ✅ 完成 |
| **存储管理** | 文件存储工具 | 本地/云端文件管理 | ✅ 完成 |
| **视频合成** | 视频合成工具 | 智能视频合成 | ✅ 完成 |

## 🔧 工具配置详解

### 1. AI服务工具配置

#### OpenAI Client Tool

**功能**: GPT-4、GPT-3.5等模型的文本生成和对话

**配置参数**:
```yaml
openai_client:
  api_key: "your_openai_api_key"
  base_url: "https://api.openai.com/v1"  # 可选，支持代理
  default_model: "gpt-4"
  default_max_tokens: 2000
  default_temperature: 0.7
  timeout: 120
```

**环境变量**:
```bash
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选
```

**使用示例**:
```python
await openai_tool.execute(ToolInput(
    action="chat_completion",
    parameters={
        "messages": [{"role": "user", "content": "创作一个科技主题的短视频脚本"}],
        "model": "gpt-4",
        "max_tokens": 1000
    }
))
```

#### Kimi Client Tool

**功能**: 月之暗面Kimi模型，支持长文本处理和中文优化

**配置参数**:
```yaml
kimi_client:
  api_key: "your_kimi_api_key"
  base_url: "https://api.moonshot.cn/v1"
  default_model: "moonshot-v1-8k"
  default_max_tokens: 2000
  default_temperature: 0.7
  timeout: 120
```

**环境变量**:
```bash
KIMI_API_KEY=your_kimi_api_key
```

**使用示例**:
```python
await kimi_tool.execute(ToolInput(
    action="long_text_generation",
    parameters={
        "prompt": "基于以下内容创作视频脚本...",
        "model": "moonshot-v1-32k",
        "max_tokens": 4000
    }
))
```

#### 智谱AI Client Tool

**功能**: GLM-4.5文本生成、CogView图像生成、CogVideoX视频生成

**配置参数**:
```yaml
zhipu_client:
  api_key: "your_zhipu_api_key"
  base_url: "https://open.bigmodel.cn/api/paas/v4"
  default_model: "glm-4-plus"
  default_max_tokens: 2000
  default_temperature: 0.7
  timeout: 120
```

**环境变量**:
```bash
ZHIPU_API_KEY=your_zhipu_api_key
```

**使用示例**:
```python
# 文本生成
await zhipu_tool.execute(ToolInput(
    action="chat_completion",
    parameters={
        "messages": [{"role": "user", "content": "创作短视频脚本"}],
        "model": "glm-4-plus"
    }
))

# 图像生成
await zhipu_tool.execute(ToolInput(
    action="generate_image",
    parameters={
        "prompt": "科技感背景图片",
        "model": "cogview-3",
        "size": "1024x1024"
    }
))

# 视频生成
await zhipu_tool.execute(ToolInput(
    action="generate_video",
    parameters={
        "prompt": "科技产品展示视频",
        "model": "cogvideox"
    }
))
```

#### 图像生成客户端工具

**功能**: 统一多个图像生成服务的接口

**配置参数**:
```yaml
image_generation_client:
  default_provider: "stability"  # stability, openai, zhipu, tongyi
  timeout: 300
  
  # Stability AI配置
  stability_api_key: "your_stability_key"
  
  # OpenAI DALL-E配置
  openai_api_key: "your_openai_key"
  
  # 智谱AI配置
  zhipu_api_key: "your_zhipu_key"
  
  # 通义万相配置
  tongyi_api_key: "your_tongyi_key"
```

**环境变量**:
```bash
STABILITY_API_KEY=your_stability_key
OPENAI_API_KEY=your_openai_key  # 如果要使用DALL-E
ZHIPU_API_KEY=your_zhipu_key    # 如果要使用CogView
TONGYI_API_KEY=your_tongyi_key  # 如果要使用通义万相
```

### 2. 视频处理工具配置

#### FFmpeg工具

**功能**: 视频编辑、格式转换、音频合成等

**系统要求**:
- 必须安装FFmpeg（版本4.0+）
- Linux: `sudo apt install ffmpeg`
- Windows: 下载并添加到PATH
- macOS: `brew install ffmpeg`

**配置参数**:
```yaml
ffmpeg_tool:
  output_dir: "/tmp/video_output"
  temp_dir: "/tmp/ffmpeg_temp"
  max_resolution: "1920x1080"
  default_fps: 30
  default_bitrate: "2M"
  timeout: 600  # 10分钟
```

**使用示例**:
```python
# 合成视频
await ffmpeg_tool.execute(ToolInput(
    action="compose_video",
    parameters={
        "video_clips": ["clip1.mp4", "clip2.mp4"],
        "output_filename": "final_video.mp4",
        "audio_file": "background.mp3",
        "resolution": "1920x1080"
    }
))

# 创建图片幻灯片
await ffmpeg_tool.execute(ToolInput(
    action="create_slideshow",
    parameters={
        "images": ["img1.jpg", "img2.jpg", "img3.jpg"],
        "duration_per_image": 3.0,
        "output_filename": "slideshow.mp4",
        "transition_effect": "fade"
    }
))
```

### 3. 存储管理工具配置

#### 文件存储工具

**功能**: 支持本地存储、MinIO、AWS S3等多种存储方式

**配置参数**:
```yaml
file_storage_tool:
  storage_type: "local"  # local, s3, minio
  local_storage_dir: "/tmp/video_storage"
  max_file_size: 524288000  # 500MB
  
  # S3配置（如果使用）
  s3_bucket: "your-bucket-name"
  s3_region: "us-east-1"
  s3_access_key: "your-access-key"
  s3_secret_key: "your-secret-key"
  
  # MinIO配置（如果使用）
  minio_endpoint: "localhost:9000"
  minio_access_key: "minioadmin"
  minio_secret_key: "minioadmin"
  minio_bucket: "video-storage"
  minio_secure: false
```

**环境变量**:
```bash
# S3存储
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
S3_BUCKET_NAME=your_bucket_name

# MinIO存储
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=video-storage
```

**使用示例**:
```python
# 上传文件
await storage_tool.execute(ToolInput(
    action="upload_file",
    parameters={
        "file_path": "/path/to/video.mp4",
        "metadata": {"type": "final_video", "project_id": "123"}
    }
))

# 从URL上传
await storage_tool.execute(ToolInput(
    action="upload_from_url",
    parameters={
        "url": "https://example.com/image.jpg",
        "metadata": {"source": "ai_generated"}
    }
))
```

### 4. 视频合成工具配置

#### 视频合成工具

**功能**: 高级视频合成、场景编排、智能转场

**配置参数**:
```yaml
video_composer_tool:
  output_dir: "/tmp/video_composition"
  temp_dir: "/tmp/composition_temp"
  quality_preset: "medium"  # low, medium, high
  default_transition_duration: 1.0
  
  ffmpeg:
    # FFmpeg工具配置
    output_dir: "/tmp/video_output"
    timeout: 600
  
  storage:
    # 存储工具配置
    storage_type: "local"
    local_storage_dir: "/tmp/video_storage"
```

**使用示例**:
```python
# 合成故事视频
await composer_tool.execute(ToolInput(
    action="compose_story_video",
    parameters={
        "scenes": [
            {
                "video_file": "scene1.mp4",
                "duration": 5.0,
                "subtitle_text": "第一幕：开场",
                "transition_in": "fade"
            },
            {
                "video_file": "scene2.mp4", 
                "duration": 8.0,
                "audio_file": "narration.mp3",
                "transition_out": "slideright"
            }
        ],
        "background_music": "bg_music.mp3",
        "output_filename": "story_video.mp4",
        "style": "cinematic"
    }
))

# 平台优化
await composer_tool.execute(ToolInput(
    action="optimize_for_platform",
    parameters={
        "input_video": "original.mp4",
        "platform": "tiktok",  # youtube, tiktok, instagram
        "output_filename": "tiktok_optimized.mp4"
    }
))
```

## 🚀 工具使用流程

### 典型的视频生成流程

1. **概念规划** (Kimi/GLM-4.5)
   ```python
   concept = await kimi_tool.execute(ToolInput(
       action="generate_concept",
       parameters={"user_prompt": "科技产品介绍视频"}
   ))
   ```

2. **脚本生成** (GPT-4/GLM-4.5)
   ```python
   script = await openai_tool.execute(ToolInput(
       action="generate_script",
       parameters={"concept": concept["content"]}
   ))
   ```

3. **图像生成** (多平台图像生成)
   ```python
   images = await image_tool.execute(ToolInput(
       action="batch_generate_images",
       parameters={
           "prompts": script["scene_descriptions"],
           "provider": "stability"
       }
   ))
   ```

4. **视频生成** (CogVideoX)
   ```python
   videos = await zhipu_tool.execute(ToolInput(
       action="generate_video",
       parameters={
           "prompt": scene_description,
           "image_url": key_frame_image
       }
   ))
   ```

5. **视频合成** (视频合成工具)
   ```python
   final_video = await composer_tool.execute(ToolInput(
       action="compose_story_video",
       parameters={
           "scenes": processed_scenes,
           "style": "professional"
       }
   ))
   ```

6. **存储管理** (文件存储工具)
   ```python
   storage_result = await storage_tool.execute(ToolInput(
       action="upload_file",
       parameters={"file_path": final_video["output_file"]}
   ))
   ```

## ⚙️ 配置文件示例

### 完整的工具配置文件 (config/tools.yaml)

```yaml
# AI服务工具配置
ai_services:
  openai_client:
    api_key: "${OPENAI_API_KEY}"
    default_model: "gpt-4"
    timeout: 120
  
  kimi_client:
    api_key: "${KIMI_API_KEY}"
    default_model: "moonshot-v1-8k"
    timeout: 120
  
  zhipu_client:
    api_key: "${ZHIPU_API_KEY}"
    default_model: "glm-4-plus"
    timeout: 120
  
  image_generation_client:
    default_provider: "stability"
    stability_api_key: "${STABILITY_API_KEY}"
    openai_api_key: "${OPENAI_API_KEY}"
    zhipu_api_key: "${ZHIPU_API_KEY}"

# 视频处理工具配置
video_processing:
  ffmpeg_tool:
    output_dir: "/app/storage/video_output"
    temp_dir: "/tmp/ffmpeg_temp"
    max_resolution: "1920x1080"
    default_fps: 30
    timeout: 600

# 存储工具配置
storage:
  file_storage_tool:
    storage_type: "${STORAGE_TYPE:-local}"
    local_storage_dir: "/app/storage/files"
    max_file_size: 524288000
    
    # S3配置
    s3_bucket: "${S3_BUCKET}"
    s3_region: "${S3_REGION:-us-east-1}"
    s3_access_key: "${AWS_ACCESS_KEY_ID}"
    s3_secret_key: "${AWS_SECRET_ACCESS_KEY}"

# 视频合成工具配置
video_composition:
  video_composer_tool:
    output_dir: "/app/storage/composition"
    temp_dir: "/tmp/composition_temp"
    quality_preset: "medium"
    
    ffmpeg:
      output_dir: "/app/storage/video_output"
      timeout: 600
    
    storage:
      storage_type: "${STORAGE_TYPE:-local}"
      local_storage_dir: "/app/storage/files"
```

## 🔍 故障排除

### 常见问题和解决方案

#### 1. FFmpeg相关问题

**问题**: `FFmpeg not found or not working properly`
**解决**: 
- 确保系统已安装FFmpeg
- 检查FFmpeg是否在PATH中
- Linux: `which ffmpeg`
- Windows: `where ffmpeg`

#### 2. API密钥问题

**问题**: `API key not configured`
**解决**:
- 检查环境变量是否正确设置
- 确认API密钥格式正确
- 验证API密钥权限和余额

#### 3. 存储空间问题

**问题**: `File too large` 或磁盘空间不足
**解决**:
- 调整`max_file_size`配置
- 清理临时文件目录
- 检查存储空间配置

#### 4. 网络连接问题

**问题**: API调用超时或连接失败
**解决**:
- 检查网络连接
- 调整`timeout`配置
- 配置代理（如需要）

## 📊 性能优化建议

### 1. 并发处理
- 合理设置工具的并发数量
- 使用异步处理避免阻塞
- 实现任务队列管理

### 2. 缓存策略
- 启用图像生成结果缓存
- 缓存常用的视频片段
- 实现智能去重机制

### 3. 资源管理
- 定期清理临时文件
- 监控内存和磁盘使用
- 实现资源限制和熔断

### 4. 质量与速度平衡
- 根据用途选择合适的质量设置
- 使用预设模板加速生成
- 实现分层处理策略

## 🔄 工具扩展指南

### 添加新的AI服务工具

1. 继承`AsyncTool`基类
2. 实现必要的方法
3. 注册到工具注册表
4. 添加配置和文档

### 自定义视频处理流程

1. 扩展FFmpeg工具功能
2. 创建专用的处理模板
3. 集成到视频合成工具中
4. 实现参数化配置

通过以上配置，你可以充分利用短视频生成平台的所有工具功能，创建出高质量的视频内容。
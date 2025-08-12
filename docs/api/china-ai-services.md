# 🇨🇳 中国AI服务集成指南

## 概述

本项目已完全支持中国国内的AI服务，包括大语言模型、图片生成、视频生成和云存储服务。所有服务都针对中国用户进行了优化，支持中文处理，并提供更好的网络访问体验。

## 🚀 支持的服务

### 📝 大语言模型 (LLM)

#### 1. Kimi K2 (月之暗面)
- **最新模型**: kimi-k2, kimi-k2-0711-preview
- **传统模型**: moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k
- **特色**: 
  - **Kimi K2**: 万亿参数MoE架构，专为智能体能力设计
  - **128K超长上下文**，中文优化
  - **强大的工具调用能力**
  - **32B激活参数，1T总参数**
- **API密钥**: `KIMI_API_KEY`
- **基础URL**: `https://api.moonshot.cn/v1`
- **定价**: Kimi K2: $0.15/百万输入token, $2.50/百万输出token

#### 2. GLM-4.5 (智谱AI)
- **模型**: glm-4-plus, glm-4-0520, glm-4-long, glm-4-flash
- **特色**: 支持视觉理解、代码生成、图像生成
- **API密钥**: `GLM_API_KEY`
- **基础URL**: `https://open.bigmodel.cn/api/paas/v4`
- **定价**: 根据模型不同

#### 3. 豆包 (字节跳动)
- **模型**: 支持多种豆包模型
- **特色**: 字节跳动出品，与即梦生态集成
- **API密钥**: `DOUBAO_API_KEY`
- **基础URL**: `https://ark.cn-beijing.volces.com`

### 🎨 图片生成

#### 即梦AI (基于豆包Seedream 3.0)
- **模型**: general_v3.0, realistic_v2.0, anime_v2.0, art_v1.0
- **特色**: 
  - 原生2K输出，无需后处理
  - 3秒极速生成
  - 优化的中文提示词支持
  - 多种艺术风格
- **API密钥**: `JIMENG_API_KEY`
- **支持尺寸**: 1024x1024, 1024x1792, 1792x1024等
- **定价**: ¥0.05/张起（1024x1024标准质量）

### 🎬 视频生成

#### MiniMax abab-video-1
- **模型**: abab-video-1
- **特色**:
  - 支持文生视频和图生视频
  - **关键特性**: 支持首尾帧图片输入生成视频
  - 最高1280×720分辨率，25fps
  - 最长6秒视频
  - 电影级镜头移动效果
- **API密钥**: `MINIMAX_API_KEY`
- **定价**: ¥0.8/秒（高质量）

### ☁️ 云存储

#### 阿里云OSS
- **特色**:
  - 中国最大的云存储服务
  - 多区域支持，网络访问快
  - 成本效益高
  - 与国内CDN深度集成
- **配置项**:
  - `OSS_ACCESS_KEY_ID`
  - `OSS_ACCESS_KEY_SECRET`
  - `OSS_ENDPOINT`
  - `OSS_BUCKET_NAME`
- **定价**: ¥0.12/GB/月（标准存储）

## 🔧 配置说明

### 环境变量配置

在 `.env` 文件中添加以下配置：

```bash
# 中国AI服务API密钥
KIMI_API_KEY=your_kimi_api_key
GLM_API_KEY=your_glm_api_key
DOUBAO_API_KEY=your_doubao_api_key

# 图片生成
JIMENG_API_KEY=your_jimeng_api_key

# 视频生成
MINIMAX_API_KEY=your_minimax_api_key

# 阿里云OSS存储
OSS_ACCESS_KEY_ID=your_oss_access_key_id
OSS_ACCESS_KEY_SECRET=your_oss_access_key_secret
OSS_ENDPOINT=https://oss-cn-beijing.aliyuncs.com
OSS_BUCKET_NAME=your_bucket_name
OSS_REGION=cn-beijing

# 存储类型设置为oss
STORAGE_TYPE=oss
```

### API密钥获取

#### Kimi API
1. 访问 [Kimi开放平台](https://platform.moonshot.cn/)
2. 注册账号并完成认证
3. 创建应用获取API Key
4. 查看[定价详情](https://platform.moonshot.cn/pricing)

#### 智谱AI GLM
1. 访问 [智谱AI开放平台](https://open.bigmodel.cn/)
2. 注册并实名认证
3. 创建API Key
4. 查看[模型列表和定价](https://open.bigmodel.cn/pricing)

#### 豆包/即梦
1. 访问 [火山引擎](https://www.volcengine.com/product/doubao)
2. 开通豆包大模型服务
3. 获取API密钥
4. 即梦图片生成可通过第三方API接入

#### MiniMax
1. 访问 [MiniMax开放平台](https://www.minimaxi.com/)
2. 注册开发者账号
3. 创建应用获取API Key
4. 开通视频生成服务

#### 阿里云OSS
1. 访问 [阿里云OSS控制台](https://oss.console.aliyun.com/)
2. 创建Bucket
3. 获取AccessKey和SecretKey
4. 配置权限策略

## 🛠️ 工具使用示例

### 使用Kimi K2进行中文写作

```python
from app.agents.tools import tool_registry

# 获取Kimi客户端
kimi_tool = tool_registry.get_tool("kimi_client")

# 使用Kimi K2进行中文写作
result = await kimi_tool.execute({
    "action": "chinese_writing",
    "parameters": {
        "topic": "人工智能的未来发展",
        "style": "expository",
        "length": "medium",
        "tone": "professional",
        "model": "kimi-k2"  # 使用最新的K2模型
    }
})

# 使用K2的工具调用能力
result = await kimi_tool.execute({
    "action": "chat_completion",
    "parameters": {
        "messages": [
            {"role": "user", "content": "请帮我分析一下这个数据..."}
        ],
        "model": "kimi-k2",
        "temperature": 0.6,  # K2推荐温度
        "max_tokens": 4000
    }
})
```

### 使用即梦生成图片

```python
# 获取即梦图片工具
jimeng_tool = tool_registry.get_tool("jimeng_image")

# 文生图
result = await jimeng_tool.execute({
    "action": "text_to_image", 
    "parameters": {
        "prompt": "一只可爱的熊猫在竹林中玩耍，水墨画风格",
        "model": "general_v3.0",
        "size": "1024x1024",
        "style": "artistic",
        "num_images": 1
    }
})
```

### 使用MiniMax生成视频（支持首尾帧）

```python
# 获取MiniMax视频工具
minimax_tool = tool_registry.get_tool("minimax_video")

# 图生视频（首尾帧）
result = await minimax_tool.execute({
    "action": "image_to_video",
    "parameters": {
        "prompt": "平滑的镜头推进，展现画面的细节变化",
        "start_image": "https://example.com/start_frame.jpg",
        "end_image": "https://example.com/end_frame.jpg", 
        "duration": 6,
        "quality": "high",
        "motion_strength": 0.8
    }
})
```

### 使用阿里云OSS存储

```python
# 获取OSS存储工具
oss_tool = tool_registry.get_tool("oss_storage")

# 上传文件
result = await oss_tool.execute({
    "action": "upload",
    "parameters": {
        "local_path": "/path/to/video.mp4",
        "remote_path": "videos/generated_video.mp4",
        "public_read": True
    }
})
```

## 💰 成本对比

| 服务类型 | 国外服务 | 中国服务 | 优势 |
|---------|---------|---------|------|
| **文本生成** | OpenAI GPT-4: $0.03/1K tokens | Kimi K2: $0.15/1M输入, $2.5/1M输出 | MoE架构，智能体优化 |
| **图片生成** | DALL-E 3: $0.04/张 | 即梦: ¥0.05/张 | 价格相当，中文提示词更准确 |
| **视频生成** | RunwayML: $12/月 | MiniMax: ¥0.8/秒 | 按需付费，支持首尾帧 |
| **云存储** | AWS S3: $0.023/GB | 阿里云OSS: ¥0.12/GB | 国内访问快，价格合理 |

## 🌟 优势分析

### 网络优势
- **低延迟**: 服务器位于中国大陆，访问速度快
- **高可用**: 避免国际网络不稳定问题
- **合规性**: 符合中国数据安全法规

### 功能优势
- **中文优化**: 所有服务都对中文进行了专门优化
- **本土化**: 更好理解中国用户需求和使用习惯
- **集成度**: 服务间可以更好协同工作

### 成本优势
- **竞争定价**: 大多数服务价格优于国外同类产品
- **人民币结算**: 避免汇率波动风险
- **本土支付**: 支持支付宝、微信支付等

## 🔄 迁移指南

### 从国外服务迁移

1. **文本生成**: OpenAI → Kimi/GLM-4.5
2. **图片生成**: DALL-E/MidJourney → 即梦AI
3. **视频生成**: RunwayML → MiniMax
4. **云存储**: AWS S3 → 阿里云OSS

### 迁移步骤
1. 申请对应的API密钥
2. 更新环境变量配置
3. 测试服务可用性
4. 逐步切换生产流量
5. 监控服务质量和成本

## 🚨 注意事项

### API限制
- 每个服务都有不同的调用频率限制
- 建议实现请求队列和重试机制
- 监控API配额使用情况

### 数据合规
- 确保用户数据处理符合相关法规
- 注意敏感内容过滤
- 建立数据备份和恢复机制

### 服务稳定性
- 实现多服务商备份策略
- 建立服务监控和告警机制
- 准备服务降级方案

## 📊 监控和维护

### 关键指标
- API调用成功率
- 响应时间
- 成本控制
- 服务可用性

### 建议实践
- 定期更新API密钥
- 监控服务使用量
- 优化请求参数
- 建立成本预警

## 🔗 相关链接

- [Kimi开放平台](https://platform.moonshot.cn/)
- [智谱AI开放平台](https://open.bigmodel.cn/)
- [MiniMax开放平台](https://www.minimaxi.com/)
- [阿里云OSS](https://www.aliyun.com/product/oss)
- [豆包大模型](https://www.volcengine.com/product/doubao)

---

通过集成这些中国AI服务，项目可以为中国用户提供更好的体验，同时控制成本并确保服务稳定性。所有服务都已在代码中实现，可以通过配置环境变量即可使用。
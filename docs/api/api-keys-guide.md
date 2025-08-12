# 🔑 API密钥配置完整指南

## 🎯 概述

本短视频制作平台支持多个AI服务提供商，你可以根据需求和预算选择性配置。**至少需要配置一个AI服务的API密钥**。

## 📊 API密钥重要性等级

| 服务商 | 重要性 | 功能 | 推荐指数 | 费用情况 |
|--------|--------|------|----------|----------|
| **OpenAI** | 🔴 必需 | 文本生成、对话、脚本创作 | ⭐⭐⭐⭐⭐ | 按用量计费 |
| **Anthropic** | 🟡 可选 | 高质量文本生成、内容审核 | ⭐⭐⭐⭐ | 按用量计费 |
| **Stability AI** | 🟡 可选 | 图像生成、图片处理 | ⭐⭐⭐ | 按用量计费 |
| **Runway ML** | 🟢 增强 | 视频生成、视频编辑 | ⭐⭐⭐ | 订阅制 |

## 🚀 快速开始 - 最小配置

### 仅配置OpenAI（推荐新手）

**为什么选择OpenAI？**
- ✅ 功能最全面（文本生成、对话、内容创作）
- ✅ 生态最成熟，文档最完善
- ✅ 新用户通常有免费额度
- ✅ 一个密钥就能让系统正常运行

**配置步骤：**

1. **注册OpenAI账户**
   - 访问：https://platform.openai.com/
   - 点击"Sign up"注册账户
   - 验证邮箱和手机号

2. **获取API密钥**
   - 登录后访问：https://platform.openai.com/account/api-keys
   - 点击"Create new secret key"
   - 给密钥命名（如："short-video-maker"）
   - 复制生成的密钥（格式：`sk-...`）
   - ⚠️ **重要：立即保存密钥，页面关闭后无法再次查看**

3. **配置到项目中**
   ```env
   # 在.env文件中添加
   OPENAI_API_KEY=sk-your-actual-api-key-here
   ```

4. **测试配置**
   ```batch
   # 运行验证脚本
   cd backend
   python scripts\validate_system.py
   ```

## 🔑 详细API密钥获取指南

### 1. OpenAI API Key

**官网：** https://platform.openai.com/

**获取步骤：**
1. 注册/登录OpenAI账户
2. 进入 [API Keys页面](https://platform.openai.com/account/api-keys)
3. 点击 "Create new secret key"
4. 命名密钥（方便管理）
5. 复制密钥（`sk-...`开头）

**配置：**
```env
OPENAI_API_KEY=sk-proj-your-key-here
```

**费用：**
- 新用户通常有 $5-18 免费额度
- 按Token使用量计费
- GPT-4: ~$0.03/1K tokens
- GPT-3.5-turbo: ~$0.002/1K tokens

**使用场景：**
- ✅ 视频概念规划
- ✅ 脚本编写
- ✅ 内容优化
- ✅ 用户交互

### 2. Anthropic API Key (Claude)

**官网：** https://console.anthropic.com/

**获取步骤：**
1. 访问 Anthropic Console
2. 注册账户（需要邀请或申请）
3. 进入 API Keys 部分
4. 创建新密钥

**配置：**
```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**费用：**
- 按Token计费
- Claude-3: ~$0.01-0.08/1K tokens

**优势：**
- ✅ 内容质量高
- ✅ 上下文理解强
- ✅ 安全性好

### 3. Stability AI API Key

**官网：** https://platform.stability.ai/

**获取步骤：**
1. 注册 Stability AI 账户
2. 进入 API Keys 页面
3. 生成新的API密钥

**配置：**
```env
STABILITY_API_KEY=sk-your-stability-key-here
```

**费用：**
- 新用户通常有免费额度
- 按图像生成数量计费
- ~$0.02-0.20 per image

**功能：**
- ✅ 高质量图像生成
- ✅ 图像编辑和优化
- ✅ 多种艺术风格

### 4. Runway ML API Key

**官网：** https://runwayml.com/

**获取步骤：**
1. 注册 Runway ML 账户
2. 订阅适当的计划
3. 在 API 设置中获取密钥

**配置：**
```env
RUNWAY_API_KEY=your-runway-key-here
```

**费用：**
- 订阅制，月费 $12+
- 按处理时间计费

**功能：**
- ✅ AI视频生成
- ✅ 视频编辑
- ✅ 特效处理

## 💰 费用预估和选择建议

### 个人学习/测试（预算：$0-20/月）
```env
# 推荐配置：仅OpenAI
OPENAI_API_KEY=sk-your-openai-key-here
```
**优势：** 成本低，功能完整，适合学习

### 小型项目（预算：$20-100/月）
```env
# 推荐配置：OpenAI + Stability AI
OPENAI_API_KEY=sk-your-openai-key-here
STABILITY_API_KEY=sk-your-stability-key-here
```
**优势：** 支持文本+图像生成，功能较全

### 商业项目（预算：$100+/月）
```env
# 推荐配置：全套服务
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
STABILITY_API_KEY=sk-your-stability-key-here
RUNWAY_API_KEY=your-runway-key-here
```
**优势：** 功能最全，质量最高，支持所有特性

## 🛡️ API密钥安全最佳实践

### 1. 密钥保护
```env
# ❌ 错误：不要在代码中硬编码
const apiKey = "sk-your-key-here"

# ✅ 正确：使用环境变量
OPENAI_API_KEY=sk-your-key-here
```

### 2. 权限限制
- 为每个项目创建独单独的API密钥
- 设置适当的使用限额
- 定期轮换密钥

### 3. 监控使用量
- 定期检查API使用量和费用
- 设置使用量警报
- 监控异常调用

### 4. 开发vs生产
```env
# 开发环境 - 使用限制较严格的密钥
OPENAI_API_KEY=sk-dev-key-with-limits

# 生产环境 - 使用功能完整的密钥
OPENAI_API_KEY=sk-prod-key-full-access
```

## 🔧 配置验证和测试

### 1. 验证API密钥有效性
```batch
# 运行内置验证脚本
cd backend
python scripts\validate_system.py

# 单独测试OpenAI连接
python -c "
import openai
import os
from app.core.config import settings
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
response = client.chat.completions.create(
    model='gpt-3.5-turbo',
    messages=[{'role': 'user', 'content': 'Hello'}],
    max_tokens=5
)
print('OpenAI连接成功:', response.choices[0].message.content)
"
```

### 2. 测试各种功能
```batch
# 测试文本生成
curl -X POST "http://localhost:8000/api/v1/test/text-generation" ^
     -H "Content-Type: application/json" ^
     -d "{\"prompt\": \"Create a short video concept about AI\"}"

# 测试图像生成（如果配置了Stability AI）
curl -X POST "http://localhost:8000/api/v1/test/image-generation" ^
     -H "Content-Type: application/json" ^
     -d "{\"prompt\": \"A futuristic city\"}"
```

## 🚨 常见问题和解决方案

### 问题1：API密钥无效
**错误信息：** `Invalid API key`
**解决方案：**
1. 检查密钥是否正确复制（注意空格）
2. 确认密钥未过期
3. 检查账户是否有足够额度

### 问题2：配额不足
**错误信息：** `Rate limit exceeded` 或 `Quota exceeded`
**解决方案：**
1. 检查账户余额
2. 升级API计划
3. 减少并发请求数量

### 问题3：权限不足
**错误信息：** `Permission denied`
**解决方案：**
1. 检查API密钥权限设置
2. 确认模型访问权限
3. 联系服务提供商

### 问题4：网络连接问题
**错误信息：** `Connection timeout`
**解决方案：**
1. 检查网络连接
2. 配置代理（如果需要）
3. 增加超时时间设置

## 🌟 高级配置

### 模型选择优化
```env
# OpenAI模型配置
OPENAI_DEFAULT_MODEL=gpt-3.5-turbo  # 经济型
# OPENAI_DEFAULT_MODEL=gpt-4        # 高质量型

# 请求超时设置
AI_SERVICE_TIMEOUT=120

# 重试配置
AI_SERVICE_MAX_RETRIES=3
```

### 成本控制
```env
# 设置使用限制
MAX_TOKENS_PER_REQUEST=2000
MAX_REQUESTS_PER_MINUTE=10
ENABLE_COST_TRACKING=true
COST_ALERT_THRESHOLD=10.0
```

### 缓存优化
```env
# 启用AI响应缓存
ENABLE_AI_CACHE=true
AI_CACHE_TTL=3600
```

## 📞 技术支持

如果遇到API配置问题：

1. **查看官方文档**
   - [OpenAI文档](https://platform.openai.com/docs)
   - [Anthropic文档](https://docs.anthropic.com/)
   - [Stability AI文档](https://platform.stability.ai/docs)

2. **使用验证工具**
   ```batch
   python backend/scripts/validate_system.py
   ```

3. **查看日志**
   ```batch
   type backend\logs\app.log
   ```

4. **社区支持**
   - GitHub Issues
   - 项目讨论区

---

**🎉 配置完成后，你就可以开始创作AI驱动的短视频了！**

**💡 提示：建议从OpenAI开始，熟悉系统后再逐步添加其他服务。**
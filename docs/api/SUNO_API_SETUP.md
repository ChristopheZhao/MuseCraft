# 🎵 Suno AI背景音乐配置指南

## 1. 获取 Suno AI API 密钥

### 选项A：官方 Suno API（推荐）
1. 访问 [Suno API官方服务](https://sunoapi.org/)
2. 注册账户并获取API密钥
3. 选择合适的套餐：
   - 免费试用：通常提供有限的生成次数
   - 付费套餐：按次付费或包月套餐

### 选项B：第三方 API 提供商
- [AI/ML API](https://aimlapi.com/suno-ai-api)
- [API.box](https://api.box/suno)
- [Kie.ai](https://kie.ai/suno-api)

## 2. 配置环境变量

### 步骤 1：创建 .env 文件
```bash
# 从示例文件创建环境配置
cp .env.example .env
```

### 步骤 2：添加 Suno API 密钥
编辑 `.env` 文件，找到以下行并取消注释：
```bash
# Suno AI配置 (用于背景音乐生成)
SUNO_API_KEY=your-suno-api-key-here
```

将其修改为：
```bash
# Suno AI配置 (用于背景音乐生成)
SUNO_API_KEY=sk-your-actual-suno-api-key
```

## 3. 验证配置

### 测试 API 连接
```bash
# 运行测试脚本验证 Suno AI 连接
cd backend
python -c "
import os
from app.agents.tools.ai_services.suno_client import SunoClientTool

# 检查API密钥
api_key = os.getenv('SUNO_API_KEY')
if not api_key:
    print('❌ SUNO_API_KEY not found in environment')
else:
    print(f'✅ SUNO_API_KEY found: {api_key[:10]}...')
    
# 创建工具实例
tool = SunoClientTool()
print(f'✅ SunoClientTool initialized successfully')
print(f'🔧 Tool functional: {tool._functional}')
"
```

## 4. 音乐生成功能特性

### 支持的功能
- ✅ **文本到音乐**：根据描述生成背景音乐
- ✅ **风格控制**：cinematic, ambient, electronic, orchestral等
- ✅ **情绪匹配**：happy, calm, epic, mysterious等
- ✅ **时长控制**：10秒到5分钟
- ✅ **纯音乐模式**：无歌词的背景音乐
- ✅ **商业授权**：生成的音乐可商业使用

### 音乐风格
```python
# 支持的音乐风格
music_styles = [
    "cinematic",    # 电影配乐风格
    "ambient",      # 环境音乐
    "electronic",   # 电子音乐
    "orchestral",   # 管弦乐
    "acoustic",     # 原声音乐
    "jazz",         # 爵士乐
    "classical",    # 古典音乐
    "corporate",    # 商务音乐
    "uplifting",    # 振奋人心
    "dramatic",     # 戏剧化
    "peaceful",     # 平静安详
    "energetic"     # 充满活力
]
```

### 情绪类型
```python
# 支持的情绪类型
mood_types = [
    "happy",        # 快乐
    "sad",          # 悲伤
    "excited",      # 兴奋
    "calm",         # 平静
    "mysterious",   # 神秘
    "epic",         # 史诗
    "romantic",     # 浪漫
    "adventurous",  # 冒险
    "playful",      # 活泼
    "serious"       # 严肃
]
```

## 5. 完整的环境配置示例

```bash
# .env 文件中的完整AI服务配置
# =============================================================================
# AI服务API密钥 - 国际服务
# =============================================================================

# OpenAI配置 (推荐)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Suno AI配置 (用于背景音乐生成)
SUNO_API_KEY=sk-your-suno-api-key-here

# =============================================================================
# AI服务API密钥 - 中国服务
# =============================================================================

# GLM-4.5 (智谱AI) - 支持文本生成、图像生成(CogView)、视频生成(CogVideoX)
GLM_API_KEY=your-glm-api-key-here
ZHIPU_API_KEY=your-glm-api-key-here  # GLM_API_KEY 的别名
```

## 6. 开始使用

配置完成后，重启开发服务器：
```bash
cd backend
python scripts/start_dev.py
```

现在创建视频时将自动生成背景音乐！🎵

## 7. 故障排除

### 常见问题

**Q: 显示 "SunoClientTool not functional - API key required"**
A: 检查 `.env` 文件中的 `SUNO_API_KEY` 是否正确配置并重启服务

**Q: 音乐生成失败**
A: 检查 API 密钥是否有效，账户是否有余额

**Q: 音乐生成超时**
A: Suno AI 通常需要 20-120 秒生成音乐，请耐心等待

**Q: 生成的音乐与视频不匹配**
A: 系统会自动分析视频内容匹配音乐风格，如需自定义可修改 `AudioGeneratorAgent` 的逻辑

### 日志检查
```bash
# 查看音乐生成日志
tail -f logs/app.log | grep -i "audio\|music\|suno"
```

## 8. 成本估算

- **免费试用**：通常提供 5-10 次生成
- **付费套餐**：
  - 按次付费：约 $0.10-0.50/首
  - 包月套餐：$10-50/月不等
  - 企业套餐：定制价格

生成一个30秒的短视频背景音乐成本约 $0.20-0.30。

---

配置完成后，你的短视频就能拥有专业的背景音乐了！🎬✨
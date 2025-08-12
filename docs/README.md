# 📚 文档中心

本目录包含短视频生成平台的所有技术文档，按照功能分类组织。

## 📂 文档结构

### 🏗️ `/architecture` - 架构设计文档
- **[agent-design-patterns.md](architecture/agent-design-patterns.md)** - 多智能体系统设计模式
  - Agent基类设计、工具系统、内存管理、提示词模板等核心架构
- **[multi-agent-system-analysis.md](architecture/multi-agent-system-analysis.md)** - 多智能体系统分析报告
  - 系统架构分析、Agent协作流程、技术实现细节
- **[tools-configuration.md](architecture/tools-configuration.md)** - 工具系统配置指南
  - Tool Registry设计、工具插件开发、配置管理

### 🚀 `/deployment` - 部署相关文档
- **[deployment-guide.md](deployment/deployment-guide.md)** - 生产环境部署指南
  - 完整部署流程、环境配置、验证测试、运维配置
- **[windows-deployment-guide.md](deployment/windows-deployment-guide.md)** - Windows部署指南
  - Windows环境特殊配置、IIS部署、服务管理
- **[windows-native-setup.md](deployment/windows-native-setup.md)** - Windows原生环境设置
  - 开发环境搭建、依赖安装、常见问题

### 💻 `/development` - 开发指南
- **[claude-assistant.md](development/claude-assistant.md)** - Claude AI助手集成指南
  - CLAUDE.md配置说明、AI辅助开发最佳实践
- **[migration-to-uv.md](development/migration-to-uv.md)** - 迁移到UV包管理器
  - UV工具介绍、迁移步骤、性能对比
- **[optimization-summary.md](development/optimization-summary.md)** - 系统优化总结
  - 性能优化记录、最佳实践、优化成果

### 🔌 `/api` - API文档
- **[api-keys-guide.md](api/api-keys-guide.md)** - API密钥配置指南
  - 各AI服务API申请流程、配置方法、费用说明
- **[china-ai-services.md](api/china-ai-services.md)** - 中国AI服务集成
  - 百度、阿里、智谱等国内AI服务接入
- **[kimi-k2-update.md](api/kimi-k2-update.md)** - Kimi K2 API更新说明
  - 新版API变更、迁移指南、功能增强

### 🧪 `/testing` - 测试文档
- **[integration-test-guide.md](testing/integration-test-guide.md)** - 集成测试执行指南
  - 测试环境搭建、测试用例说明、执行步骤

### 🔧 `/operations` - 运维文档
- **[monitoring-guide.md](operations/monitoring-guide.md)** - 监控配置指南
  - 监控指标、告警配置、日志管理
- **[troubleshooting.md](operations/troubleshooting.md)** - 故障排查指南
  - 常见问题、调试技巧、性能分析

## 📖 文档使用说明

### 新手入门
1. 先阅读项目根目录的 [README.md](../README.md) 了解项目概况
2. 查看 [架构设计文档](architecture/agent-design-patterns.md) 理解系统设计
3. 根据你的操作系统，参考相应的部署指南

### 开发者
1. 阅读 [开发指南](development/claude-assistant.md) 了解开发流程
2. 查看 [API文档](api/api-keys-guide.md) 配置所需服务
3. 参考 [测试指南](testing/integration-test-guide.md) 进行测试

### 运维人员
1. 使用 [部署清单](deployment/deployment-checklist.md) 进行部署
2. 配置 [监控系统](operations/monitoring-guide.md)
3. 准备 [故障排查手册](operations/troubleshooting.md)

## 🔄 文档维护

- 文档应保持与代码同步更新
- 使用Markdown格式，遵循项目编码规范
- 重要变更需要更新相关文档
- 定期审查和更新过时内容

## 📝 贡献指南

欢迎贡献文档改进！请遵循以下原则：
- 保持文档结构清晰
- 使用简洁明了的语言
- 包含实际的代码示例
- 更新文档索引

---

最后更新时间：2024-01-XX
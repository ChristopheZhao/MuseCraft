# 监控配置指南

## 概述

本文档介绍如何配置和使用短视频生成平台的监控系统。

## 监控指标

### 系统指标
- CPU使用率
- 内存使用率
- 磁盘I/O
- 网络流量

### 应用指标
- API响应时间
- 请求成功率
- 并发连接数
- 任务队列长度

### AI服务指标
- API调用次数
- 调用成功率
- 响应时间
- 成本统计

## 监控端点

- `/health` - 健康检查
- `/metrics` - Prometheus格式指标
- `/api/v1/stats` - 业务统计数据

## 告警配置

### 关键告警
- 服务不可用
- API错误率 > 5%
- 响应时间 > 5秒
- 磁盘空间 < 10%

### 配置示例

```yaml
alerts:
  - name: high_error_rate
    condition: error_rate > 0.05
    duration: 5m
    severity: critical
    
  - name: slow_response
    condition: p95_latency > 5000
    duration: 10m
    severity: warning
```

## 日志管理

### 日志级别
- ERROR: 错误信息
- WARN: 警告信息
- INFO: 一般信息
- DEBUG: 调试信息

### 日志轮转
- 按天轮转
- 保留30天
- 自动压缩

## Grafana仪表板

项目提供了预配置的Grafana仪表板，位于 `monitoring/grafana-dashboard.json`。

### 导入步骤
1. 登录Grafana
2. 导入仪表板JSON
3. 配置数据源
4. 调整时间范围

## 性能分析

### APM集成
支持与以下APM工具集成：
- New Relic
- DataDog
- AppDynamics

### 分析工具
- Python: cProfile, py-spy
- 数据库: pg_stat_statements
- Redis: redis-cli --stat
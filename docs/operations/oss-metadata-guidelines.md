# OSS 自定义元数据使用指引

## 背景

在 2025-09-24 的 image_agent 流程中，参考图上传到阿里云 OSS 时频繁触发 `SignatureDoesNotMatch`。同样的密钥在调试脚本中却一直成功，导致排查时间被拉长。当日的问题最终定位在元数据命名上。

## 现象与日志

- image_agent 上传日志中出现：
  - `OSS upload signature mismatch detected, refreshing client and retrying once`
  - 403 响应内的 `StringToSign` 缺少 `x-oss-meta-scene_number`。
- 调试脚本 `repro_image_agent_oss.py` 使用相同 AccessKey 成功上传。

## 根因分析

- image_agent 在元数据中传入了 `scene_number`，最终形成 header `x-oss-meta-scene_number`。
- 阿里云 OSS 要求自定义元数据 key 只能包含 **小写字母、数字、短横线**（`-`）。带下划线的 key 会被服务端忽略。
- 客户端签名时包含了该 header，服务器签名时将其丢弃，因此 HMAC 校验失败并返回 `SignatureDoesNotMatch`。

## 修复措施

- 在 `oss_storage_tool` 中新增 `_normalize_meta_key()`：
  - 将元数据 key 统一转为小写。
  - 非法字符统统替换为短横线 `-`。
  - 去除首尾的短横线，避免空 key。
- 所有 `metadata` 写入都走该函数，未来新增字段无需再记规则。
- 保留 `secret_sha1`、`OSS_RETRY_HEADERS` 调试日志，方便对比请求内容。

## 建议实践

1. **始终经过工具层规范化元数据 key**，不要在各 Agent 手工拼接 `x-oss-meta-*`。
2. **新增字段时优先使用符合规范的命名（小写 + `-`）**，即使规范化函数存在，也要在意图上保持一致。
3. **遇到 `SignatureDoesNotMatch` 时，第一时间对比服务端返回的 `StringToSign` 与客户端 headers**，即可快速定位是哪一个字段差异。
4. **调试信息要打印指纹而非明文密钥**，既能排查“实际加载哪套凭证”，又不会泄漏敏感数据。

## 参考文件

- `backend/app/agents/tools/storage/oss_storage_tool.py`
- `backend/app/agents/tools/ai_services/image_generation_tool.py`
- `backend/scripts/repro_image_agent_oss.py`

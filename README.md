# The Company Agent

企业 AI 工作平台 V1，目标是通过一个 Chat 入口组合企业知识、临时文件、数据库、API/MCP、程序能力和可复用 Skill/Plugin。

## 当前状态

项目处于原生 Windows 开发阶段，不依赖 Docker：

- 方案文档：[V1 技术设计方案（评审稿）](需求文档/v1/v1_technical_design_review.md)
- 主 Chat 模型：Agnes 2.5 Flash
- Vision：SiliconFlow `Qwen/Qwen3.5-4B`
- Embedding：SiliconFlow `BAAI/bge-m3`
- 关系数据库：本机 MySQL
- 开发期向量检索：本机 Elasticsearch
- 开发期任务流：MySQL Outbox + Redis Streams

完整安全 Sandbox、隔离 stdio MCP 和 Office 预览属于后续发布闸门；当前不会开放任意用户代码执行。

## 安全

密钥、数据库密码、连接字符串和本地运行数据禁止提交到 Git。请使用未跟踪的 `.env.local` 或本地 Secret Store。模型 API Key 已在聊天中出现，正式联调前应轮换测试 Key。

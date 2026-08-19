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

## Native 开发启动

当前分支不要求 Docker。首次配置本地密钥时，在 PowerShell 执行：

```powershell
./scripts/setup-native-secrets.ps1
```

脚本会在本地交互读取 MySQL 密码和可选模型 Key，写入被 Git 忽略的 `.env.local`；不会在终端回显 Secret。没有 `.env.local` 时，Provider Probe 只做配置检查，不会调用外部模型。

基础检查：

```powershell
.venv/Scripts/ruff.exe check backend tests
.venv/Scripts/pytest.exe
.venv/Scripts/alembic.exe heads
```

启动 API：

```powershell
.venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
cd frontend
& E:/Environment_f/nvm_f/v22.13.0/npm.cmd run dev
```

## 安全

密钥、数据库密码、连接字符串和本地运行数据禁止提交到 Git。请使用未跟踪的 `.env.local` 或本地 Secret Store。模型 API Key 已在聊天中出现，正式联调前应轮换测试 Key。

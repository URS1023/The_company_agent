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

native-dev 只开放仓库内经过测试的确定性分析器和受限的 `python.safe` 数据变换（无 import、文件、网络和任意主机访问）；完整安全 Sandbox、隔离 stdio MCP 和 LibreOffice 预览属于后续发布闸门，当前不会开放任意用户代码执行。

## Native 开发启动

当前分支不要求 Docker。首次配置本地密钥时，在 PowerShell 执行：

本项目的原生脚本会优先使用 Conda 环境 `E:\Environment_f\conda_envs\company-agent`；也可以通过进程环境变量 `COMPANY_AGENT_PYTHON` 指定其他 Python 路径。首次安装 Conda 环境：

```powershell
conda create --prefix E:\Environment_f\conda_envs\company-agent python=3.12 -y
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent python -m pip install -e ".[files,dev]"
```

安装完成后，后续不需要手动激活 Conda；仓库提供的 `.cmd` 入口会自动选择该环境。

```powershell
./scripts/setup-native-secrets.cmd
```

如果直接运行 `.ps1` 被 Windows 的执行策略拦截，可以使用上面的 `.cmd` 入口；它只对当前 PowerShell 子进程启用 `Bypass`，不会修改系统或用户的持久执行策略。也可以显式执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-native-secrets.ps1
```

脚本会在本地交互读取 MySQL 密码和可选模型 Key，写入被 Git 忽略的 `.env.local`；不会在终端回显 Secret。没有 `.env.local` 时，Provider Probe 只做配置检查，不会调用外部模型。

基础检查：

```powershell
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent ruff check backend tests
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent python -m pytest
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent python -m alembic heads
```

浏览器回归（会启动临时 SQLite API，不会触碰本地 MySQL）：

```powershell
cd frontend
& E:/Environment_f/nvm_f/v22.13.0/npm.cmd run test:e2e
```

也可以直接访问 `/demos` 验证招投标缺口检测和财务经营分析两个示例；真实 Chat Run 通过 `/runs/:runId` 查看步骤、Tool 调用和错误诊断。

启动 API：

```powershell
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

另开 PowerShell 窗口启动原生 Worker：

```powershell
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent python -m backend.runtime.worker relay
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent python -m backend.runtime.worker agent
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent python -m backend.runtime.ingestion
```

配置好 `.env.local` 后，也可以由脚本统一启动/停止本项目自己的进程：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-native.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop-native.ps1
```

或使用不受执行策略影响的入口：

```powershell
./scripts/start-native.cmd
./scripts/stop-native.cmd
```

脚本不会启动、停止或修改现有 MySQL、Redis、Elasticsearch 服务。

数据库迁移和首个管理员创建需要先确认 `.env.local` 中的 MySQL 连接可用：

```powershell
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent python -m alembic upgrade head
conda run --no-capture-output --prefix E:\Environment_f\conda_envs\company-agent python -m backend.scripts.bootstrap_admin --username workspace-admin
```

也可以用一次性验证脚本确保配置的 MySQL 数据库存在、执行迁移、初始化管理员和完成三个 Provider 的真实 Probe（管理员密码仍以交互方式读取）：

```powershell
./scripts/verify-native.cmd -AdminUsername workspace-admin
```

等价的显式命令为：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-native.ps1 -AdminUsername workspace-admin
```

启动 API 和原生 Worker 后，可以运行认证冒烟测试：

```powershell
./scripts/run-native-smoke.cmd -Username workspace-admin
```

等价的显式命令为：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-smoke.ps1 -Username workspace-admin
```

脚本只输出 HTTP 状态和 Run 状态，不输出模型回答、文件内容、密码或 API Key。

启动前端：

```powershell
cd frontend
& E:/Environment_f/nvm_f/v22.13.0/npm.cmd run dev
```

## 安全

密钥、数据库密码、连接字符串和本地运行数据禁止提交到 Git。请使用未跟踪的 `.env.local` 或本地 Secret Store。模型 API Key 已在聊天中出现，正式联调前应轮换测试 Key。

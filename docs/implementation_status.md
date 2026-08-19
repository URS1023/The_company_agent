# Implementation Status

更新时间：2026-08-20  
当前分支：`dev/native-gate0`  
远程：`origin/dev/native-gate0`

## 已完成

- GitHub 远程已配置，开发分支已推送。
- 原生 Windows 开发骨架：FastAPI、Next.js、Python 3.12 venv、Node 22。
- `.env.example` 和安全的 PowerShell Secret 配置脚本。
- MySQL/Redis/Elasticsearch/LocalFileStorage 适配接口。
- Agnes Chat Provider、SiliconFlow Vision/Embedding Provider Probe。
- Admin/Member 本地账号模型、Argon2id 密码、opaque Session。
- Admin 创建成员和一次性临时密码 API。
- Organization、Workspace、Conversation、Message、Run、RunEvent、Outbox、RunStep、ToolCall、ModelCall、Citation、Audit 迁移。
- Conversation/Run 创建、幂等键、资源快照、SSE Event Stream、取消/重试/续接和失败诊断。
- Redis Streams Outbox Relay/Agent Worker/Knowledge Ingestion Worker 基础实现。
- 临时文件上传、Hash、Workspace/Owner 绑定、删除和列表。
- Knowledge Base、Knowledge Document、Knowledge Chunk 和显式文件入库边界。
- SiliconFlow BGE-M3 Embedding → Elasticsearch `dense_vector`/kNN 适配。
- Chat 页面、登录页面、真实 Run/SSE 调用骨架和证据轨道视觉元素。
- DOCX/PPTX/XLSX/PDF Renderer API 已能从 Run 生成并保存 Artifact；Artifact 支持预览、下载、继续作为输入。
- Tool Gateway 已覆盖 HTTP/只读 SQL/MCP Streamable HTTP/Database/Builtin/可信 Sandbox，参数编译、来源策略和结果标准化均在调用前执行。
- Connector → Tool → ToolVersion → Plugin Binding 数据模型已建立。
- Skill/Connector/Plugin 必须先 Test Run，再允许 Publish。
- 招投标缺口检测、财务分析 Builtin Tool、结构化业务 Demo、Run Capability Proposal 和自然语言 Capability Builder 已加入。
- 管理员成员列表、停用、重置密码和会话撤销页面已加入。
- Skill/Connector/Plugin 版本列表、Draft、复制、分享、回滚、Tool 启停和 MCP 工具发现已加入。
- 文件批量上传、Knowledge 文档加入/删除/重建索引、Chat 文件/知识库/Plugin Context Chip 已加入。
- Admin Secret、Model Profile/安全 Probe、Audit Log 和 Run Trace 页面已加入。

## 已验证

```text
Python 3.12 compile      passed
Ruff                     passed
Pytest                   52 passed
Ruff                     passed
Alembic SQL generation   passed (`0002_runtime_trace`)
Next ESLint              passed
Next production build    passed
Next 16 routes           production build passed
FastAPI /health/live     HTTP 200
Redis PING               PONG
Elasticsearch info       8.14.3
Elasticsearch kNN        random index create/search/delete passed
Redis Streams            random stream/group/read/ack/delete passed
Playwright E2E           14 passed (Chromium + mobile Chromium, serialized SQLite server)
```

## 尚未执行

- 没有执行真实 MySQL 上的 `alembic upgrade head`，因为 `.env.local` 尚未由用户通过本地安全脚本配置；已通过 `--sql` 生成并检查两段迁移。
- 没有使用聊天中出现的 Agnes/SiliconFlow Key 发起模型请求。
- 没有把聊天中的 MySQL 密码写入任何文件或命令。
- 没有修改现有 MySQL、Redis、Elasticsearch 服务配置。
- native-dev 只开放仓库内经过测试的确定性分析器和受限 `python.safe` 数据变换；任意 Python、文件/网络访问和普通用户 stdio MCP 仍保持关闭，需安全发布阶段隔离运行时后开启。

## 下一步

用户在本机执行：

```powershell
./scripts/setup-native-secrets.ps1
```

然后再运行：

```powershell
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/company-agent-bootstrap.exe --username workspace-admin
.venv/Scripts/company-agent-probe.exe agnes --live
.venv/Scripts/company-agent-probe.exe siliconflow-vision --live
.venv/Scripts/company-agent-probe.exe siliconflow-embedding --live
```

这些命令会真正验证数据库权限、模型 Key、图片输入和 BGE-M3 向量维度；执行前应将聊天中出现过的测试 Key 轮换为新的测试 Key。

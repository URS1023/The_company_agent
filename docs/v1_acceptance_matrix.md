# V1 验收矩阵

本矩阵把 `需求文档/v1/v1_requirements.md` 的 V1 必须实现项映射到代码入口和自动化证据。`自动化通过` 表示不依赖真实外部账号的本地测试已通过；`真实联调待执行` 只适用于必须使用用户本机 MySQL/模型凭据的闸门。

| V1 要求 | 当前实现 | 证据 |
| --- | --- | --- |
| Chat、Streaming | Next Chat + Run SSE + Worker `message.delta` | `tests/test_run_api.py`, `tests/test_worker_execution.py`, Playwright 14 passed |
| 多文件/临时文件 | `/files/batch`、文件 Context Snapshot、文件魔数/大小校验 | `tests/test_files_api.py`, `frontend/tests/e2e/authenticated-pages.spec.ts` |
| Knowledge Base/RAG | Parser、Chunk、SiliconFlow BGE-M3、Elasticsearch kNN、Citation | `tests/test_knowledge_api.py`, `tests/test_processors.py`；真实 Key/ES 索引联调待执行 |
| 图片/扫描件识别 | SiliconFlow Qwen Vision Base64 路径；未启用时明确失败 | `backend/app/services/context.py`, `backend/runtime/ingestion.py`, `tests/test_providers.py`；真实 Vision Probe 待执行 |
| REST Connector | SSRF 校验、Schema、Secret Auth、OAuth Client Credentials、结果标准化 | `tests/test_tools.py`, `tests/test_capabilities_api.py` |
| MCP Connector | Streamable HTTP 初始化、工具发现、调用和结果标准化 | `tests/test_tools.py`, `tests/test_capabilities_api.py` |
| Database Connector | MySQL/PostgreSQL 只读 SQL、Schema/Table/Query Tool | `tests/test_tools.py`, `tests/test_capabilities_api.py`；真实数据库连接待执行 |
| Python Sandbox | Trusted Builtin + 受限 `python.safe`；禁止 import/文件/网络/任意主机代码 | `tests/test_tools.py`, `tests/test_worker_tools.py`, `tests/test_worker_tool_loop.py` |
| Skill 创建/修改/版本 | Root + Draft/Published Version、Patch 生成 Draft、回滚 Draft、Test Run | `tests/test_capabilities_api.py` |
| Plugin 创建/修改/使用 | Skill/Tool/Resource Binding、Plugin Run、Chat 选择、Tool Loop | `tests/test_capabilities_api.py`, `tests/test_worker_tool_loop.py`, Playwright |
| Plugin 复制/分享/回滚 | 复制时复制绑定、Workspace 分享、历史版本回滚 | `tests/test_capabilities_api.py` |
| Artifact | DOCX/PPTX/XLSX/PDF Renderer、Preview、Download、Use-as-input、Lineage | `tests/test_processors.py`, `tests/test_artifacts_api.py`, `tests/test_artifact_service.py` |
| Run 状态/Trace | Run、RunStep、ToolCall、ModelCall、Event、SSE Cursor、Cancel/Retry/Continue | `tests/test_run_api.py`, `tests/test_worker_execution.py` |
| Workspace/权限 | Organization/Workspace、Admin/Member、Owner/Workspace Visibility、Binding IDOR 校验 | `tests/test_auth_api.py`, `tests/test_capabilities_api.py` |
| Secret | AES-GCM 密文、禁止内嵌凭据、轮换、撤销、只返回元数据 | `tests/test_capabilities_api.py`, `tests/test_security.py` |
| Model Gateway/Profile | Agnes reasoning、SiliconFlow Vision/Embedding、Profile/Probe 记录和重试 | `tests/test_providers.py`, `tests/test_health_and_config.py`；真实 Probe 待执行 |
| Audit | 用户、文件、知识、能力、Run、Artifact、Model Probe 等动作 | `tests/test_auth_api.py`, `tests/test_run_api.py`, `tests/test_health_and_config.py` |
| 招投标 Demo | Requirement Spec、缺口识别、Document Spec、DOCX/PDF Renderer | `tests/test_builtin_tools.py`, `tests/test_demos_api.py`, Playwright `/demos` |
| 财务 Demo | Decimal 汇总、预算偏差、Presentation/Spreadsheet Spec、Tool Loop | `tests/test_builtin_tools.py`, `tests/test_demos_api.py`, `tests/test_worker_tool_loop.py`, Playwright `/demos` |

## 当前未闭合的真实环境闸门

代码和本地 Mock/SQLite/HTTP/MCP 测试已经通过，但以下证据必须在用户机器上使用本地 Secret 取得后才能标记 V1 完成：

1. `alembic upgrade head` 在用户的 MySQL 账号上成功执行。
2. Agnes `agnes-2.5-flash` 真实 Chat/Streaming/Tool Loop 请求成功。
3. SiliconFlow `Qwen/Qwen3.5-4B` 真实图片输入请求成功。
4. SiliconFlow `BAAI/bge-m3` 真实 Embedding 返回 1024 维，并完成 ES 索引/检索。
5. 本地 MySQL DataSource 的 `SELECT`、Schema/表描述和权限拒绝路径成功。
6. 原生 Relay、Agent、Ingestion Worker 在真实 Redis/MySQL/ES 上完成一次两 Demo Run。

执行入口：

```powershell
./scripts/setup-native-secrets.ps1
./scripts/verify-native.ps1 -AdminUsername workspace-admin
```

启动原生 API/Worker 后的认证冒烟入口：

```powershell
./scripts/run-native-smoke.ps1 -Username workspace-admin
```

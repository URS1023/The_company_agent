# 企业 AI 工作平台 V1 技术设计方案（评审稿）

> 文档版本：0.2  
> 文档状态：待用户审核  
> 编制日期：2026-08-20  
> 需求基线：`v1_requirements.md`  
> 交付目标：完成 V1 全部必选能力、可供真实用户通过界面使用，并自动验收招投标与财务经营分析两个业务示例。  
> 安全说明：本文档不记录任何数据库密码、模型 API Key 或其它 Secret 明文。

> 0.2 变更：当前开发阶段不搭建 Docker；复用本机 MySQL、Redis 和 Elasticsearch；主 Chat 保持 Agnes 2.5 Flash，Embedding 改用硅基流动 `BAAI/bge-m3`，Vision 改用硅基流动 `Qwen/Qwen3.5-4B`；完整安全 Sandbox 延后到 V1 发布闸门。

---

# 1. 方案结论

本项目采用“原生 Windows 本地开发 → 安全本地发布”的两阶段路线。当前开发阶段使用模块化单体、独立原生 Worker、现有 MySQL/Redis/Elasticsearch 和本地文件存储，不要求 Docker；完整 V1 发布前再加入一次性容器 Sandbox 和隔离 MCP Runner。

V1 不是只完成后端接口或演示页面，而是交付一个能够由管理员配置、由普通成员直接使用的完整产品：

```text
管理员初始化系统并创建成员账号
  ↓
成员使用账号密码登录
  ↓
在 Chat 中上传文件、选择知识库/插件/数据源
  ↓
系统异步创建 Run，流式展示执行进度
  ↓
模型读取上下文并调用 HTTP / MCP / Database / Sandbox Tool
  ↓
参数、来源、权限和业务规则校验
  ↓
生成 DOCX / XLSX / PPTX / PDF / 图表等 Artifact
  ↓
成员预览、下载或把 Artifact 作为下一次输入
  ↓
成功 Run 保存为 Skill，并组合 Tool/Resource 形成 Plugin
  ↓
同一 Workspace 的授权用户再次稳定使用
```

本方案把用户所说的“两个示例”定义为：

1. 招投标文件生成。
2. 财务经营分析及 PPT 生成。

原需求中的“企业已有 API”场景仍然实现和自动测试，但作为平台级 Connector 验收，不计入两个业务示例。

---

# 2. 已确定的技术决策

用户未指定的事项按以下方案执行；审核通过后视为 V1 基线。

| 编号 | 决策 | V1 选择 | 原因 |
|---|---|---|---|
| TD-01 | 部署方式 | 本地单节点，先开发环境后同构本地交付 | 满足当前验证目标，同时保持未来私有部署迁移能力 |
| TD-02 | 登录方式 | 用户名 + 密码，不开放注册，由管理员创建成员 | 符合用户要求，降低 V1 身份系统复杂度 |
| TD-03 | 首个管理员 | 部署 CLI 交互式创建 | 不提供硬编码默认账号和密码 |
| TD-04 | 分享与访问 | `private` / `workspace` 两级可见性，Admin/Member 两级角色 | 满足基础分享和资源权限，并为未来 ACL 预留 |
| TD-05 | Connector 与 Tool | 正式拆分，一对多 | 一个 MCP Server 或 API 可以暴露多个 Tool |
| TD-06 | 业务数据库 | 本机 MySQL 8.0，平台库与示例业务库分离 | 使用用户现有环境，同时避免平台表与业务数据混用 |
| TD-07 | 向量数据库 | 原生开发复用 Elasticsearch 8.14.3；通过 VectorStore 接口保留 Qdrant | 当前 Elasticsearch 已运行且支持 `dense_vector`/kNN，避免新增服务 |
| TD-08 | 队列与缓存 | MySQL Transactional Outbox + Redis Streams | 兼容当前 Windows Redis 5，不依赖 Windows 支持较弱的 Celery Worker |
| TD-09 | 文件存储 | 原生开发使用受控 LocalFileStorage；发布时可切换 MinIO/S3 | 当前没有 MinIO；存储接口保持不变，开发阶段减少外部依赖 |
| TD-10 | 主聊天模型 | Agnes 2.5 Flash，经 Model Gateway 调用 Chat Completions | 官方文档明确支持流式、工具调用和图像 URL 输入 |
| TD-11 | Embedding | 硅基流动 `/v1/embeddings` + `BAAI/bge-m3`，固定 1024 维 | 官方支持 8192 Token 输入；适合中文、多语言和长文档 RAG |
| TD-12 | 视觉输入 | 硅基流动 `/v1/chat/completions` + `Qwen/Qwen3.5-4B` | 官方标记为多模态模型，支持 URL/Base64 图片，解决本地图片无法给 Agnes 公网访问的问题 |
| TD-13 | MCP | 支持 stdio、Streamable HTTP；兼容旧 HTTP+SSE 作为过渡 | 符合当前 MCP 标准并兼容已有服务 |
| TD-14 | HTTP Auth | None、API Key、Bearer、Basic、OAuth2 Client Credentials | 覆盖常见机器到机器企业接口；不做交互式 OAuth 授权码流程 |
| TD-15 | Database Connector | PostgreSQL + MySQL，默认只读；财务示例使用 MySQL | 满足原 V1 范围并匹配本地环境 |
| TD-16 | Sandbox | 当前只运行可信内置分析器；普通用户任意 Python 执行保持关闭；发布前补一次性容器 | 暂不安装 Docker，但不能因此降低最终 Sandbox 安全标准 |
| TD-17 | 文档生成 | 先实现结构化 Spec + Python Renderer；LibreOffice 预览在安装后启用 | 当前机器没有 LibreOffice，不阻塞 DOCX/XLSX/PPTX 文件生成验证 |
| TD-18 | API 风格 | REST `/api/v1` + OpenAPI；SSE 用于 Run Event | 资源边界清晰，前后端契约易于生成和测试 |
| TD-19 | 服务形态 | FastAPI 模块化单体 + 原生 Agent/Ingestion/Render Worker 进程 | 当前无需容器，同时保留未来同镜像多角色部署方式 |
| TD-20 | UI 方向 | 借鉴 ChatGPT Web 的交互骨架，使用自有品牌、色板和组件 | 保持熟悉度，但不复制 OpenAI 品牌或资产 |

---

# 3. 当前本地环境预检

2026-08-20 的只读环境检查结果：

| 项目 | 当前状态 | 设计影响 |
|---|---|---|
| MySQL | 8.0.46，`3306` 正在监听；监听地址显示为 `::` | 可作为平台元数据和财务示例数据库；账号密码尚未通过安全 Secret 通道实测，真实使用前核对 `bind_address` 与防火墙 |
| Redis | Windows Redis 5.0.14.1，`6379` 返回 `PONG` | 可做原生开发的 Stream/通知；版本较旧，只作为本地开发依赖 |
| Elasticsearch | 8.14.3 Basic License，`9200` 可访问 | 支持 `dense_vector`/kNN，可直接作为开发期 VectorStore |
| Elasticsearch 安全 | HTTP 无认证，监听范围不只 localhost | 仅允许虚构测试数据；真实企业数据前必须隔离并启用认证 |
| Node.js | NVM 中有 20.20.2、22.13.0、23.11.1 | 项目固定使用 Node 22 LTS，不使用当前活动的 Node 23 |
| Python | uv 提供干净的 CPython 3.12.13；系统另有 3.14.6 | 项目从 Python 3.12 独立 venv 开始；不污染系统 3.14 环境 |
| Python 包 | 3.12 环境当前为空 | 实施时才创建项目 venv 和锁定依赖；本轮未安装任何包 |
| FFmpeg | 8.1.2 可用 | 可处理媒体、生成预览中间件 |
| ClamAV | 1.5.3 CLI 可用，但病毒库超过 7 天未更新 | 安装阶段更新病毒库后再启用上传扫描 |
| LibreOffice | 未发现 | DOCX/XLSX/PPTX 可先生成，Office/PDF 预览需后续安装或配置替代 Renderer |
| MinIO/Qdrant | 未发现 | 原生开发分别改用 LocalFileStorage 和 Elasticsearch |
| OCR | 未发现本地 PaddleOCR/Tesseract | 当前使用硅基流动视觉模型；本地 OCR 作为后续离线回退 |
| Docker/WSL/Sandbox | Docker 不可用；WSL、Hyper-V、Windows Sandbox 未启用 | 当前不能安全开放任意用户 Python；完整 V1 发布前必须补隔离运行时 |
| 内存 | 约 14 GB | 足够当前原生服务；Embedding/Vision 走 API，不在开发机加载大型模型 |
| CPU | 6 核 / 12 线程 | 足够进行本地功能验证，Worker 并发需限制 |
| GPU | 集成显卡 | 不把 GPU 作为 V1 本地运行前提 |
| 磁盘 | C 盘约 41.5 GB、E 盘约 20.2 GB 可用 | 原生文件和索引设置开发配额、生命周期和清理任务 |
| SiliconFlow 网络 | `.cn` API 域名可达，未认证请求得到预期 HTTP 响应 | 网络路径可用；Key 权限和模型实际输出待安全 Probe |

当前原生开发前置条件：

1. 使用 uv 的 Python 3.12.13 创建项目专用 venv；开始实施前不安装依赖。
2. 使用 NVM 的 Node 22.13.0，并通过 lockfile 固定前端依赖。
3. 保留现有 MySQL，实施时通过安全 Secret 配置验证账号并创建专用最小权限用户。
4. Redis/Elasticsearch 仅使用测试数据；真实数据前先完成网络绑定、认证和独立命名空间。
5. Agnes 与 SiliconFlow Key 只进入 Secret Store 或未提交的本地 Secret 文件。
6. 已在聊天中出现过的测试 Key 建议在正式联调前轮换成新的限额测试 Key。
7. 当前无需安装 Docker；但在开放普通用户任意 Python 和 stdio MCP 前必须补安全隔离运行时。

当前阶段没有使用任何模型 Key 或数据库密码进行认证调用，也没有把它们写入仓库、文档、Shell 历史或测试快照。已验证的是本地进程、端口、公开模型文档和无凭据网络连通性；Key 有效性与账号模型权限将在用户明确开始实施后，通过 Secret 注入的 Probe 验证。

---

# 4. V1 交付范围

## 4.1 必须完整实现

### 用户侧

- 管理员创建的本地账号登录。
- Chat 新建、历史会话、搜索和归档。
- 流式回答、停止、重试和断线恢复。
- 多文件上传、移除、预览和继续使用。
- 会话选择知识库、Plugin、DataSource 和临时 Connector。
- Knowledge Base 创建、文档索引、检索和引用。
- Plugin 浏览、运行、复制和 Workspace 分享。
- Artifact 预览、下载、Trace 和继续作为输入。
- Run 状态与业务化执行进度。
- 招投标和财务分析两个完整示例。

### 管理和高级能力

- Workspace、Admin/Member 和基础资源访问控制。
- Connector Builder。
- HTTP、MCP、Database、Builtin、Sandbox Provider。
- Secret 加密存储和引用。
- ToolSpec、参数编译、Schema/业务/权限/来源校验。
- Python Sandbox。
- Skill 创建、修改、测试、发布、归档和版本。
- Plugin 创建、修改、测试、发布、复制、分享、回滚和版本。
- Chat/Run → Skill/Plugin Draft。
- Error Classifier 和失败诊断。
- Run、Step、ToolCall、ModelCall、Event、Artifact Trace。
- 基础 Audit Log、模型用量和核心产品指标。
- DOCX、XLSX、PPTX、PDF、图片、图表、代码、数据集和 JSON Artifact。

## 4.2 V1 只预留，不建设产品功能

- Workflow Builder。
- Plugin 调 Plugin。
- Agent 调 Agent和 Multi-Agent。
- 复杂审批中心。
- SSO/SAML/OIDC/SCIM/LDAP。
- ABAC、DLP 和完整数据分类策略。
- Marketplace、Plugin Signing 和供应链平台。
- 定时、事件和批处理 UI。
- Browser/Desktop Agent。
- 多区域、HA 和灾备。

预留仅包括枚举、可空字段、接口类型和关联位置，不提前实现对应引擎或页面。

---

# 5. 总体架构

## 5.1 当前 native-dev 架构

```text
                                 Browser
                         ┌──────────┴──────────┐
                    Next.js :3000        FastAPI :8000
                         │              REST/Cookie/SSE
                         └──────────┬──────────┘
                                    │
                         FastAPI Control Plane
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
           MySQL 8                Redis             LocalFileStorage
        业务元数据/事件        Streams/Cache/PubSub      文件/Artifact
              │                     │                      │
              └─────────────────────┼──────────────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                    Agent Worker          Ingestion Worker
                         │                     │
                  Context Resolver       Parser/Chunker
                         │                     │
                   Model Gateway       Elasticsearch 8.14
                ┌────────┼────────┐       dense_vector/kNN
              Agnes   SiliconFlow│
              Chat    Vision/Embedding
                         │
                 Parameter Compiler
                         │
        Schema → Business → Source → Permission Validator
                         │
                    Tool Gateway
       ┌─────────────┬───────┬──────────┬──────────┐
       │             │       │          │          │
      HTTP          MCP   Database   Builtin   Trusted Analyzer
       │             │       │          │          │
       └─────────────┴───────┴──────────┴──────────┘
                         │
                 Result Normalizer
                         │
               Artifact / Citation / Event
                         │
                   Chat + Run Trace
```

`native-dev` 不开放任意模型生成 Python；图中的 Trusted Analyzer 只执行平台代码库内经过测试的确定性分析操作。Sandbox Tool 在 UI 和 Tool Registry 中保持禁用。

## 5.2 当前原生进程

| 服务 | 职责 | 是否对宿主暴露 |
|---|---|---|
| `web` | Next.js 用户界面 | `127.0.0.1:3000` |
| `api` | FastAPI、认证、REST、SSE、权限 | `127.0.0.1:8000` |
| `outbox-relay` | MySQL Outbox → Redis Streams | 否 |
| `worker-agent` | LLM Tool Calling Loop 和 Run 编排 | 否 |
| `worker-ingestion` | 文件解析、Chunk、SiliconFlow Embedding、Elasticsearch 写入 | 否 |
| `worker-render` | DOCX/XLSX/PPTX 生成；预览能力按环境启用 | 否 |
| `redis` | Stream、缓存、Session 和事件通知 | 已有 `127.0.0.1:6379` |
| `elasticsearch` | 全文、向量和 Metadata Filter | 已有 `9200`；当前不安全，仅测试数据 |
| `mysql` | 平台事实库和财务 Demo | 已有 `3306` |
| `local-storage` | 受控目录保存 File/Artifact | 只由 API/Worker 访问，不直接暴露目录 |

## 5.3 安全发布架构增量

完整 V1 发布前，在不改变领域接口的情况下替换/增加：

```text
LocalFileStorage → MinIO/S3（可选，单机也可继续受控文件存储）
Native Worker    → 容器/服务进程
Disabled Sandbox → 一次性隔离容器 Sandbox
Trusted stdio    → 隔离 MCP Runner
Dev CORS         → Caddy 同源网关
Test ES/Redis    → 独立、认证、仅本机/内网可访问的实例
```

## 5.4 模块化单体边界

```text
backend/app/
  identity/
  workspace/
  chat/
  files/
  knowledge/
  models/
  runtime/
  connectors/
  tools/
  skills/
  plugins/
  artifacts/
  audit/
  common/
```

模块通过应用服务和明确契约调用，不直接跨模块读写 ORM 对象。Storage、VectorStore、Queue、Sandbox、MCP Runner 和 Model Provider 都使用接口，确保 native-dev 与 secure-release 只替换基础设施 Adapter。

---

# 6. 技术栈

| 层级 | 选择 |
|---|---|
| Web | Next.js、React、TypeScript、App Router |
| UI | Tailwind CSS + Radix primitives + 自有组件/token |
| Web 数据 | TanStack Query；轻量 UI 状态使用 Zustand 或局部状态 |
| Web 测试 | Vitest、Testing Library、Playwright、axe-core |
| API | uv CPython 3.12、FastAPI、Pydantic v2 |
| ORM/迁移 | SQLAlchemy 2、Alembic、MySQL Driver |
| 异步任务 | MySQL Transactional Outbox + Redis Streams Consumer Group |
| 主数据库 | MySQL 8.0，`utf8mb4`，UTC `DATETIME(6)` |
| 向量检索 | Elasticsearch 8.14 `dense_vector` + kNN；VectorStore 接口保留 Qdrant Adapter |
| 文件存储 | `LocalFileStorage`（native-dev）；S3/MinIO Adapter 预留 |
| 文件解析 | PyMuPDF、python-docx、openpyxl、python-pptx、Pillow、CSV/文本解析器 |
| OCR/Vision | SiliconFlow `Qwen/Qwen3.5-4B`；本地 PaddleOCR 作为未来离线回退 |
| Embedding | SiliconFlow `BAAI/bge-m3`，固定 1024 维、最大 8192 Token |
| 文档输出 | python-docx、openpyxl/xlsxwriter、python-pptx、Matplotlib |
| 预览/转换 | PyMuPDF 负责 PDF；LibreOffice 安装后负责 Office → PDF |
| 密码 | Argon2id |
| Secret 加密 | AES-256-GCM；主密钥只在本地 Secret/环境文件中 |
| 日志/追踪 | 结构化 JSON Log、OpenTelemetry 接口预留 |
| 原生开发编排 | PowerShell 启停脚本 + PID/健康检查；不注册 Windows 系统服务 |
| 前后端访问 | `localhost:3000` + `localhost:8000`，开发期只允许精确 Origin；发布时切 Caddy 同源 |

具体依赖版本在开始实现时锁定到当时稳定版本并提交 lockfile；不使用浮动 `latest` 作为交付基线。

---

# 7. Model Gateway：Agnes 与 SiliconFlow 集成设计

## 7.1 已确认能力

官方文档确认：

- 模型标识：`agnes-2.5-flash`。
- Base URL：`https://apihub.agnes-ai.com/v1`。
- V1 主接口：`POST /v1/chat/completions`。
- Bearer API Key 认证。
- 支持 OpenAI 兼容 `messages`。
- 支持 `stream: true`。
- 支持 `tools` 和 `tool_choice`。
- 支持文本与 `image_url` 混合输入。
- 图像 URL 必须公网可访问。
- 官方标注上下文窗口 512K、最大输出 65.5K；实际限额取决于账号权限。

官方页面没有承诺：

- `response_format/json_schema/strict` Structured Outputs。
- Base64/Data URL 图片。
- 并行 Tool Call 的具体行为。
- 流式 Tool Call 的完整事件格式。
- 速率、并发、错误码和重试规则。

因此 V1 不能把这些未确认能力写死为前提。

## 7.2 Model Gateway 配置

```yaml
provider: agnes
protocol: openai_chat_completions
base_url: https://apihub.agnes-ai.com/v1
model: agnes-2.5-flash
secret_ref: secret://workspace/model-agnes-test
capabilities:
  chat: true
  streaming: probe
  tools: probe
  vision: true
  vision_transport: public_image_url
  structured_output: unknown
  parallel_tools: unknown
limits:
  context_window: documented_512k
  max_output: documented_65_5k
```

`secret_ref` 只是示意，真实 Key 不出现在配置文件和数据库 Spec 明文中。

## 7.3 V1 使用策略

1. 统一使用 Chat Completions Adapter，Responses 和 Anthropic Messages Adapter 只预留。
2. 普通聊天温度默认 `0.4`。
3. Parameter Compiler、Builder 和错误分类默认 `0.1`。
4. 复杂规划可按 Profile 启用 Thinking，但必须先做兼容性测试。
5. 默认上下文预算不超过约 32K Token；不因官方支持大窗口就直接塞入全部文档。
6. Tool Arguments 必须经过 JSON Parse 和平台 Validator，绝不信任模型输出。
7. 结构化输出优先利用函数 Tool Schema；失败最多修复两次，仍失败则终止并报告。
8. ModelCall 记录模型、Profile、Token、延迟、Provider Request ID 和脱敏错误。

## 7.4 实施第一关：模型能力 Probe

在业务开发前先建立独立、可重复运行的 Provider Probe：

1. 基础中文问答。
2. 多轮上下文。
3. SSE 文本流格式和结束标志。
4. 单 Tool Call。
5. Tool Result 回传后的第二轮回答。
6. Tool Arguments 的 JSON 合法性。
7. 多 Tool/并行行为探测。
8. Thinking 与 Tool Calling 是否兼容。
9. Agnes 公网测试图片识别，仅作为其 Provider 能力记录。
10. SiliconFlow `Qwen/Qwen3.5-4B` 的 URL 和 Base64 图片识别。
11. SiliconFlow Vision + Tool 是否能同请求稳定使用。
12. SiliconFlow `BAAI/bge-m3` 的单条、批量、空输入和超长输入。
13. 实测 Embedding 维数必须为 1024，并做同义/无关中文检索小基准。
14. 两个 Provider 的 429、401、超时、断流和非法响应处理。

Probe 结果写入 Model Profile Capability，不由开发人员凭经验假定。

## 7.5 SiliconFlow Provider

官方文档确认：

- Base URL：`https://api.siliconflow.cn/v1`，使用 `.cn` 域名。
- `Qwen/Qwen3.5-4B` 是当前正常服务的 Chat/VLM，官方标记 `vlm`、Function Calling 和 JSON Object Mode。
- Chat/Vision 使用 `POST /v1/chat/completions`。
- 支持 `enable_thinking`、`tools`、URL/Base64 图片输入。
- 支持 `response_format: {"type":"json_object"}`；该模型的严格 `json_schema` 仍需实测，不能直接依赖。
- `BAAI/bge-m3` 使用 `POST /v1/embeddings`，最大输入 8192 Token。
- `BAAI/bge-m3` 不是可变维数模型，按上游规格和实际响应固定为 1024 维。

```yaml
provider: siliconflow
base_url: https://api.siliconflow.cn/v1
secret_ref: secret://workspace/model-siliconflow-test
profiles:
  vision/default:
    endpoint: /chat/completions
    model: Qwen/Qwen3.5-4B
    supports_url_image: true
    supports_base64_image: true
    supports_tools: probe
    supports_json_object: true
    supports_strict_json_schema: unknown
  embedding/default:
    endpoint: /embeddings
    model: BAAI/bge-m3
    dimensions: 1024
    max_input_tokens: 8192
```

同一个 SiliconFlow Secret 可以被两个 Profile 引用，但 Secret 值仍只在 Model Gateway 调用时解析。

外部处理策略按用途分别保存：

```text
allow_external_chat
allow_external_vision
allow_external_embedding
```

当前虚构 Demo 可全部开启。真实企业资料只有在 Workspace 管理员确认相应外发策略后才发送；关闭 `allow_external_embedding` 时知识摄取应进入“等待本地 Embedding Profile”状态，而不是偷偷改用其它云模型或建立空索引。

## 7.6 Vision 与本地隐私

主 Chat 继续使用 Agnes；图片理解改由独立 SiliconFlow Vision Profile 完成。独立 Profile 使图片传输、大小限制、外发策略和费用可以单独管理。

路由规则：

```text
用户粘贴公开图片 URL
  → SiliconFlow Qwen Vision URL Input

用户上传本地图片/扫描件
  ├── 允许外发且通过格式/大小检查 → SiliconFlow Base64 Vision
  ├── Workspace 禁止外发 → 本地 OCR（安装后）
  └── 没有可用处理器 → 明确提示无法识别，不静默忽略图片
```

Base64 解决“云模型无法访问 localhost 文件 URL”的技术问题，但不改变数据会离开本机这一事实。Workspace 必须保存 `allow_external_model_processing` 策略，Chat 上传区显示外发提示；分类为禁止外发的图片绝不发送给 SiliconFlow。

## 7.7 Embedding 与 Rerank

Embedding 使用用户指定的 SiliconFlow `BAAI/bge-m3`：

```text
embedding/default → SiliconFlow BAAI/bge-m3, 1024 dimensions
rerank/default    → V1 初始关闭
rerank/quality    → 可选 BAAI/bge-reranker-v2-m3
```

默认 Chunk 目标约 800–1000 Token、Overlap 100–150 Token；虽然模型支持 8192 Token，仍不使用超长 Chunk 牺牲定位和检索精度。Embedding Profile、维数或归一化策略变化后必须创建新索引并重建知识库，不能在同一 Elasticsearch `dense_vector` 字段中混用。

SiliconFlow 普通 `/embeddings` 响应只按 Dense Vector 使用；不承诺暴露 BGE-M3 上游的 Sparse/ColBERT 输出。初始检索采用 Elasticsearch BM25 + Dense kNN 的应用层融合，需要时再调用 Reranker。

---

# 8. 前端与交互设计

## 8.1 设计原则

界面借鉴 ChatGPT Web 的熟悉交互：

- 可折叠左侧栏。
- 新建对话和最近会话。
- 居中的消息流。
- 底部悬浮多行输入框。
- “+”上下文菜单。
- 流式输出、停止、重新运行。
- 移动端侧栏抽屉。

不复制：

- OpenAI/ChatGPT 名称、Logo、图标和品牌文案。
- 专有字体、色板和逐像素布局。
- 无关的营销动画。

产品临时设计主题为“可信工作记录”：主体安静、内容优先，使用一条克制的“证据轨道”串联输入来源、Run Step 和 Artifact 血缘。

建议 Token：

```text
canvas       #F7F7F8
surface      #FFFFFF
text         #202123
muted        #6B6F76
border       #E5E7EB
brand        #5856D6
evidence     #0F8A72
danger       #C53B3B
```

字体：

- 中文正文：Noto Sans SC/思源黑体，本地打包。
- 西文与 UI：Inter。
- Trace/JSON/Run ID：IBM Plex Mono。

## 8.2 桌面布局

```text
┌──────────────────┬─────────────────────────────────┬──────────────────┐
│ 品牌 / 新建对话   │ 会话标题 · 当前上下文 · 详情      │ Run/来源/成果检查器 │
│ 搜索              ├─────────────────────────────────┤ 默认收起           │
│ 对话/知识库/插件   │                                 │                  │
│ 文件/数据源        │       消息与结构化结果流           │                  │
│                  │                                 │                  │
│ 最近对话          │                                 │                  │
│ Workspace / 用户  │   Context Chips + 固定输入框      │                  │
└──────────────────┴─────────────────────────────────┴──────────────────┘
```

- 左栏 248–280 px，可折叠。
- 主消息列最大 800–900 px。
- 右侧检查器 360–420 px，默认关闭。
- 主消息、侧栏和检查器独立滚动。

## 8.3 普通成员导航

- 新建对话。
- 搜索对话。
- 对话。
- 知识库。
- 插件。
- 文件。
- 数据源。
- 最近对话。
- Workspace/用户菜单。

“文件”页包含：

- 本次输入。
- 输出成果。

管理员从用户菜单进入管理控制台，普通成员主导航不展示 MCP、Tool、Schema、Runtime 等词汇。

## 8.4 主要路由

| 路由 | 页面 |
|---|---|
| `/login` | 用户名密码登录 |
| `/first-login/password` | 首次登录强制改密 |
| `/chat/new` | 新对话 |
| `/chat/:conversationId` | Chat |
| `/knowledge`、`/knowledge/:id` | 知识库 |
| `/plugins`、`/plugins/:id` | Plugin |
| `/files?tab=inputs` | 临时文件 |
| `/files?tab=artifacts` | Artifact |
| `/data-sources` | 数据源 |
| `/runs/:runId` | Run Trace 深链接 |
| `/settings/profile` | 个人设置 |
| `/admin/members` | 成员管理 |
| `/admin/capabilities` | Skill/Connector/Plugin 管理 |
| `/admin/models` | Model Profile 与能力测试 |
| `/admin/secrets` | Secret 元数据，不显示值 |
| `/admin/audit` | Audit Log |

## 8.5 Chat Composer

支持：

- Enter 发送、Shift+Enter 换行。
- 中文输入法组合期间不误发送。
- 拖放、粘贴和选择多文件。
- 每个文件独立进度、失败和重试。
- Context Chip 显示知识库、Plugin、DataSource、File、Artifact。
- 流式中发送键变为停止。
- 用户离开底部后暂停自动滚动并显示“跳到最新消息”。

“+”菜单使用用户语言：

- 上传文件。
- 选择知识库。
- 使用插件。
- 连接数据源。

管理员/高级用户额外看到：

- 添加企业 API/程序。
- 添加高级连接（MCP）。

## 8.6 Message Part 呈现

| Part | 呈现 |
|---|---|
| Text | 平铺 Markdown、表格、代码 |
| Status | 业务化状态，技术细节折叠 |
| ToolCall/ToolResult | 默认放在执行详情，主消息只显示摘要 |
| Citation | 行内来源编号和来源抽屉 |
| File | 文件名、类型、大小、处理状态 |
| Artifact | 预览、下载、继续使用、Trace |
| Error | 错误归属、影响、可执行下一步 |
| InputRequest | 缺失资料/参数的上传或继续选择 |
| Approval | 只预留类型，不建设复杂审批中心 |

## 8.7 响应式和可访问性

- 大屏可同时显示左栏、主消息和右检查器。
- 平板检查器改为覆盖抽屉。
- 手机为单栏，资源选择和过滤使用底部 Sheet。
- 320 px 宽度和 200% 缩放不能出现页面级横向滚动。
- 触控目标至少 44×44 CSS px。
- 目标 WCAG 2.2 AA。
- 流式 Token 不逐个写入 `aria-live`，只播报阶段和完成状态。
- 完整键盘操作、可见焦点、Reduced Motion。
- 图表必须同时提供文字总结和数据表。

---

# 9. 本地账号、Workspace 和权限

## 9.1 首个管理员

部署后运行交互命令：

```text
create-admin
  → 输入登录名
  → 输入显示名
  → 安全读取密码
  → 创建默认 Organization 和 Workspace
```

命令不打印密码、不写 Shell 历史、不提供 `admin/admin` 默认值。

## 9.2 管理员创建成员

管理员输入：

- 登录名。
- 显示名。
- 可选企业邮箱。
- Admin/Member。
- 可使用的 Workspace 资源。

系统生成一次性临时密码，只在成功弹窗显示一次，默认 24 小时有效。成员首次登录必须修改密码；关闭弹窗后管理员只能重置，不能重新查看。

密码规则：

- 12–128 字符。
- 允许密码管理器和粘贴。
- Argon2id 存储。
- 不在日志、Audit、Trace、DOM 快照中出现。

登录安全：

- 错误统一显示“账号或密码不正确”。
- 连续失败递增冷却，默认 5 次后 15 分钟。
- Admin 重置密码可同时注销全部会话。
- 停用用户立即撤销会话。
- 不能停用或降级最后一个活跃 Admin。

## 9.3 Session

- HttpOnly Cookie。
- SameSite=Lax。
- 生产/HTTPS 使用 Secure 和 `__Host-` 前缀。
- 本地 HTTP 使用开发 Cookie 名，不降低生产配置。
- 登录和改密后轮换 Session ID。
- Session 数据保存在 Redis，MySQL 保留必要审计元数据。
- 修改请求校验 Origin/CSRF Token。

## 9.4 V1 权限模型

对象包含：

```text
workspace_id
owner_user_id
visibility = private | workspace
```

权限规则：

| 行为 | Admin | Member |
|---|---:|---:|
| 创建成员/重置密码 | 是 | 否 |
| 管理 Workspace Secret | 是 | 否 |
| 创建 Connector/DataSource | 是 | 否，除非后续授权 |
| 创建个人 Knowledge/Skill/Plugin | 是 | 是 |
| 发布到 Workspace | 是 | 仅可提交 Draft，默认由 Admin 发布 |
| 使用 Workspace 可见资源 | 是 | 有使用权限时是 |
| 查看他人 private 对象 | 是 | 否 |
| 查看 Audit | 是 | 否 |

V1 预留 `resource_grants`，但不提供复杂逐字段 ACL 编辑器。

---

# 10. 数据模型设计

## 10.1 数据约定

- ID 使用可排序 ULID，MySQL `CHAR(26)` ASCII Binary Collation。
- 时间统一 UTC `DATETIME(6)`，前端按本地时区显示。
- 状态使用 `VARCHAR` + 应用层枚举，不使用难迁移的 MySQL ENUM。
- Spec 和 Snapshot 使用 MySQL JSON。
- Published Version 永久不可修改。
- 删除业务对象默认软删除/归档。
- 所有 Workspace 业务对象必须带 `workspace_id`。
- 所有列表使用游标分页。
- 重要 Draft 使用 `lock_version`/ETag 做乐观并发控制。

MySQL 没有 PostgreSQL RLS，Workspace 隔离采用三层约束：

1. 所有 Workspace 资源表的 `workspace_id` 非空。
2. 关键父子关系使用 `(workspace_id, id)` 唯一键和复合外键，阻止跨 Workspace 绑定。
3. Repository 从认证上下文注入 Workspace Scope，不接受客户端自行省略或替换 Scope。

每种资源的 GET/UPDATE/DELETE、Plugin Binding、Run/Conversation、Artifact Lineage 都必须有跨 Workspace IDOR 自动测试；Elasticsearch kNN/全文检索的 Workspace/Knowledge Base Filter 同样由服务端强制注入。

## 10.2 表分组

### 身份与权限

```text
organizations
workspaces
users
user_identities
workspace_members
user_sessions
resource_grants
```

### Chat

```text
conversations
conversation_bindings
messages
message_parts
```

### 文件与知识

```text
files
file_processing_jobs
knowledge_bases
knowledge_documents
knowledge_document_versions
knowledge_chunks
knowledge_ingestion_jobs
citations
```

向量和可搜索副本存入 Elasticsearch；MySQL `knowledge_chunks` 保存文本、位置、Hash、Embedding Profile、维数、Index 名称和 Elasticsearch Document ID，作为审计事实源。

### 模型和 Secret

```text
model_providers
model_profiles
model_probe_results
secrets
```

### Skill/Connector/Tool/Plugin

```text
skills
skill_versions

connectors
connector_versions
tools
tool_versions
connector_tool_bindings

data_sources

plugins
plugin_versions
plugin_version_skill_bindings
plugin_version_tool_bindings
plugin_version_resource_bindings

test_cases
test_runs
```

### Runtime

```text
runs
run_resource_snapshots
run_steps
run_events
tool_calls
model_calls
```

### Artifact、Secret 与审计

```text
artifacts
artifact_lineage
audit_logs
outbox_events
```

## 10.3 Root + Version 模式

```text
skills
  id
  workspace_id
  name
  owner_user_id
  current_published_version_id

skill_versions
  id
  skill_id
  version_number
  based_on_version_id
  status: DRAFT | PUBLISHED | ARCHIVED
  spec_json
  created_by
  published_at
```

Connector 和 Plugin 使用同一模式。

规则：

1. 修改 Published 时复制出新 Draft。
2. 发布时事务性更新根对象的当前版本指针。
3. 回滚重新激活历史不可变版本，或从历史版本创建新版本。
4. Run 绑定 `plugin_version_id`、`skill_version_ids` 和 `tool_version_ids`。
5. Plugin Binding 必须挂到 `plugin_version_id`，不能挂到 Plugin 根对象。

## 10.4 Connector 与 Tool

```text
Connector = 连接配置和 Provider Adapter
Tool      = Connector 暴露的单个可调用操作
```

一个 MCP Connector 或 OpenAPI 服务可以生成多个 Tool Version。Database 的通用 Tool 与具体 DataSource 也必须分离。

## 10.5 Run 可复现快照

每次 Run 保存：

- Conversation ID。
- 用户和 Workspace。
- Plugin/Skill/Tool 精确 Version。
- Model Profile 和 Provider Adapter Version。
- File/Artifact Hash。
- Knowledge Document/Chunk 引用。
- DataSource ID，不保存 Secret。
- Resource Binding Snapshot。
- Runtime Schema Version。
- Field Source Policy Snapshot。

即使以后发布新 Plugin 或重新索引知识库，也能解释历史 Run 使用了什么。

---

# 11. REST API 设计

## 11.1 约定

- Base Path：`/api/v1`。
- Collection 使用复数名词。
- JSON 字段使用 `snake_case`。
- 异步操作返回 `202 Accepted` 和资源/Run ID。
- 创建 Run 支持 `Idempotency-Key`。
- Draft 更新使用 `ETag`/`If-Match`。
- 列表使用 `cursor` 和 `limit`。
- 错误使用 `application/problem+json`。
- OpenAPI 是前后端契约源，生成 TypeScript Client。

错误示例：

```json
{
  "type": "https://local.company-agent/errors/validation",
  "title": "参数校验失败",
  "status": 422,
  "code": "TOOL_ARGUMENT_VALIDATION_FAILED",
  "detail": "start_date 必须使用 YYYY-MM-DD",
  "request_id": "req_xxx",
  "errors": [
    {
      "field": "start_date",
      "message": "格式不正确"
    }
  ]
}
```

## 11.2 主要端点

### Auth/User

```text
POST /auth/login
POST /auth/logout
POST /auth/change-password
GET  /me

GET  /admin/users
POST /admin/users
PATCH /admin/users/{id}
POST /admin/users/{id}/reset-password
POST /admin/users/{id}/revoke-sessions
```

### Conversation/Run

```text
GET  /conversations
POST /conversations
GET  /conversations/{id}
PATCH /conversations/{id}
DELETE /conversations/{id}
POST /conversations/{id}/runs

GET  /runs/{id}
GET  /runs/{id}/steps
GET  /runs/{id}/events                 # SSE
POST /runs/{id}/cancel
POST /runs/{id}/retry
POST /runs/{id}/continue               # 基于已完成 Run 创建续接 Run
```

### File/Artifact

```text
POST /files/upload-sessions
POST /files/{id}/complete
GET  /files
GET  /files/{id}
DELETE /files/{id}

GET  /artifacts
GET  /artifacts/{id}
GET  /artifacts/{id}/preview
GET  /artifacts/{id}/download
POST /artifacts/{id}/use-as-input
```

### Knowledge

```text
GET  /knowledge-bases
POST /knowledge-bases
GET  /knowledge-bases/{id}
PATCH /knowledge-bases/{id}
DELETE /knowledge-bases/{id}
POST /knowledge-bases/{id}/documents
DELETE /knowledge-bases/{id}/documents/{document_id}
POST /knowledge-bases/{id}/reindex
POST /knowledge-bases/{id}/search
```

### Capability

```text
/skills
/skills/{id}/versions
/skill-versions/{id}/test-runs
/skill-versions/{id}/publish

/connectors
/connectors/{id}/versions
/connector-versions/{id}/test-connection
/connector-versions/{id}/test-invocation
/connector-versions/{id}/publish

/data-sources
/data-sources/{id}/test-connection

/plugins
/plugins/{id}/versions
/plugin-versions/{id}/test-runs
/plugin-versions/{id}/publish
/plugins/{id}/clone
/plugins/{id}/share
/plugins/{id}/runs

POST /runs/{id}/capability-proposals
```

### Admin

```text
/admin/model-profiles
/admin/model-profiles/{id}/probe
/admin/secrets
/admin/audit-logs
```

Secret API 永远只返回 ID、名称、类型和状态，不返回原值。

---

# 12. Chat、Run 和事件协议

## 12.1 Run 状态

V1 实际实现：

```text
CREATED → QUEUED → RUNNING → COMPLETED
                       ├──→ FAILED
                       ├──→ CANCELLED
```

预留：

```text
WAITING_INPUT
WAITING_APPROVAL
PAUSED
```

V1 不建设通用的 Run 暂停/恢复引擎。招投标 Gap Detection 或参数缺失时，当前 Run 生成结构化 `InputRequestPart`/Gap Report 后正常完成；用户点击“上传资料”或“继续并保留占位符”后，创建带 `parent_run_id` 的 continuation Run。这样既完成用户交互，又不提前实现复杂 Human-in-the-loop Workflow。

## 12.2 事件信封

```json
{
  "id": "evt_xxx",
  "schema_version": 1,
  "sequence": 37,
  "event": "tool.completed",
  "run_id": "run_xxx",
  "step_id": "step_xxx",
  "timestamp": "2026-08-20T10:00:00.000Z",
  "payload": {}
}
```

事件至少包括：

```text
run.created
run.queued
run.started
run.continuation_created
run.completed
run.failed
run.cancelled
step.started
step.completed
step.failed
tool.started
tool.completed
tool.failed
artifact.created
message.delta
message.completed
```

规则：

- `run_events` 持久化后再发布通知。
- 每个 Run 的 `sequence` 严格递增。
- SSE 支持 `Last-Event-ID`。
- Redis 只负责唤醒，不是事件唯一存储。
- 页面刷新或断线后按 Run ID 重放。
- 前端按事件 ID 去重。

## 12.3 Run 创建和 Worker 可靠性

创建 Run 时，在同一个 MySQL 事务中写入：

```text
User Message
Run(QUEUED)
run.created Event
Outbox Event
```

事务提交后由 Outbox Relay 使用 Redis `XADD` 投递到 Stream。Worker Consumer Group 领取任务，并使用 MySQL compare-and-set 写入短租约与心跳；过期租约可由其它 Worker 回收。MySQL 是状态真相，Redis 丢失或重启不能使已创建的 Run 消失。

执行语义为 at-least-once，因此：

- 每个 Run、Step、ToolCall、Artifact Create 都有幂等键。
- Worker 不在外部模型/HTTP/数据库调用期间持有 MySQL 长事务。
- 只读或明确幂等 Tool 才自动重试。
- 支持幂等键的外部接口重试时复用同一键。
- 非幂等外部调用超时且结果未知时，标记 `EXTERNAL_OUTCOME_UNKNOWN`，不得自动重复调用。
- Renderer 和 Artifact Import 按 `tool_call_id` 去重。
- 状态更新、Run Event 和 Outbox 写入保持同一事务。

## 12.4 Agent Runtime

```text
Resolve Context
  → LLM Call
  → Text Reply ? 完成
  → Tool Call
  → Parameter Compiler
  → Validation Pipeline
  → Tool Gateway
  → Normalized Result
  → LLM Call
  → 直到完成或达到限制
```

默认限制：

- 一个 Run 最多 12 个 Agent Loop。
- 一个 Run 最长 20 分钟。
- 单 Model Call 默认 180 秒。
- 单 Tool Call 默认 120 秒，可由 ToolSpec 限制到更低。
- 单次数据库查询默认 30 秒、1000 行和 10 MB。
- 单 Run 最多同时运行一个 Sandbox；系统默认并发两个 Sandbox。
- 达到限制时产生明确的 Runtime Error，不无限循环。

## 12.5 Context Resolver

统一组装：

```text
平台安全规则
Workspace Policy
Published Skill Rules
Plugin/Tool Schema
User Permission
当前消息
Conversation Summary
User Files/Artifact
Knowledge Retrieval
Resource Binding
Field Source Policy
Token Budget
```

各业务模块不得自行拼接系统 Prompt。文件、知识和 Tool Result 都视为不可信内容，不得覆盖权限和系统规则。

---

# 13. File、Knowledge 和 Citation

## 13.1 File 生命周期

```text
UPLOADING
  → UPLOADED
  → SCANNING
  → PROCESSING
  → READY
  └→ FAILED
```

默认限制：

- 单文件 100 MB。
- 单次消息 20 个文件。
- Workspace 默认配额 10 GB，可配置。
- MIME 嗅探与扩展名同时校验。
- Office 宏不执行。
- ZIP bomb、路径穿越和超大解压结果拒绝。

临时 File 不自动进入 Knowledge。用户必须在知识库页面显式上传或选择“加入知识库”。

## 13.2 格式能力

| 格式 | 解析 | 预览 | 模板 | 输出 |
|---|---:|---:|---:|---:|
| PDF | 文本 + 扫描页 OCR | 是 | 否 | 是 |
| DOCX | 文本/表格/样式摘要 | PDF 预览 | 是 | 是 |
| XLSX | Sheet/表格/公式值 | 分页表格 | 可选 | 是 |
| CSV | 表格 | 分页表格 | 否 | 是 |
| TXT/Markdown | 文本 | 是 | 否 | 是 |
| PPTX | 文本/表格/备注基础解析 | PDF/页面图 | 是 | 是 |
| 图片 | OCR；可用时 Vision | 是 | 否 | 是 |

## 13.3 Knowledge 摄取

```text
File
  → Parser/OCR
  → Cleaner
  → Heading/Table-aware Chunker
  → Metadata
  → SiliconFlow BGE-M3 Embedding
  → Elasticsearch Bulk Index
  → Knowledge Document READY
```

Chunk 保存：

- Workspace、Knowledge Base。
- File/Document Version。
- Content Hash。
- 页码、Sheet、Slide、标题路径和字符位置。
- Parser/Chunker/Embedding Profile Version。
- Elasticsearch Index/Document ID。

默认检索：

- Dense Search Top 20。
- Metadata Filter 强制 Workspace/KB。
- 可选 Rerank 到 Top 8。
- Context Packer 去重并保留来源。

## 13.4 Citation

引用至少记录：

```text
source_file_id
knowledge_document_version_id
chunk_id
page / sheet / slide
location
quoted_excerpt_hash
```

Chat 点击引用打开来源抽屉，显示文件、页码/位置和相关片段。Run 保存本次命中的 Chunk，避免只有最终答案而无法审计证据。

---

# 14. Parameter Compiler 和验证

Parameter Compiler 输出不是裸 JSON，而是参数提案：

```json
{
  "arguments": {
    "project_id": "P001823",
    "start_date": "2026-01-01",
    "end_date": "2026-06-30",
    "template_id": "OP-02"
  },
  "field_provenance": {
    "project_id": [
      {
        "source_type": "tool",
        "source_id": "search_project",
        "location": "items[0].id"
      }
    ]
  },
  "unresolved_fields": [],
  "warnings": [],
  "confidence": 0.94,
  "requires_confirmation": false
}
```

调用前固定流水线：

```text
JSON Parse
  → JSON Schema Draft 2020-12 Validation
  → Business Rule Validation
  → Field Source Policy
  → Resource Binding
  → User/Workspace Permission
  → Risk/Confirmation Policy
  → Tool Gateway
```

V1 Validator：

- Required。
- Type。
- Enum。
- Min/Max。
- String/Array Length。
- Format。
- 自定义业务 Validator。
- 字段来源和引用要求。

Field Source Policy 最小结构：

```text
field
allowed_source_types
allow_llm_generate
require_citation
require_confirmation
fallback_policy
```

无法确定的字段按策略查询 Tool、检索 Resource或使用显式默认值；仍无法确定时生成结构化 Input Request，并由用户下一条消息创建 continuation Run。禁止静默猜测企业事实。

---

# 15. Tool Gateway 与 Provider

## 15.1 ToolSpec

```json
{
  "id": "tool_generate_ppt",
  "version": 1,
  "name": "generate_ppt",
  "description": "根据 PresentationSpec 生成 PPTX",
  "provider": "http",
  "input_schema": {},
  "output_schema": {},
  "permissions": [],
  "risk_level": "low",
  "requires_approval": false,
  "side_effect_class": "read",
  "idempotency": "safe",
  "timeout_seconds": 120,
  "retry_policy": {},
  "redaction_paths": [],
  "result_limits": {}
}
```

Gateway 负责：

- Tool Lookup 和版本固定。
- Workspace/用户权限。
- Secret 解析。
- 参数/业务/来源校验。
- Timeout、Cancellation 和 Retry。
- 日志脱敏。
- Result Normalization。
- ToolCall 持久化和 Audit。

## 15.2 HTTP Provider

支持：

- GET/POST/PUT/PATCH/DELETE 定义；V1 可注册写操作，但风险级别高且默认不可自动调用。
- Path、Query、Header、JSON Body 映射。
- None、API Key、Bearer、Basic、OAuth2 Client Credentials。
- 响应 Schema、字段映射和 Artifact URL 提取。
- 连接测试和调用测试。

安全：

- 默认拒绝 loopback、云 Metadata 和未允许的私网地址。
- 本地 Renderer/企业内网通过 Admin Allowlist 明确放行。
- DNS 解析和重定向后再次检查目标。
- 默认不跨域重定向。
- TLS 校验默认不可关闭；开发例外必须显式标红。
- 限制响应大小和超时。
- 只对幂等/显式声明可重试操作自动重试。

## 15.3 MCP Provider

支持：

- 当前标准 stdio。
- 当前标准 Streamable HTTP。
- 旧 HTTP+SSE 兼容适配，UI 标记 Deprecated。
- initialize、tools/list、tool call、cancel 和基础 Server Version。
- Tool Enable/Disable。
- Input/Output Schema 映射。
- Secret 引用。

stdio 安全：

- native-dev 默认关闭普通用户 stdio；Gate 0/开发者测试只允许明确指定的可信可执行文件。
- 只由 Admin 配置。
- 使用参数数组直接 exec，不经过 Shell 字符串拼接。
- secure-release 必须在 `mcp-runner` 隔离容器中启动，不在宿主机直接运行。
- 固定工作目录、资源限制和环境变量 Allowlist。
- V1 不允许运行时从未知网络动态安装任意包。

Streamable HTTP 安全：

- Origin、认证和协议版本处理。
- SSRF 规则与 HTTP Provider 一致。
- Session ID、断线和取消单独管理。

## 15.4 Database Provider

统一 Tool：

```text
database.describe
database.list_tables
database.describe_table
database.query
```

支持 MySQL 和 PostgreSQL；Demo 使用 `demo_finance` MySQL 数据库。

四层只读防护：

1. 独立只读数据库账号。
2. 只读事务/会话。
3. SQL Parser 验证单条只读查询。
4. Timeout、Row、Byte 和 Table Allowlist。

拒绝：

- 多语句。
- INSERT/UPDATE/DELETE/DDL。
- 写入 CTE。
- `SELECT ... FOR UPDATE`。
- 导出文件和已知有副作用函数。
- 未授权 Schema/Table。

连接串和密码不得进入 LLM、DOM、PluginSpec 或 Trace。

## 15.5 Result Normalizer

```json
{
  "status": "success",
  "data": {},
  "artifacts": [
    {
      "type": "presentation",
      "name": "经营报告.pptx",
      "storage_ref": "artifact_xxx"
    }
  ],
  "metadata": {
    "provider_request_id": "external_xxx"
  }
}
```

外部 URL 优先转存到当前 Storage Adapter（native-dev 为受控本地目录）；无法转存时由平台授权代理访问，不把永久公共 URL 直接暴露给用户。

## 15.6 长任务

Provider 可以返回：

```json
{
  "status": "running",
  "job_id": "external_job_xxx",
  "poll_after_seconds": 5
}
```

Runtime 保存 Job ID，使用配置的 poll/cancel Tool 继续执行，不把 HTTP 请求生命周期当作任务生命周期。

---

# 16. Python Sandbox

本节是完整 V1/secure-release 标准，不在当前 native-dev 启动。native-dev 只运行平台内置 Trusted Analyzer，`python_execute` Tool 对普通用户不可见且后端强制拒绝；不能用普通 Windows 子进程冒充 Sandbox。

每次执行创建一次性容器：

```text
Image: 固定签名/版本的 Python Runtime
User: non-root
Network: none（默认）
Root FS: read-only
Input: /workspace/input，只读
Output: /workspace/output，只写当前 Run
Temp: 独立 tmpfs
CPU: 默认 1 core
Memory: 默认 1 GB
PIDs: 默认 64
Timeout: 默认 120 秒
Capabilities: drop ALL
Security: no-new-privileges
```

预装：

- pandas。
- numpy。
- matplotlib。
- openpyxl。
- xlsxwriter。
- python-docx。
- pyarrow。
- pydantic。

V1 不允许运行时任意 `pip install`。新增包通过受控镜像版本发布。

执行过程：

```text
授权输入复制/只读挂载
  → 创建容器
  → 执行受控入口
  → 限制 stdout/stderr 大小
  → 扫描 output
  → 允许的文件转为 Artifact
  → 销毁容器和临时卷
```

Sandbox Controller 是 secure-release 阶段的发布闸门，需要隔离运行时权限。当前 native-dev 不运行这一 Controller，也不开放任意代码执行。后续不能把 Docker Socket 暴露给 Web/API/Agent 容器；本地容器方案适合受信用户单机部署，不等同于公开敌对多租户隔离，生产部署需独立执行节点以及更强的 gVisor/Kata 等边界。

Programmatic Tool Calling 只预留 SDK 接口，V1 默认关闭 Sandbox 内对企业 Tool 的任意调用。

---

# 17. Skill、Plugin 和 Capability Builder

## 17.1 Skill

Skill 保存“怎么做”：

- 目标。
- Instructions。
- Rules。
- 输入/输出描述。
- Examples。
- 推荐 Tool。
- 必需 Resource。
- Test Cases。

自然语言修改流程：

```text
读取当前 Published Version
  → 生成结构化 Proposal 和 Diff
  → 用户确认
  → 新 Draft Version
  → Test Run
  → Publish
```

不直接覆盖历史版本。

## 17.2 Plugin

Plugin Version 包含：

- 一个或多个 Skill Version。
- Tool Version Binding。
- Resource Binding。
- Input/Output Schema。
- Permission/Visibility。
- Model Profile 建议，不直接绑定厂商 API Key。
- Test Suite。

功能：

- 创建、修改、归档。
- Draft/Published/Archived。
- Test Run。
- 发布和回滚。
- Clone。
- Share to Workspace。
- Chat 使用。
- Artifact 输出。

Clone 不复制 Secret 明文，并重新检查创建者对所有依赖的权限。

## 17.3 Chat/Run → Capability

输入：

```text
User Intent
Conversation Summary
Resolved Resources
Tool Calls and Versions
Field Provenance
Errors and Corrections
Artifacts
Final User Feedback
```

输出只能是 Draft Proposal：

```text
只保存方法 → Skill Draft
接入外部系统 → Connector Draft
方法 + Tool/Resource/Output → Plugin Draft
```

用户查看提取出的目标、规则、依赖、输入输出和不可编造约束；Test Run 通过后才可发布。

## 17.4 Error Classifier

统一错误类别：

```text
SKILL_ERROR
PARAMETER_ERROR
VALIDATION_ERROR
PERMISSION_ERROR
DATA_ERROR
CONNECTOR_ADAPTER_ERROR
EXTERNAL_TOOL_ERROR
SANDBOX_ERROR
MODEL_ERROR
PLATFORM_ERROR
```

外部企业程序错误只报告上下文和建议，不出现“自动修改外部程序”操作。平台托管的程序只能通过 Patch → Test → New Version → Publish 修复。

---

# 18. Artifact 与 Renderer

## 18.1 Artifact 类型

```text
document
spreadsheet
presentation
pdf
image
chart
code
dataset
json
```

Artifact 必须：

- 绑定 Run。
- 绑定 Owner/Workspace。
- 记录 MIME、Hash、大小和 Storage Key。
- 记录输入、ToolCall 和父 Artifact lineage。
- 通过权限校验后预览/下载。
- 能成为下一次 Run 的 Resource。

## 18.2 结构化 Spec

```text
LLM → DocumentSpec → Document Renderer → DOCX/PDF
LLM → PresentationSpec → Presentation Renderer → PPTX/PDF Preview
LLM → SpreadsheetSpec/DataFrame → Spreadsheet Renderer → XLSX
```

LLM 不直接控制 Word/PPT 底层格式。

## 18.3 本地 Renderer

- DOCX：python-docx + 用户模板样式映射。
- XLSX：openpyxl/xlsxwriter。
- PPTX：python-pptx + Template/Theme 约束。
- 图表：Matplotlib，输出 PNG/SVG 和无障碍数据摘要。
- Office Preview：安装 LibreOffice 后转 PDF，再渲染页面图；未安装时保留下载并显示“预览组件未配置”。
- 中文字体：native-dev 使用项目登记的本地字体目录；secure-release 镜像固定 Noto CJK，保证排版一致。

预览失败不等于 Artifact 失败；用户仍可下载原文件，并看到明确的“预览不可用”。

---

# 19. 本地部署与网络

## 19.1 仓库结构

```text
apps/
  web/

backend/
  app/
  migrations/
  tests/

workers/
  agent/
  ingestion/
  render/
  sandbox/
  mcp_runner/

packages/
  contracts/
  generated-client/

infra/
  compose/
  docker/

tests/
  fixtures/
  e2e/
  live_model/

docs/
```

## 19.2 原生 Windows 开发进程

```text
Browser
  ├── http://127.0.0.1:3000  Next.js
  └── http://127.0.0.1:8000  FastAPI/SSE

Python 3.12 venv
  ├── api
  ├── outbox-relay
  ├── worker-agent
  ├── worker-ingestion
  └── worker-render

Existing native services
  ├── MySQL 3306
  ├── Redis 6379
  └── Elasticsearch 9200
```

计划提供 PowerShell 启停脚本，只启动项目自己的 API/Web/Worker 进程并保存 PID；不自动修改或重启用户现有 MySQL、Redis、Elasticsearch，不注册 Windows 系统服务。

开发期 FastAPI CORS 只允许精确 Origin `http://127.0.0.1:3000`/`http://localhost:3000`，允许凭据但不使用 `*`。发布时再用 Caddy 统一 Origin，并对 Run SSE 关闭代理缓冲。

当前 Redis 只监听 localhost，可以用于测试；Elasticsearch 当前 HTTP 无认证且监听范围较宽，不能存真实企业数据。开始真实用户测试前必须二选一：

1. 为项目创建独立、仅 localhost、启用认证的 Elasticsearch 实例。
2. 在确认不影响现有应用后加固当前实例，并为平台创建最小权限 API Key。

## 19.3 MySQL

使用现有本机 MySQL：

```text
company_agent        # 平台元数据
demo_finance         # 财务示例数据
```

账号：

```text
company_agent_app    # 对平台库读写，不使用 root
finance_reader       # 对 demo_finance 仅 SELECT
```

用户提供的开发密码只放在未提交的 `.env.local`/Secret 中。CI 使用独立临时 MySQL 容器和随机密码。

## 19.4 LocalFileStorage、Elasticsearch 和 Redis

`LocalFileStorage` 使用服务端生成的 Storage Key，不把用户文件名直接拼接为路径。根目录通过配置指定，不放在源码目录；浏览器不能直接访问该目录，所有上传、预览和下载都经过 API 权限检查。

Elasticsearch 索引使用固定前缀和版本：

```text
company-agent-knowledge-v1-<embedding_profile_hash>
```

Mapping 至少包含：

```text
workspace_id / knowledge_base_id / document_version_id / chunk_id
content / metadata / location
embedding: dense_vector, dims=1024, similarity=cosine
```

所有 BM25 和 kNN 查询由服务端强制注入 Workspace/Knowledge Base Filter。更换 Embedding Profile 或维数时创建新索引并重建，不原地混用。

Redis Streams 仅做任务分发和事件唤醒；Run/Step/Event 真相仍在 MySQL。当前 Redis 5 只用于 native-dev，安全发布时升级到受支持的新版本或等价服务。

## 19.5 本地 Secret

仓库只提交：

```text
.env.example
```

不提交：

```text
.env
.env.local
secrets/
storage/
Elasticsearch/MySQL 数据目录
测试录像中的敏感内容
```

平台 Secret 使用 AES-GCM 加密；主密钥不入 MySQL。Admin UI 写入后只能看到状态和最后更新时间。

## 19.6 健康检查

系统提供：

- `/health/live`。
- `/health/ready`。
- Admin“系统状态”页。

检查：

- MySQL。
- Redis。
- LocalFileStorage 可读写空间和剩余配额。
- Elasticsearch Version、License、认证和目标索引状态。
- Worker 心跳。
- Agnes Model Profile Probe 状态。
- SiliconFlow Vision/Embedding Profile Probe 状态。
- Renderer。
- Sandbox 状态；native-dev 必须明确显示“任意代码执行未启用”。

---

# 20. 测试策略

## 20.1 测试分层

### 单元测试

- 权限矩阵。
- 状态机。
- Version 不可变性。
- Schema/Field Source Validator。
- SQL 只读分析。
- Result Normalizer。
- MessagePart 序列化。
- SSE 去重。
- Error Classifier。

### 集成测试

- MySQL Migration/Repository。
- MySQL Outbox、Redis Streams Consumer Group、重复投递和恢复。
- LocalFileStorage 路径隔离、配额和文件往返。
- Elasticsearch BM25/kNN、1024 维 Mapping 和 Workspace Filter。
- 文件解析和 SiliconFlow Vision；本地 OCR 安装后增加回退测试。
- HTTP/MCP/Database Provider。
- Trusted Analyzer 只允许预定义操作；Sandbox 隔离和超时在 secure-release 闸门测试。
- DOCX/XLSX/PPTX/PDF Renderer。

### 契约测试

所有 Tool Provider 通过同一套兼容测试：

- Tool 列表和 Schema。
- 正常调用。
- 非法参数。
- 权限失败。
- Secret 缺失。
- Timeout/Cancel。
- 非法返回。
- 大响应体。
- Artifact 返回。
- Retry 和日志脱敏。

### E2E

- Playwright 覆盖 Chromium Desktop/Mobile。
- Nightly 覆盖 Firefox/WebKit。
- 不使用固定 Sleep，等待业务事件。
- 失败保留 Trace/截图/视频，落盘前检查 Secret。
- axe 覆盖登录、Chat、Run、Artifact、缺口和能力编辑器。

### 模型测试

两套模式：

1. `FakeModel/FakeEmbedding`：确定性，PR/CI 必跑。
2. `live-agnes`：真实 Agnes Chat/Tool，人工触发。
3. `live-siliconflow-vision`：Qwen URL/Base64、JSON Object 和 Tool 组合探测。
4. `live-siliconflow-embedding`：BGE-M3 批量、维数、相似度、限流和错误探测。

真实模型测试属于 Gate/发布门禁，不把外部波动当作普通单测失败。记录 Schema 合规率、Tool Call 成功率、Embedding 维数/检索指标、Token、延迟和错误，不保存 Key、原始敏感文档或认证 Header。

---

# 21. 示例 A：招投标自动验收

## 21.1 固定测试资料

- 知识库：营业执照、ISO9001、历史项目、产品资料。
- 故意缺失：项目经理证书。
- 当前文件：`智慧园区招标文件.pdf`。
- 模板：`投标文件模板.docx`。
- 第二次复用：另一份招标文件和相同 Plugin。

资料均使用虚构公司和测试数据，不使用真实敏感信息。

## 21.2 主流程

1. Admin 创建 Member 并授予知识库/Plugin 权限。
2. Member 登录并创建知识库。
3. 上传历史资料，等待索引完成。
4. 新建 Chat，选择知识库。
5. 上传本次招标 PDF 和 DOCX 模板。
6. 验证临时文件没有自动进入知识库。
7. 输入生成投标文件请求。
8. Run 执行文件解析、知识检索、要求提取和 Gap Detection。
9. 输出 `BidRequirementSpec`。
10. Chat 显示“项目经理证书缺失”，明确不会虚构。
11. 用户选择“继续生成并保留占位符”。
12. 生成 `DocumentSpec`。
13. 调用 Document Renderer。
14. 返回 DOCX Artifact 和 PDF 预览。
15. 引用可以定位到真实文件和页码。
16. Run Trace 展示版本、Step、来源和 Artifact。
17. 用户“保存为可复用能力”。
18. 生成招投标 Skill Draft 和绑定 Renderer 的 Plugin Draft。
19. Test Run 通过并发布。
20. 新 Chat 使用 Published Plugin 对第二份招标文件再次成功生成。

## 21.3 自动断言

- `BidRequirementSpec` 必填字段完整。
- 缺失证书不会出现虚构编号、发证机构或事实断言。
- DOCX 包含 `[待补充：项目经理证书]` 占位符。
- DOCX 包含必需章节、目录和模板样式。
- Citation 指向测试资料真实位置。
- SSE 重连不重复 Message/Step/Artifact。
- 未通过 Test Run 的 Draft 不能发布。
- Published Version 修改后保持不变，产生新 Draft。
- 第二次 Run 使用精确 Published Version。
- Artifact 可以回溯生成 Run。

---

# 22. 示例 B：财务经营分析自动验收

## 22.1 固定测试数据

在 `demo_finance` 创建：

```text
projects
monthly_revenue
monthly_cost
budgets
transactions
```

使用固定种子数据，预先计算收入、成本、利润、利润率和预算差异期望值。补充文件为 `2026H1经营补充数据.xlsx`。

## 22.2 管理员配置

1. Admin 创建 MySQL DataSource。
2. 使用只读 `finance_reader` Secret。
3. Test Connection 显示只读。
4. 发布 Connector/DataSource。
5. 授权 Member 使用。

## 22.3 成员运行

1. Member 新建 Chat，选择财务 DataSource。
2. 上传补充 Excel。
3. 输入“分析 2026 年上半年收入、成本、利润变化，生成图表和汇报 PPT”。
4. Runtime 执行：

```text
database.describe
  → database.query
  → Excel 读取
  → Sandbox 分析
  → 图表
  → PresentationSpec
  → PPT Renderer
```

5. Chat 返回有来源的经营结论。
6. 返回图表和 PPTX Artifact。
7. PPTX 可预览/下载并绑定 Run。
8. 用户把 PPTX 作为下一次输入。
9. 保存为财务经营分析 Plugin Draft。
10. Plugin 绑定财务分析 Skill、DataSource、Python、图表和 PPT Renderer Version。
11. Test Run 后发布。
12. 新对话再次执行并成功。

## 22.4 自动断言

- 数据库只执行 SELECT。
- UPDATE/DELETE/DDL 在 Provider 前被拒绝。
- 金额等字段来源为 Database/Excel，不允许 LLM 生成。
- 计算结果与固定种子期望值在容差内一致。
- Sandbox 无网络、无宿主文件访问且超时可终止。
- 图表有文字摘要和数据表。
- PPTX MIME、文件结构和关键页面正确。
- 密码/连接串不出现在 DOM、日志、Trace、截图和 PluginSpec。
- 移除 DataSource 权限后 Plugin 明确提示缺少权限。
- Workspace B 不能访问 Workspace A 的 Artifact。

---

# 23. 企业 API 平台级验收

虽然不计入两个业务 Demo，仍作为 V1 自动测试：

```text
粘贴接口说明
  → AI 生成 Connector/Tool Draft
  → Admin 确认 Schema/Auth
  → Test Connection
  → Test Invocation
  → Publish
  → Chat 生成参数提案
  → Validator
  → HTTP Provider
  → Result Normalizer
  → Artifact/Result
```

必须验证：

- Tool Schema 字段描述、枚举、日期格式。
- Secret 只保存引用。
- 无效参数不触达外部服务。
- SSRF 地址被拒绝。
- 可重试和不可重试方法分开。
- 外部程序错误只报告，不自动修改外部代码。

---

# 24. 非功能指标与上线门槛

## 24.1 本地 V1 容量基线

- 20 个注册用户。
- 10 个同时在线用户。
- 5 个并发 Agent Run。
- 2 个并发 Sandbox。
- 2 个并发知识摄取任务。
- 单 Workspace 10 GB 文件默认配额。

这是本地验收基线，不代表未来生产扩容上限。

## 24.2 性能和可靠性

- 普通元数据 API 本地 p95 < 500 ms。
- 创建 Run 到收到 `run.created` < 1 秒。
- 持久事件到 SSE 客户端显示 < 1 秒。
- 页面刷新后可以恢复正在运行的 Run。
- Worker 崩溃不会丢失已持久化 Step/Event。
- Agnes 首 Token 和总延迟单独统计，不把外部模型延迟算作本地 API SLO。

## 24.3 安全门槛

- Workspace 隔离自动测试全部通过。
- Secret 泄露扫描通过。
- HTTP SSRF 测试通过。
- Database 写入绕过测试通过。
- Sandbox 路径、网络、资源和宿主访问测试通过。
- Published Version 不可变测试通过。
- Artifact 授权下载测试通过。

## 24.4 用户可用门槛

从空环境到两个 Demo 必须满足：

1. 不手工修改业务表。
2. 除首次管理员 CLI 外，不需要开发者命令完成业务流程。
3. Admin 能从 UI 创建账号、配置模型、数据源和权限。
4. Member 能从 UI 完成两个 Demo。
5. 错误和空状态提供明确下一步。
6. 提供部署、管理员和普通用户三份使用说明。
7. Chat、文件、知识库、Plugin、Run 和 Artifact 有可恢复状态。

---

# 25. 实施阶段与验收闸门

## Gate 0：本地可行性 Probe

交付：

- uv Python 3.12 venv 与 Node 22 工具链验证。
- MySQL 凭据、最小权限用户和 Migration Probe。
- Agnes 文本、流式和 Tool Calling Probe。
- SiliconFlow Qwen URL/Base64 Vision、JSON Object 和 Tool 组合 Probe。
- SiliconFlow BGE-M3 批量 Embedding、1024 维和中文检索小基准。
- Redis Streams Consumer Group、Outbox、重复投递和恢复 Probe。
- Elasticsearch `dense_vector(1024)`、BM25 + kNN、Workspace Filter 和索引重建 Probe。
- LocalFileStorage 路径隔离、Hash、配额和文件往返。
- DOCX/XLSX/PPTX 生成 PoC；LibreOffice 预览明确记录为未安装能力。
- Trusted Analyzer 完成固定财务计算；验证 native-dev 不暴露任意代码执行。

Gate 0 当前不要求 Docker，也不声称通过 Sandbox 安全验收。退出条件是原生核心技术链达到最低预期、两个外部 Provider 的真实能力有记录、所有不通过项有明确替代方案。

## Phase 1：基础骨架

- Auth/User/Workspace。
- Chat/Conversation/MessagePart。
- File/LocalFileStorage。
- Model Gateway。
- Run/Step/Event/MySQL Outbox/Redis Streams/SSE。
- Artifact 基础。
- Audit 基础。

## Phase 2：Tool 闭环

- Secret。
- Connector/Tool/Version。
- HTTP Provider。
- Parameter Compiler/Validator。
- Result Normalizer。
- 企业 API 平台级测试。

## Phase 3：Skill/Plugin 复用

- Skill/Plugin Version。
- Test Run。
- Publish/Rollback/Clone/Share。
- Plugin Run。
- 最小 Run → Capability Draft。
- Repeat Success 自动测试。

## Phase 4：Knowledge 和招投标

- 全格式解析、SiliconFlow Vision、BGE-M3、Elasticsearch Hybrid Retrieval、Citation。
- BidRequirementSpec、Gap Detection。
- DocumentSpec/DOCX/PDF Preview。
- 示例 A 完整 E2E。

## Phase 5A：Database、可信分析器、MCP 和财务原生验证

- MySQL/PostgreSQL Provider。
- Trusted Analyzer（只执行仓库内置、经过测试的分析操作）。
- Excel/图表/PPT Renderer。
- Streamable HTTP MCP；stdio 只允许管理员配置的可信本地命令。
- 示例 B 完整 E2E。

## Phase 5B：完整 V1 Sandbox 安全闸门

- 安装并验证 Docker/等价隔离运行时。
- 一次性非 root 容器、无网络、只读根目录、CPU/内存/PID/超时限制。
- 隔离 stdio MCP Runner。
- 开放 Python Sandbox Tool 前完成逃逸、跨 Run、网络和资源耗尽测试。

Phase 5A 可以在无 Docker 环境完成业务效果验证；Phase 5B 未通过前，不允许把产品标记为完整 V1，也不允许普通用户执行任意模型生成代码。

## Phase 6：自然语言能力与生产加固

- Capability Builder 完整版。
- 修改意图分类和 Diff。
- Error Classifier。
- Model/Tool Metrics。
- 安全、恢复、容量和可访问性测试。
- 用户文档与发布检查。

完整 V1 的粗略周期仍按 6–8 人工程团队约 20–26 周评估；Gate 0、SiliconFlow/Agnes 实测、Office Preview 和后续隔离运行时选择会影响排期。

---

# 26. V1 Definition of Done

只有同时满足以下条件才能称为“完成全部第一版需求”：

1. Admin 可以初始化系统、创建/停用/重置成员。
2. Member 可使用接近 ChatGPT 交互模式的 Chat 完成任务。
3. File 与 Knowledge 在数据和 UI 上严格分离。
4. Knowledge 支持摄取、搜索、删除、重建和引用。
5. HTTP、MCP、MySQL、PostgreSQL、Builtin、Sandbox Tool 统一走 Gateway。
6. Tool 参数全部经过 Schema、业务、来源和权限校验。
7. Database 默认只读且多层阻断写操作。
8. 用户代码在一次性隔离容器执行。
9. Skill、Connector、Plugin 有不可变 Version、Test、Publish 和 Archived。
10. Plugin 可运行、修改、复制、分享和回滚。
11. Run 有 Step、Event、ToolCall、ModelCall、Artifact 和可恢复 Trace。
12. Artifact 支持需求中的全部类型，并可预览/下载/继续使用。
13. Chat 成功任务可生成 Skill/Plugin Draft，测试后发布。
14. Secret 不进入 Prompt、Chat、Spec、日志、Trace 和前端响应。
15. Workspace 隔离和基础权限测试通过。
16. 招投标示例完整通过并可第二次复用。
17. 财务经营分析示例完整通过并可第二次复用。
18. 企业 HTTP API 平台级场景通过。
19. SSE 断线恢复、Worker 故障和幂等测试通过。
20. 普通用户不需要开发工具即可完成两个示例。

---

# 27. 审核确认项

0.2 已根据用户反馈确认：当前暂不搭建 Docker；接受两个业务示例、内置 Renderer、账号/权限方案；数据库使用现有本机 MySQL，Secret 不写入文档。更新后的重点结论是：

1. native-dev 复用现有 MySQL、Redis、Elasticsearch，不新增 Qdrant/MinIO/Docker。
2. 主 Chat 为 Agnes；Embedding 为 SiliconFlow `BAAI/bge-m3`；Vision 为 SiliconFlow `Qwen/Qwen3.5-4B`。
3. 本地图片可通过 Base64 发给 SiliconFlow，但必须受 Workspace 外发策略和 UI 提示控制。
4. 当前 Elasticsearch 无认证，只能放虚构测试数据；真实企业数据前必须创建独立安全实例或加固现有实例。
5. 当前没有 LibreOffice，先验收 Office 文件生成；预览安装后再启用。
6. 当前没有安全 Sandbox：财务示例先用 Trusted Analyzer，完整 V1 发布前仍必须完成隔离运行时闸门。
7. 模型 Key 和数据库密码尚未进行认证调用；只在用户明确开始实施后经 Secret 注入运行 Probe。

本文档更新不代表开始实施。只有用户明确说“开始实施”后，才创建环境、安装依赖、建库或调用带凭据的模型 API；届时先执行 Gate 0，再根据报告决定是否进入 Phase 1–6。

---

# 28. 参考资料

- 原始需求：`需求文档/v1/v1_requirements.md`
- Agnes 2.5 Flash 官方文档：https://agnes-ai.com/zh-Hans/docs/agnes-25-flash
- SiliconFlow Chat Completions：https://docs.siliconflow.cn/cn/api-reference/chat-completions/chat-completions
- SiliconFlow Multimodal Vision：https://docs.siliconflow.cn/cn/userguide/capabilities/multimodal-vision
- SiliconFlow Embeddings：https://docs.siliconflow.cn/cn/api-reference/embeddings/create-embeddings
- SiliconFlow Function Calling：https://docs.siliconflow.cn/cn/userguide/guides/function-calling
- Qwen/Qwen3.5-4B 模型卡：https://huggingface.co/Qwen/Qwen3.5-4B
- BAAI/bge-m3 模型卡：https://huggingface.co/BAAI/bge-m3
- Elasticsearch kNN Search：https://www.elastic.co/docs/solutions/search/vector/knn
- MCP Transport 最新官方规范：https://modelcontextprotocol.io/specification/latest/basic/transports
- MySQL Vector Functions 官方说明：https://dev.mysql.com/doc/refman/26.7/en/vector-functions.html

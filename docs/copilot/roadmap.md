# Neorvion ERP Copilot 路线图

## 1. 产品目标

ERP Copilot 是独立于 ERP Core、IAM 和 Knowledge 的智能交互层。它帮助用户查询业务、解释异常、生成操作草稿，并在明确授权和人工确认后调用现有 ERP API 执行动作。

核心边界：

- Copilot 不直接读写 ERP MySQL，不导入 ERP Model、Repository 或 Service。
- 业务查询和写入只通过 ERP API；知识检索只通过 Knowledge API。
- 身份、租户与权限以 IAM 为唯一权威来源。`X-Tenant-ID` 只是用户意愿，所有下游服务仍需自行校验。
- 写操作必须经过 Tool → ERP API → TenantContext → RBAC → 状态机 → DB。
- 有业务副作用的动作必须具备幂等键、审计记录；高风险动作必须“预览 → 用户确认 → 执行”。
- 模型输出不具有执行权限。只有服务端注册、校验并授权的 Tool 能调用下游 API。

## 2. 目标架构

```text
Browser / apps/copilot
        |
        v
services/copilot (FastAPI, port 8013)
  - conversation / SSE
  - planner and tool registry
  - policy / confirmation / audit
  - PostgreSQL: copilot-owned state only
        |
        +---- IAM 8010: JWT, tenant snapshot, high-risk authorize
        +---- ERP 8011: business read/write APIs
        +---- Knowledge 8012: search/RAG/citations
        +---- model provider: OpenAI-compatible chat API
```

前端作为 Wujie 子应用挂到 Shell `/copilot`，开发端口 `8019`。后端使用独立 `services/copilot`，API 端口 `8013`。当前只复用 Knowledge 所在 PostgreSQL 实例；Knowledge 使用 `neorvion_knowledge`，Copilot 使用独立的 `neorvion_copilot` 数据库、专用角色和 `copilot_alembic_version`。不要把 Copilot Router 注册进 ERP 或 Knowledge。

## 3. 版本路线

### V1：只读 Copilot MVP

目标：可信地回答“发生了什么、为什么、下一步看哪里”，不执行任何 ERP 写操作。

- 独立 FastAPI 与 React 微前端骨架，接入 Shell、IAM audience 和 `copilot:use` 权限。
- 会话、消息、Tool Run、引用和模型用量落 Copilot PostgreSQL。
- SSE 事件：`status`、`tool_call`、`tool_result`、`token`、`citation`、`done`、`error`。
- 服务端白名单只读 Tool，首批覆盖：工作台摘要、销售订单详情/列表、采购单详情/列表、库存查询、商品查询、任务与操作日志查询。
- Knowledge 检索作为独立 Tool，回答业务制度或操作说明时返回文档引用。
- 下游调用透传用户 Bearer Token 与已验证的租户头；ERP/Knowledge 仍独立做 RBAC。
- 防护：最大 Tool 步数、超时、结果截断、参数 Schema 校验、敏感字段过滤、文档内容按不可信输入处理。
- `MODEL_PROVIDER=mock` 可离线测试；真实模型密钥只在服务端环境变量。
- V1 明确拒绝所有写意图，并说明尚未支持执行。

验收口径：跨租户访问无法发生；无权限 Tool 不可调用；无命中不编造；回答能追溯到业务 API 或 Knowledge 引用；模型不可用时给出明确错误；测试不调用真实模型。

### V2：可解释的多步只读分析

目标：从单次查询升级为受控的跨域分析。

- 多 Tool 规划，但限制步骤、并行度、超时和数据量。
- 结构化结果卡片与页面深链，例如订单、SKU、库存、任务和异常卡片。
- 订单—库存—出库—物流的只读链路分析；采购—收货—库存链路分析。
- 统一 Trace、Tool 延迟、Token、失败原因和反馈记录。
- 建立离线评测集：Tool 选择正确率、参数正确率、回答事实性、租户隔离和拒答。
- 支持会话标题、历史搜索、反馈与重新生成。

### V3：会话持久化与 Copilot 微前端

目标：将 V2 的只读 Agent 做成可刷新恢复、可多轮使用的完整业务入口。

- PostgreSQL 保存用户私有会话、消息、模型工具协议与脱敏 ToolRun 摘要。
- 会话行锁、数据库唯一约束和 `client_request_id` 保证并发与幂等边界。
- 服务端从可信历史重建上下文，按完整 turn 裁剪，不接受客户端伪造持久化历史。
- React/Wujie 微前端提供会话 CRUD、POST SSE、工具过程、停止生成和租户切换清理。
- 本版仍只注册 ERP 只读工具，不引入 Knowledge RAG、写操作或 Checkpointer。

### V4：Knowledge RAG 与可追溯分析（当前）

目标：在保持只读边界的前提下，把 ERP 实时事实与企业制度、流程知识联合回答，并让结论可追溯。

- 复用 Knowledge 的 HYBRID/VECTOR/KEYWORD、RRF 与 Rerank，不在 Copilot 复制向量库。
- 用户显式指定知识库范围；Knowledge 独立执行租户、权限和知识库 Grant 校验。
- ERP 与 Knowledge 结果形成服务端证据登记，SSE 提供状态和 evidence 事件。
- 历史 Knowledge 证据展示前重新鉴权；权限撤销、来源删除和版本变化有明确状态。
- 外部知识只作为不可信事实材料，服务端拒绝模型伪造的引用编号。
- 继续禁止 ERP 写操作、多 Agent、Checkpointer 和自由 URL/SQL/Shell 工具。

### V5：动作提案与审批

### V6：可恢复的长流程

目标：支持需要等待、重试和人工介入的工作流。

- 使用持久化状态图或等价状态机管理跨步骤任务。
- 支持暂停、恢复、取消、有限重试、超时、补偿与人工接管。
- PostgreSQL 是流程状态真相；队列只传递任务 ID。
- 典型场景：缺货排查、待出库异常核对、采购收货差异处理建议。
- 任何自动执行仍受 V5 的 Proposal、确认和策略约束。

### V7：事件驱动的主动洞察

目标：从“用户提问”扩展到“系统发现值得关注的异常”。

- 订阅 `system_events` 或稳定事件接口，不直接轮询或读 ERP 数据库。
- 规则先行，模型负责解释和归纳，不让模型独立决定高风险动作。
- 租户级订阅、静默时段、去重、节流和通知偏好。
- 只在有意义变化、失败或需要用户动作时通知，避免噪声。

### V8：企业治理与运营

目标：让 Copilot 可度量、可控、可运营。

- 模型路由、降级、预算、租户配额和成本归集。
- Prompt、Tool Schema、策略与评测集版本化，可回滚、可对比。
- 管理后台展示使用量、成功率、拒答率、Tool 错误率、P95 和用户反馈。
- 数据保留、脱敏、导出、删除和合规审计策略。
- 灰度发布、功能开关、租户白名单与紧急停用开关。

### V9：领域技能与生态

目标：在稳定平台上扩展可治理的 ERP 技能，而不是无限制自由 Agent。

- 将销售、采购、库存、售后等能力拆成版本化 Skill/Tool 包。
- 提供只读 OpenAPI/Tool 契约生成与兼容性测试。
- 支持外部系统连接器时，仍通过服务端凭据库、最小权限与审计。
- 用评测门槛决定 Skill 是否可发布，不以演示效果代替可靠性。

### VN：目标形态

Copilot 最终应成为“受策略控制的 ERP 操作入口”：默认只读、证据优先、权限继承、执行可预览、风险可审批、过程可恢复、结果可审计。VN 不追求模型拥有数据库权限，也不追求无人监督地执行所有业务。

## 4. 推荐交付节奏

每个版本拆成可独立验收的纵向切片：

1. 服务骨架、鉴权和健康检查。
2. 数据模型、迁移与会话 API。
3. 单个只读 Tool 的端到端闭环。
4. Planner、SSE 与前端会话页。
5. 扩展 Tool、评测、审计和部署配置。

每个切片都必须同时包含后端测试、前端测试或类型检查、文档和配置示例。不要一次性生成整个 VN，也不要在一个提交范围内同时引入写操作与高风险审批。

## 5. V1 不做

- 不直接连接 ERP MySQL。
- 不修改销售、采购、库存、物流或售后状态。
- 不支持任意 URL、任意 SQL、任意 Python 或 Shell Tool。
- 不让模型选择租户、伪造权限或覆盖服务端确认策略。
- 不引入多 Agent 自由协作；先把单 Agent 的 Tool 契约、审计和评测做扎实。
- 不在 API 容器启动时自动执行 Alembic；迁移仍是独立部署步骤。

## 6. 开发进度

### V1-A：已并入 V1-B 前置实现

- `services/copilot` 独立 FastAPI 服务与 8013 端口。
- IAM audience、授权快照、`copilot:use` 权限、`/health` 与 `/me`。
- Docker Compose、请求 ID、统一错误响应和基础测试。

### V1-B：已实现

- OpenAI-compatible Chat Adapter，支持 DeepSeek 与百炼兼容端点。
- `MODEL_PROVIDER=mock` 的离线测试模式。
- 单节点 LangGraph StateGraph，无 Checkpointer、无多 Agent。
- `POST /api/v1/chat` 非流式接口。
- `POST /api/v1/chat/stream` SSE 接口，事件为 `message` / `done` / `error`。
- 客户端只能携带有限 `user` / `assistant` 上下文，系统提示由服务端注入。
- 尚未实现 ERP Tool、Knowledge Tool、前端和会话持久化；这些不属于 V1-B。

### V2：ERP 只读 Tool Calling 已实现

- OpenAI-compatible Adapter 支持 `tools`、`tool_choice`、流式 `tool_calls` 参数拼接和 `tool` 消息。
- LangGraph 升级为 `Agent → Tool → Agent` 条件循环，限制轮次、调用数、总时限、分页与结果大小。
- 只读工具覆盖销售订单、库存、商品、采购单、仓库和售后；所有数据通过 ERP HTTP API 获取。
- 使用已验证用户的多 audience Access Token 和租户头访问 ERP；ERP 继续独立校验租户与具体读权限。
- 服务端执行工具白名单、严格参数校验、字段脱敏、结果截断和不可信数据隔离。
- SSE 新增 `tool_start` / `tool_end` / `tool_error`，保留 `message` / `done` / `error`。
- 未注册低库存工具：现有阈值不是持久化的可信安全库存配置，V2 不生成补货结论。
- 仍未实现前端、会话持久化、Knowledge/RAG、多 Agent、写操作或审批。

### V3：会话与微前端已实现

- 新增独立 `copilot_*` PostgreSQL 表与 `copilot_alembic_version` 迁移版本表。
- 会话访问同时约束已验证租户和当前用户；复合租户外键与 `TenantAsyncSession` 双重守卫。
- 持久化 Chat 支持幂等 `client_request_id`、会话行锁、单会话单生成和异常 RUNNING 恢复。
- 完整保存用户消息、助手消息、模型协议消息与脱敏 ToolRun 摘要。
- 服务端按完整 turn 裁剪上下文，避免拆散 tool_calls/tool 消息，并给 ERP 结果标记查询时间。
- 新增 `apps/copilot`，支持历史会话、安全文本渲染、POST SSE、工具状态、停止生成和租户切换清理。
- Shell 注册 `/copilot` Wujie 保活微前端，继续使用 Shell Token、租户和刷新契约。

### V4 启动前修复：已完成代码与本地数据库验证

- Copilot 已从 `neorvion_knowledge` 迁到同实例的独立 `neorvion_copilot`，使用最小权限专用角色；
  新环境由初始化脚本建库，已有环境按“备份—迁移—校验—切换”执行。
- 旧 Knowledge 数据库中的 Copilot 表暂时保留作为回滚副本；任何清理都需要再次核对数据并取得明确授权。
- 数据库连接池等待、建连、SQL 和 IAM Redis 快照读取均有可配置的有限超时，并返回明确 503。
- 持久化 Chat 使用短事务和 `FOR NO KEY UPDATE` 串行化同一会话；所有异常/取消路径立即回滚，
  LLM 与 ERP 调用不持有数据库事务，避免 `idle in transaction` 长时间占锁。
- 已增加独立数据库、真实 PostgreSQL CRUD/ToolRun/租户隔离/幂等/并发/池耗尽，以及 GET、普通 Chat、
  SSE 与断开清理测试。V4 仍需在目标部署环境完成备份校验、灰度切换和监控观察后再启动。

### V4：Knowledge RAG 与证据引用已实现

- 新增 `search_knowledge` 只读工具，直接调用 Knowledge 现有 `/api/v1/search`，复用混合检索、RRF 与 Rerank。
- 知识库 ID 必须显式提供；Copilot 检查 `knowledge:read` 与 audience，Knowledge 再执行租户和知识库 Grant 复核。
- ERP 与 Knowledge 工具结果由服务端登记为 `[E数字]` / `[K数字]` 证据；模型伪造编号不会进入最终答案。
- 新增 `copilot_evidences` 迁移；SSE 提供 `analysis_status` 与 `evidence`，会话详情返回分类来源。
- 历史 Knowledge 证据会并发重新鉴权并受整批超时保护；失权或删除后不返回旧摘录，版本变化标记为 `STALE`。
- 前端支持工具过程、实时分析状态、ERP/Knowledge 来源卡片和安全文本详情展示。
- 保持单 LangGraph 受控循环、只读边界和服务端安全校验；未引入写操作、多 Agent 或 Checkpointer。


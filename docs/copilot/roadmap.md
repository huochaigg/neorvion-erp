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

前端作为 Wujie 子应用挂到 Shell `/copilot`，建议开发端口 `8018`。后端使用独立 `services/copilot`，建议 API 端口 `8013`，使用独立 PostgreSQL 数据库 `neorvion_copilot`。不要把 Copilot Router 注册进 ERP 或 Knowledge。

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

### V3：草稿型低风险动作

目标：允许创建“尚未生效”的业务草稿，不允许模型直接改变库存或关键状态。

- 引入 Action Proposal：模型提出结构化草稿，服务端重新校验 Schema、权限和资源归属。
- 首批只支持低风险动作，例如创建草稿销售单/采购单、补充备注；具体范围以现有 ERP API 能力为准。
- 预览差异、明确展示将调用的动作与参数，由用户确认后执行。
- 每次执行携带幂等键；Proposal 有过期时间、参数哈希和一次性确认令牌。
- 用户修改任何关键参数后必须重新预览和确认。

### V4：高风险动作与审批

目标：在强约束下支持会影响库存、资金或状态机的动作。

- 接入 IAM 高风险实时回源授权，不能只依赖缓存快照。
- 对确认订单、确认收货、确认出库、退款、盘点、调拨等动作逐个建立策略。
- 强制“服务端预览 → 人工确认 → 服务端执行”，预览结果与执行参数通过哈希绑定。
- 二人审批或职责分离作为可配置策略；执行前再次读取当前资源状态，过期预览拒绝执行。
- 审计记录包含操作者、租户、Proposal、确认、下游 request id 和最终结果，但不记录密钥与敏感正文。

### V5：可恢复的长流程

目标：支持需要等待、重试和人工介入的工作流。

- 使用持久化状态图或等价状态机管理跨步骤任务。
- 支持暂停、恢复、取消、有限重试、超时、补偿与人工接管。
- PostgreSQL 是流程状态真相；队列只传递任务 ID。
- 典型场景：缺货排查、待出库异常核对、采购收货差异处理建议。
- 任何自动执行仍受 V3/V4 的 Proposal、确认和策略约束。

### V6：事件驱动的主动洞察

目标：从“用户提问”扩展到“系统发现值得关注的异常”。

- 订阅 `system_events` 或稳定事件接口，不直接轮询或读 ERP 数据库。
- 规则先行，模型负责解释和归纳，不让模型独立决定高风险动作。
- 租户级订阅、静默时段、去重、节流和通知偏好。
- 只在有意义变化、失败或需要用户动作时通知，避免噪声。

### V7：企业治理与运营

目标：让 Copilot 可度量、可控、可运营。

- 模型路由、降级、预算、租户配额和成本归集。
- Prompt、Tool Schema、策略与评测集版本化，可回滚、可对比。
- 管理后台展示使用量、成功率、拒答率、Tool 错误率、P95 和用户反馈。
- 数据保留、脱敏、导出、删除和合规审计策略。
- 灰度发布、功能开关、租户白名单与紧急停用开关。

### V8：领域技能与生态

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


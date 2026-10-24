# Neorvion ERP Copilot V6

独立 FastAPI + LangGraph 服务，默认端口 `8013`。V6 保留 V1-V5 全部能力，并为三类 Action Proposal 增加显式人工确认、确定性审批、执行前复核、ERP 最终幂等写入、审计和 UNKNOWN 对账。

## API 与事件

| API | 说明 |
| --- | --- |
| `GET /api/v1/health` | 公开健康检查 |
| `GET /api/v1/me` | 已验证的租户上下文和权限 |
| `POST /api/v1/chat` | 多轮工具循环后的完整回答 |
| `POST /api/v1/chat/stream` | SSE：`analysis_status`、`message`、`tool_start`、`tool_end`、`tool_error`、`evidence`、`done`、`error` |
| `POST /api/v1/conversations` | 创建当前用户私有会话 |
| `GET /api/v1/conversations` | 分页查询当前用户会话 |
| `GET /api/v1/conversations/{id}` | 加载消息、ToolRun 与经当前权限复核的证据 |
| `POST /api/v1/conversations/{id}/messages` | 向已有会话发送消息（SSE） |
| `PATCH /api/v1/conversations/{id}` | 重命名会话 |
| `DELETE /api/v1/conversations/{id}` | 软删除会话 |
| `POST/GET /api/v1/action-proposals` | 创建或分页查询当前用户业务草稿 |
| `GET/PATCH /api/v1/action-proposals/{id}` | 读取或按 revision 编辑草稿 |
| `POST /api/v1/action-proposals/{id}/validate` | 执行 ERP 无副作用预检 |
| `POST /api/v1/action-proposals/{id}/cancel` | 取消草稿（不可恢复） |
| `GET /api/v1/action-proposals/{id}/revisions` | 查看版本历史 |
| `POST /api/v1/action-proposals/{id}/confirmations` | 冻结 revision 并签发一次性确认票据 |
| `POST /api/v1/action-executions/{id}/confirm` | 当前 Proposal 所有者显式确认 |
| `POST /api/v1/action-executions/{id}/execute` | 获批后由申请人以当前权限执行 |
| `GET /api/v1/action-executions` | 当前用户执行记录分页 |
| `GET /api/v1/action-executions/{id}` | 当前用户执行详情 |
| `POST /api/v1/action-executions/{id}/reconcile` | UNKNOWN 状态按 ERP Receipt 对账 |
| `GET /api/v1/action-approvals` | `copilot:approve` 租户审批队列 |
| `POST /api/v1/action-approvals/{id}/approve|reject|revoke` | 审批决策或申请人撤销 |
| `GET /api/v1/action-executions/{id}/audit` | 追加式业务审计时间线 |

持久化聊天请求使用 `conversation_id`、`client_request_id`、`message`。旧版 `messages` 无会话请求保持兼容。

## 独立数据库与迁移

Copilot 与 Knowledge 只复用 PostgreSQL **实例**，不再复用数据库：Knowledge 使用
`neorvion_knowledge`，Copilot 使用 `neorvion_copilot`。Copilot 还应使用专用登录角色
`neorvion_copilot`；该角色仅拥有 Copilot 数据库，不授予超级用户、建库或建角色权限。
连接串及密码只能来自环境变量或部署 Secret：

```env
DATABASE_URL=postgresql+psycopg://neorvion_copilot:<secret>@127.0.0.1:5432/neorvion_copilot
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=5
DATABASE_POOL_TIMEOUT_SECONDS=3
DATABASE_CONNECT_TIMEOUT_SECONDS=3
DATABASE_STATEMENT_TIMEOUT_MS=5000
IAM_AUTH_TIMEOUT_SECONDS=4
IAM_REDIS_CONNECT_TIMEOUT_SECONDS=1.5
IAM_REDIS_READ_TIMEOUT_SECONDS=1.5
```

新 Docker 数据卷会通过 `deploy/postgres/init-databases.sh` 创建专用角色和数据库；初始化前必须设置
`COPILOT_POSTGRES_PASSWORD`。已有数据卷不会再次执行 entrypoint 初始化脚本，应由管理员手工创建：

```sql
CREATE ROLE neorvion_copilot LOGIN PASSWORD '<secret>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE DATABASE neorvion_copilot OWNER neorvion_copilot
  ENCODING 'UTF8' TEMPLATE template0;
```

随后使用 Copilot 的连接串执行迁移：

```bash
uv run --directory services/copilot alembic upgrade head
```

应用启动不会自动执行迁移。会话、消息、ToolRun 和 Evidence 通过复合租户外键关联；Repository 还会同时约束当前 `user_id`。V4 迁移 `20261023_0002` 新增 `copilot_evidences`，降级会删除该表，因此降级前应先备份证据记录。
每次开始持久化对话时会把超过 `STALE_RUN_SECONDS` 的本用户异常 RUNNING 记录恢复为失败终态；生产环境后续可把同一规则放入周期性维护任务。软删除会话当前不自动物理清理。

### 已有环境从 Knowledge 数据库迁出

1. 停止 Copilot 写流量，分别记录旧库四张表的行数、约束和索引。
2. 使用管理员账号备份旧库中的 `copilot_conversations`、`copilot_messages`、
   `copilot_tool_runs`、`copilot_alembic_version`，并验证备份清单和校验和。
3. 创建专用角色/数据库，用专用连接串执行 `alembic upgrade head`。
4. 按外键顺序导入三张业务表；迁移版本表由新库 Alembic 管理，不用旧库记录覆盖它。
5. 比对每表行数、主键、复合外键、唯一约束、索引以及抽样的 tenant/user 归属，再执行 CRUD、
   幂等、ToolRun 和 SSE 断开测试。
6. 切换 Copilot `DATABASE_URL` 并重启，只在观察期通过后再考虑清理旧对象。

旧表是可回滚副本。在未取得明确授权前，**禁止**从 `neorvion_knowledge` 执行 `DROP TABLE`，
也不得删除 Knowledge 的 `alembic_version` 或业务表。回滚时停止 Copilot 写流量，把连接串切回已备份且
仍完整的旧库并重启；若新库已接收新写入，应先备份新库并制定增量合并方案，不能直接覆盖旧库。

### 超时排查

`GET /conversations/{id}` 只走 IAM、数据库和 Repository，不调用模型或 ERP。发生等待时先按请求耗时日志
区分 IAM 与数据库，再检查 `pg_stat_activity`、`wait_event`、`pg_blocking_pids(pid)`、连接池占用和
`idle in transaction`。持久化 Chat 的会话锁只存在于建立消息占位的短事务中；LLM/ERP 网络调用不得跨越
该事务。服务端对 Redis/IAM、数据库建连、取连接和 SQL 都设置有限超时，数据库不可用或连接池耗尽返回
明确的 503，不应靠无限增大前端 timeout 掩盖锁或泄漏。SSE 客户端断开时会取消生成并写入终态、释放 Session。

客户端只能发送有限的 `user` / `assistant` 上下文，最后一条必须是 `user`。工具名、参数 Schema、租户、权限与下游地址均由服务端决定。

当前白名单工具：

- `get_sales_order`、`list_sales_orders`
- `get_inventory`
- `get_product`、`search_products`
- `list_purchase_orders`
- `get_warehouse`
- `get_after_sale`
- `list_knowledge_bases`、`search_knowledge`（先确认当前用户可见范围，检索必须显式提供一个或多个知识库 ID）
- `analyze_inventory_coverage`（精确 SKU + 显式日期区间；服务端固定公式计算）

没有注册 `list_low_stock_skus`：现有 ERP 库存 API 的 `threshold` 是调用方临时查询参数，不是可信、持久化的 SKU 安全库存配置。V2 只返回客观库存数量，不把临时阈值包装成补货结论。

## 身份与安全边界

IAM 当前 Access Token 同时包含 `neorvion-copilot`、`neorvion-erp` 和 `neorvion-knowledge` audience。Copilot 先校验 JWT、租户快照与 `copilot:use`，工具执行时再检查对应 audience 和 `*:read` 权限，然后只把原始用户 Token 与已验证的 `X-Tenant-ID` 转发到下游。ERP 与 Knowledge 会分别独立验证 JWT、租户成员关系和具体权限；Knowledge 还会按现有知识库 Grant 复核每个知识库及引用切片。

知识文档按不可信外部输入处理。模型只能引用服务端登记的 `[K数字]` / `[E数字]`，未知编号会被替换为“来源不可验证”。证据表保存检索时的有限快照和版本；加载历史会话时，Knowledge 来源会再次调用切片详情鉴权。权限撤销或来源删除后正文不再返回；版本变化标记为 `STALE`，不会把新内容冒充旧证据。

工具调用还会执行：服务端白名单、Pydantic `extra=forbid` 参数校验、最大轮次/调用数/总时限、结果字段白名单、大小截断。ERP 结果用不可信数据边界包裹后才交给模型；Token、租户参数、客户电话/地址、仓库联系方式不会进入模型上下文。

## 配置

```env
MODEL_PROVIDER=openai_compat
CHAT_BASE_URL=https://api.deepseek.com
CHAT_API_KEY=
CHAT_MODEL=deepseek-chat
CHAT_TIMEOUT_SECONDS=30
CHAT_MAX_OUTPUT_TOKENS=1024
CONVERSATION_CONTEXT_TOKENS=6000

DATABASE_URL=postgresql+psycopg://neorvion_copilot:<secret>@127.0.0.1:5432/neorvion_copilot
DATABASE_POOL_TIMEOUT_SECONDS=3
DATABASE_CONNECT_TIMEOUT_SECONDS=3
DATABASE_STATEMENT_TIMEOUT_MS=5000
IAM_AUTH_TIMEOUT_SECONDS=4

ERP_BASE_URL=http://127.0.0.1:8011
ERP_JWT_AUDIENCE=neorvion-erp
ERP_CONNECT_TIMEOUT_SECONDS=3
ERP_READ_TIMEOUT_SECONDS=10
ERP_EXECUTION_TIMEOUT_SECONDS=15
ERP_EXECUTION_SECRET=<与 ERP COPILOT_EXECUTION_SECRET 相同的至少 32 字节 Secret>
ERP_EXECUTION_AUTHORIZATION_TTL_SECONDS=60
CONFIRMATION_TTL_SECONDS=300
APPROVAL_TTL_SECONDS=86400
ACTION_GRAPH_ENABLED=true
KNOWLEDGE_BASE_URL=http://127.0.0.1:8012
KNOWLEDGE_JWT_AUDIENCE=neorvion-knowledge
KNOWLEDGE_CONNECT_TIMEOUT_SECONDS=3
KNOWLEDGE_READ_TIMEOUT_SECONDS=12
KNOWLEDGE_TOP_K_MAX=8
KNOWLEDGE_EVIDENCE_EXCERPT_CHARS=600
TOOL_MAX_ROUNDS=5
TOOL_MAX_CALLS=8
TOOL_TOTAL_TIMEOUT_SECONDS=30
TOOL_MAX_RESULT_CHARS=12000
TOOL_MAX_PAGE_SIZE=50
```

百炼可使用 `CHAT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` 和兼容 Tool Calling 的模型。密钥只能放本地 `.env` 或部署 Secret。

## 本地运行与测试

```bash
uv sync --directory services/copilot
uv run --directory services/copilot python -m app
uv run --directory services/copilot ruff check app tests
uv run --directory services/copilot pytest -q --tb=short
# 真实 PostgreSQL 测试库名称必须以 _test 结尾
COPILOT_TEST_DATABASE_URL=postgresql+psycopg://neorvion_copilot:<secret>@127.0.0.1:5432/neorvion_copilot_test \
  uv run --directory services/copilot pytest tests/test_postgres_integration.py -q
corepack pnpm --filter @neorvion/copilot test
corepack pnpm --filter @neorvion/copilot build
```

`python -m app` 会读取 `.env` 的 `APP_HOST` / `APP_PORT`（默认 `0.0.0.0:8013`）。Windows 必须使用该入口（内部指定 Selector 事件循环）。不要直接 `uvicorn app.main:app`，否则 psycopg 异步驱动无法连接 PostgreSQL。

生产构建 Copilot 前端时设置 `VITE_PUBLIC_BASE=/copilot/`、`VITE_API_BASE_URL=/copilot-api`。
Nginx 会去掉 `/copilot-api` 后再转发到 8013，并为 SSE 关闭代理缓冲；这也避免与
Knowledge 的 `/api/v1/conversations` 同路径冲突。

测试使用 mock 模型与 `httpx.MockTransport`，不调用真实 IAM、ERP 或付费模型。

## 调用示例

```bash
curl -X POST http://localhost:8013/api/v1/chat \
  -H "Authorization: Bearer <multi-audience-access-token>" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"查询 SKU-001 的可用库存"}]}'
```

```bash
curl -N -X POST http://localhost:8013/api/v1/chat/stream \
  -H "Authorization: Bearer <multi-audience-access-token>" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"订单 123 当前状态是什么？"}]}'
```

Knowledge 问答必须在消息中明确给出已授权的知识库 ID，例如“在知识库 11 中查询 DRAFT 是否预占库存”。服务端工具请求固定发送到 Knowledge `/api/v1/search`，不会接受模型提供的 URL。库存覆盖分析还需 `analytics:sales:read` 与 `inventory:read`，并要求明确 SKU 与日期区间；公式为 `可用库存 / 区间有效销量日均值`，日均销量为 0 时返回无法计算，不转化为补货建议。

## V5 Action Proposal

V5 增加三类只属于 Copilot 的业务草稿：采购单、销售订单、库存调拨。Action Registry 与只读 Tool Registry
分离，Registry 只登记参数 Schema、真实 IAM 权限、可编辑字段和固定 ERP Preview 地址，不含执行 Handler。
模型可调用 `propose_action` / `validate_action_proposal`，但 HTTP 客户端只允许访问三个
`/api/v1/action-previews/*` 路径，无法访问 ERP 创建、更新、取消或库存写接口。

数据表为 `copilot_action_proposals`、`copilot_proposal_revisions`、`copilot_proposal_validations`。
提案按 tenant + user 隔离，关联同一所有人的 Conversation；创建使用稳定幂等键，编辑必须携带
`expected_revision`，冲突返回 409。编辑后旧预检自然失效并显示 `STALE`，预检过期也显示 `STALE`；
取消或提案过期后不可编辑和预检。`READY` 仅表示当前 revision 在特定时点通过预检。

```bash
uv run --directory services/copilot alembic upgrade head
# 仅在可销毁测试数据库验证 downgrade
uv run --directory services/copilot alembic downgrade 20261023_0002
uv run --directory services/copilot alembic upgrade head
```

API：`POST/GET /api/v1/action-proposals`、`GET/PATCH /api/v1/action-proposals/{id}`、
`POST .../{id}/validate`、`POST .../{id}/cancel`、`GET .../{id}/revisions`。创建示例：

```json
{
  "conversation_id": 1,
  "idempotency_key": "purchase-request-20261023-001",
  "action": {
    "action_type": "PURCHASE_ORDER_CREATE",
    "payload": {"supplier_id": 3, "warehouse_id": 2, "items": [{"sku_id": 8, "quantity": 100}]}
  }
}
```

React 前端在对话内和独立“业务草稿”页提供编辑、保存、重新预检、历史版本与取消；没有正式执行按钮。
SSE 在原协议上新增 `proposal_created`、`proposal_updated`、`proposal_validation`，仅携带草稿 ID、revision、
类型和状态，不推送完整业务 payload。
草稿编辑器通过 ERP 既有 suppliers/customers/warehouses/product-skus 只读 API 提供远程选择；开发环境可用
`VITE_ERP_API_BASE_URL=http://localhost:8011`，生产环境留空走同源 `/api` 反向代理。ERP 会独立复核读权限。

## V6 受控执行

Execution Registry 与 LLM Tool Registry 完全分离，只登记采购、销售、库存调拨三个固定路径。模型没有
`execute_action` Tool；聊天里的“继续”不是授权。确认票据绑定 tenant、user、proposal、revision、payload hash
和短期有效期，服务端只保存 nonce hash，使用后不能重放。采购和销售为 MEDIUM，当前确定性策略无需审批；
调拨为 HIGH，固定要求 `copilot:approve` 异人审批。申请人不能自批，审批后仍由申请人以当前 JWT 和最新 IAM
权限执行，因此权限撤销会阻断写入。

正式写入前 Copilot 再调用 Preview，ERP 端在同一 MySQL 事务内再次 Preview、占用
`tenant_id + execution_key`、调用既有 Service 创建 DRAFT 单据并保存 Receipt。三类创建都不会自动提交审核、
确认、预占、出库或入库。相同 key + payload 返回原结果；相同 key + 不同 payload 返回 409。网络超时或 5xx
进入 UNKNOWN，禁止重新创建，只能查询 ERP Receipt 对账。

PostgreSQL 业务表：`copilot_action_executions`、`copilot_action_approvals`、
`copilot_action_execution_attempts`、`copilot_action_audit_events`、`copilot_action_graph_checkpoints`。
LangGraph 独立执行图使用官方 `AsyncPostgresSaver`、`interrupt()` 与 `Command(resume=...)`；Saver 自己幂等管理
`checkpoints`、`checkpoint_blobs`、`checkpoint_writes`、`checkpoint_migrations`。业务数据库状态是授权与审计权威，
Checkpoint 只负责技术恢复，二者不能互相替代。

迁移：Copilot `20261024_0004`，ERP `20261024_0023`。降级会删除 V6 执行/审批/审计或 ERP Receipt，必须先
停止执行流量、确认无 EXECUTING/UNKNOWN、导出审计与 Receipt 并验证备份。跨 PostgreSQL/MySQL 没有原子事务；
一致性由不可变 payload hash、ERP 最终幂等和 Receipt 对账保证。

V6 不做自动审批、自动提交/发货/出入库、退款、库存直接调整、任意 URL/SQL/Shell、多 Agent 和复杂 Saga。

## V7 真实模型与业务工作流

运行配置默认改为 `MODEL_PROVIDER=openai_compat`。实际本地 `.env` 若仍为 `mock` 会明确显示 Mock 横幅；真实
Provider 未配置密钥时 Chat 返回 503，不会回退到模拟回答。`GET /api/v1/model-status` 只返回 provider、模型名和
`available/mock/unconfigured/unavailable`，不会返回密钥。DeepSeek 使用 `https://api.deepseek.com` +
`deepseek-chat`；百炼使用 `https://dashscope.aliyuncs.com/compatible-mode/v1` 和实际已开通的兼容模型名。

Workflow Registry 当前只允许 `INVENTORY_REPLENISHMENT_WORKFLOW` 与只读
`SALES_ORDER_REVIEW_WORKFLOW`。工作流 API 为 `POST/GET /api/v1/workflows`、详情、steps、events、metrics、
resume、retry、cancel。库存流程不会编造安全库存、交期、在途、价格或采购数量；缺少供应商、仓库和数量时进入
`WAITING_INPUT`，生成 Proposal 后进入 `WAITING_CONFIRMATION`，正式写入继续复用 V6 Execution。

V7 表由 `20261024_0005` 创建。Redis 队列名默认 `copilot:workflows:v1`，仅投递 tenant/workflow ID；PostgreSQL
是状态权威。Worker 没有当前用户 JWT 时只回收租约并暂停等待重新授权，不会保存旧 JWT 或绕过权限执行下游步骤。
唯一例外是 UNKNOWN 的只读 Receipt 对账：Worker 用独立短期 HMAC 调 ERP 固定 internal-receipts 路径，它不能携带
payload 或创建单据，成功后以同一个 execution key 恢复 Execution/Workflow。Redis 消息丢失时 Worker 会从数据库
扫描过期租约；对账使用有限次数指数退避，耗尽预算后转人工介入。
不能安全补偿的已创建 ERP 单据进入 `NEEDS_MANUAL_INTERVENTION`，绝不自动删除或反向调拨。

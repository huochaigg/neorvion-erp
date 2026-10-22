# Neorvion ERP Copilot V3

独立 FastAPI + LangGraph 服务，默认端口 `8013`。V3 增加 PostgreSQL 会话、消息、ToolRun 持久化和 `apps/copilot` 微前端；ERP 数据仍只通过只读 HTTP Tool 获取。

## API 与事件

| API | 说明 |
| --- | --- |
| `GET /api/v1/health` | 公开健康检查 |
| `GET /api/v1/me` | 已验证的租户上下文和权限 |
| `POST /api/v1/chat` | 多轮工具循环后的完整回答 |
| `POST /api/v1/chat/stream` | SSE：`message`、`tool_start`、`tool_end`、`tool_error`、`done`、`error` |
| `POST /api/v1/conversations` | 创建当前用户私有会话 |
| `GET /api/v1/conversations` | 分页查询当前用户会话 |
| `GET /api/v1/conversations/{id}` | 加载消息与 ToolRun |
| `POST /api/v1/conversations/{id}/messages` | 向已有会话发送消息（SSE） |
| `PATCH /api/v1/conversations/{id}` | 重命名会话 |
| `DELETE /api/v1/conversations/{id}` | 软删除会话 |

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

应用启动不会自动执行迁移。会话、消息和 ToolRun 通过复合租户外键关联；Repository 还会同时约束当前 `user_id`。
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

没有注册 `list_low_stock_skus`：现有 ERP 库存 API 的 `threshold` 是调用方临时查询参数，不是可信、持久化的 SKU 安全库存配置。V2 只返回客观库存数量，不把临时阈值包装成补货结论。

## 身份与安全边界

IAM 当前 Access Token 同时包含 `neorvion-copilot` 和 `neorvion-erp` audience。Copilot 先校验 JWT、租户快照与 `copilot:use`，工具执行时再检查 ERP audience，然后只把原始用户 Token 与已验证的 `X-Tenant-ID` 转发到 ERP。ERP 会独立验证 JWT、租户成员关系和具体 `*:read` 权限。

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

## V3 明确不做

Knowledge RAG、任意 URL/SQL/Shell 工具、多 Agent、Checkpointer、写操作、审批、断线续传和自动补货均不在本版本范围内。

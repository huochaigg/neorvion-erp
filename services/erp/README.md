# Neorvion ERP

独立 FastAPI 服务。复制仓库根目录 `.env.example` 为 `services/erp/.env` 后启动。监听地址来自 `.env` 的 `APP_HOST` / `APP_PORT`（默认 `0.0.0.0:8011`）。

身份、登录、租户成员与角色只属于 IAM（`neorvion_iam`）。本库 `neorvion_erp` 不再包含 `users` / `tenants` / RBAC 表；业务行只存整数 ID，展示名走 `identity_name_snapshots`。`alembic upgrade head` 含 `20261018_0022` DROP，对有数据的本地库请先备份再人工执行。

在服务目录：

```bash
cd services/erp
cp ../../.env.example .env
uv sync
uv run alembic upgrade head
uv run python -m app
```

在仓库根目录（monorepo，不必先 `cd`）：

```bash
uv run --directory services/erp python -m app
```

Worker：

```bash
uv run --directory services/erp python -m app.tasks.worker
```

## Copilot V5 无副作用预检

ERP 提供三个 `POST /api/v1/action-previews/*` 端点，分别复用采购、销售和调拨 Service 的真实 Schema、
实体状态与权限校验。它们只执行 SELECT，不调用正式 `create_*`，不以 rollback 模拟预览，也不生成订单、
明细、库存预占/扣减、事件、操作流水、通知或任务：

- `/api/v1/action-previews/purchase-order`：`purchase:create`
- `/api/v1/action-previews/sales-order`：`order:create`
- `/api/v1/action-previews/inventory-transfer`：`stock_transfer:create`

响应包含 `valid`、阻断错误、警告、标准化参数、摘要、资源版本和过期时间。销售预检会提示当前库存与
缺失单价；调拨预检会把源仓可用库存不足作为阻断错误。预检通过不保证后续执行成功，未来执行接口必须
重新校验全部业务规则和权限。

## Copilot V6 固定执行与最终幂等

ERP 新增三个固定 `POST /api/v1/action-executions/*` 端点和 Receipt 查询。每个请求同时验证用户 JWT、租户
快照、原创建权限，以及 Copilot 用共享 Secret 签发的短期 HMAC 执行授权；授权绑定 tenant、user、动作、
execution key、revision、payload hash 和过期时间。浏览器和模型不能指定任意 URL，也不能绕过 ERP 的独立权限。

- `/purchase-order`：只创建 `DRAFT` 采购单。
- `/sales-order`：只创建 `DRAFT` 销售单，不确认、不预占。
- `/inventory-transfer`：只创建 `DRAFT` 调拨单，不调出、不调入。
- `GET /action-executions/{execution_key}`：权限复核后返回 Receipt，供 UNKNOWN 对账。

`erp_action_execution_receipts` 以 `(tenant_id, execution_key)` 唯一。ERP 在一个 MySQL 事务中插入 Receipt、再次
执行 Preview 业务校验、调用既有创建 Service 和更新成功资源 ID；并发 10 次相同 key 最终只产生一张单据。
相同 key 不同 payload 返回 409。配置 `COPILOT_EXECUTION_SECRET` 必须与 Copilot 的
`ERP_EXECUTION_SECRET` 相同，生产至少 32 字节并由部署 Secret 注入。

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

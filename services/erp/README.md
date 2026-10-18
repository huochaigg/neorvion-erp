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

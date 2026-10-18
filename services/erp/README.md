# Neorvion ERP

独立 FastAPI 服务。复制仓库根目录 `.env.example` 为 `services/erp/.env` 后启动。监听地址来自 `.env` 的 `APP_HOST` / `APP_PORT`（默认 `0.0.0.0:8011`）。

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

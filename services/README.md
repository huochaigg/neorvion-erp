# services

独立后端服务，各有自己的 `pyproject.toml`、`uv.lock`、`.env`、Alembic 和测试。不要合并成一个 FastAPI。

```text
services/
├── erp/                  # FastAPI + MySQL（当前）
├── knowledge/            # FastAPI + PostgreSQL + RAG（当前）
├── copilot/              # FastAPI + LangGraph（未来，尚未创建）
└── customer-service/     # FastAPI + WebSocket（未来，尚未创建）
```

在仓库根目录分别启动（host / port 读各自 `.env`）：

```bash
uv run --directory services/erp python -m app
uv run --directory services/knowledge python -m app
```

Worker：

```bash
uv run --directory services/erp python -m app.tasks.worker
uv run --directory services/knowledge python -m app.tasks.worker
```

本机 ERP API 端口是 **8011**。Knowledge API 是 **8012**。

# services

独立后端服务，各有自己的 `pyproject.toml`、`uv.lock`、`.env`、Alembic 和测试。不要合并成一个 FastAPI。

```text
services/
├── erp/                  # FastAPI + MySQL（当前）
├── knowledge/            # FastAPI + PostgreSQL + RAG 预留（当前）
├── copilot/              # FastAPI + LangGraph（未来，尚未创建）
└── customer-service/     # FastAPI + WebSocket（未来，尚未创建）
```

本地启动：

```bash
cd services/erp && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8011
cd services/knowledge && uv run python -m app
```

本机 ERP API 端口是 **8011**（不是 8001）。Knowledge API 是 **8012**。

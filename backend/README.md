# Neorvion ERP backend

复制仓库根目录 `.env.example` 为 `backend/.env` 后启动。

```bash
cd backend
cp ../.env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8011
```

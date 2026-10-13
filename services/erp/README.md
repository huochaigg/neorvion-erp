# Neorvion ERP

独立 FastAPI 服务。复制仓库根目录 `.env.example` 为 `services/erp/.env` 后启动。

```bash
cd services/erp
cp ../../.env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8011
```

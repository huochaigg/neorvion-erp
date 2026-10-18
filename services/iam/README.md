# Neorvion IAM

统一身份、租户、会话与功能 RBAC。ERP / Knowledge 只本地校验本服务签发的 RS256 JWT，并从 Redis 读取授权快照，不再回源本库。

## 端口与数据库

- API：`8010`
- MySQL 库：`neorvion_iam`（与 ERP 库隔离，禁止跨库 JOIN）
- Redis DB：`1`（refresh / CSRF / 授权快照）
- JWKS：`GET /.well-known/jwks.json`

## 启动

在本目录执行：

```bash
cd services/iam
uv sync
uv run python scripts/generate_keys.py
uv run alembic upgrade head
uv run python -m app.scripts.seed_permissions
uv run python -m app
```

从旧 ERP 库一次性搬迁身份数据：

```bash
uv run python -m app.scripts.migrate_from_erp
```

## 测试

```bash
uv run pytest
uv run ruff check app tests
```

# Neorvion IAM

统一身份、租户、会话与功能 RBAC。ERP / Knowledge 只本地校验本服务签发的 RS256 JWT，并从 Redis 读取授权快照，不再回源本库。

## 端口与数据库

- API：`8010`
- MySQL 库：`neorvion_iam`（与 ERP 库隔离，禁止跨库 JOIN）
- Redis DB：`1`（refresh / CSRF / 授权快照）
- JWKS：`GET /.well-known/jwks.json`

## 启动

```bash
cp services/iam/.env.example services/iam/.env
# 生成独立的密码传输 RSA 与 JWT RS256 密钥，两套私钥不得混用
uv sync --directory services/iam
uv run --directory services/iam python scripts/generate_keys.py
uv run --directory services/iam alembic upgrade head
uv run --directory services/iam python -m app.scripts.seed_permissions
uv run --directory services/iam python -m app
```

从旧 ERP 库一次性搬迁身份数据：

```bash
uv run --directory services/iam python -m app.scripts.migrate_from_erp
```

## 测试

```bash
uv run --directory services/iam pytest
uv run --directory services/iam ruff check app tests
```

# Neorvion Knowledge

独立的 AI 知识库服务。当前里程碑：**Knowledge V1**。

Knowledge 不替代 ERP 登录，也不直连 ERP MySQL。用户仍通过 Shell 登录；Knowledge 后端校验 JWT 签名后，再调用 ERP 内部身份内省确认租户成员与权限。

## 本地运行

1. PostgreSQL 已安装并运行。创建数据库：

```sql
CREATE DATABASE neorvion_knowledge;
CREATE DATABASE neorvion_knowledge_test;
```

2. 复制环境变量：

```bash
cp knowledge/.env.example knowledge/.env
```

把 `DATABASE_URL` 改成本机 PostgreSQL，把 `ERP_JWT_SECRET` 设成与 `backend/.env` 的 `SECRET_KEY` 相同，把 `ERP_INTERNAL_SERVICE_KEY` 设成与 ERP `INTERNAL_SERVICE_KEY` 相同。

3. 安装依赖并迁移：

```bash
cd knowledge
uv sync
uv run alembic upgrade head
uv run python -m app
```

Windows 必须使用 `python -m app`（内部指定 Selector 事件循环）。不要直接 `uvicorn app.main:app`，否则 psycopg 异步驱动无法连接 PostgreSQL。Linux / CI 可继续使用：

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

4. 前端：

```bash
pnpm install
pnpm --filter @neorvion/knowledge dev
```

访问：

- Knowledge API：http://127.0.0.1:8002/api/v1/health
- Knowledge 微前端：http://localhost:8017
- Shell 入口：http://localhost:8015/knowledge

完整说明见 [docs/knowledge.md](../docs/knowledge.md)。

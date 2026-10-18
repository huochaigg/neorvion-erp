# Neorvion Knowledge

独立的 AI 知识库服务。当前里程碑：**Knowledge V5**（企业级管理 + RAG 评测初始化）。

Knowledge 不替代登录，也不直连 IAM / ERP 业务库。用户通过 Shell 登录 IAM；Knowledge 本地校验 IAM 签发的 RS256 JWT，并从 Redis 读取授权快照。删除知识库等高温操作回源 `POST /api/v1/internal/authorize`。文档共享 ACL 由本服务检查。

## 本地运行

1. PostgreSQL 已安装并运行。创建数据库：

```sql
CREATE DATABASE neorvion_knowledge;
CREATE DATABASE neorvion_knowledge_test;
```

2. 复制环境变量：

```bash
cp services/knowledge/.env.example services/knowledge/.env
```

把 `DATABASE_URL` 改成本机 PostgreSQL。`IAM_JWKS_URL` 指向 IAM `:8010`。生产必须配置 `IAM_AUTHORIZE_URL` 与 `IAM_INTERNAL_KEY`。不要再设置已删除的 `ERP_JWT_SECRET` / `ERP_INTERNAL_SERVICE_KEY`。

3. 安装依赖并迁移：

```bash
cd services/knowledge
uv sync
uv run alembic upgrade head
uv run python -m app
```

在仓库根目录（monorepo，不必先 `cd`）：

```bash
uv run --directory services/knowledge python -m app
```

Worker：

```bash
uv run --directory services/knowledge python -m app.tasks.worker
```

`python -m app` 会读取 `.env` 的 `APP_HOST` / `APP_PORT`（默认 `0.0.0.0:8012`）。Windows 必须使用该入口（内部指定 Selector 事件循环）。不要直接 `uvicorn app.main:app`，否则 psycopg 异步驱动无法连接 PostgreSQL。

4. 前端：

```bash
pnpm install
pnpm --filter @neorvion/knowledge dev
```

访问：

- Knowledge API：http://127.0.0.1:8012/api/v1/health
- Knowledge 微前端：http://localhost:8017
- Shell 入口：http://localhost:8015/knowledge

完整说明见 [docs/knowledge.md](../../docs/knowledge.md)。

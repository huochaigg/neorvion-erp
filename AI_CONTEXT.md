# AI_CONTEXT

新 Cursor 会话先读本文件，再读 `docs/current-state.md`。以当前代码为准。

## 项目定位

Neorvion 已拆独立 **IAM :8010**（V2：会话表、高风险回源、授权版本）。ERP :8011 与 Knowledge :8012 是业务服务，本地校验 RS256 JWT。详见根 README 与 `docs/iam-operations.md`。ERP 业务模块本身已收口到 V15。

下一阶段才是 ERP Copilot / Agent。Agent **不直接写 ERP 数据库**。

生产：OpenCloudOS 9.2 + 宝塔 Nginx + Docker Compose。ERP 用 MySQL。Knowledge / RAG 用 PostgreSQL + pgvector。禁止自动 git commit / push / 创建 production 分支。

## 禁止

- 自动 `git add` / `commit` / `push` / `tag` / `reset` / `rebase`
- 新增商品 / 采购 / 销售 / 库存 / 物流 / 售后等大业务域（Core 已收口）
- 把库存 `quantity` 放进 Redis 当强一致缓存
- Repository 内 `commit`
- Router 直接改业务 `status`
- 任意 `PATCH status`
- Query Key 不带 `tenantId` 去拉租户数据
- 破坏 Wujie：租户切换不要 `destroyApp`，不要 `queryClient.clear()`
- 伪造生产客户、GMV、QPS、用户量
- 自动 SSH / 操作腾讯云生产机
- 把生产 Secret、RSA 私钥、数据库密码写进 Git
- 公网开放 MySQL 3306 / Redis 6379 / Postgres 5432 / FastAPI 8010/8011/8012
- ERP 业务写入走 PostgreSQL；Postgres 只给未来 Agent / RAG
- 每个 API 容器启动时自动 Alembic；Migration 是独立部署步骤

## 技术栈

- 后端：Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic + MySQL 8 + Redis。ERP 在 `services/erp`，Knowledge 在 `services/knowledge`，不要合并成一个 FastAPI
- 前端：React 19 + Vite + Wujie + Ant Design 6 + TanStack Query + Zustand
- 端口：Shell 8015 / ERP 8016 / API 8011 / Knowledge 前端 8017 / Knowledge API 8012
- Knowledge 是独立 FastAPI + PostgreSQL，不要把 Router 注册进 ERP，也不要 import ERP Model/Repository/Service

## 事务

- Repository：读写，只 `add` / `flush`，禁止 commit
- Service：事务边界，关键 Action 结束才 commit
- 库存变更与单据、流水、`system_events` 同一 Session
- 多 SKU 按 `sku_id`（必要时 `inventory_id`）升序加锁
- Session 按请求创建，异常后关闭即可回滚；不要到处套 `try/except rollback`

## 租户 / RBAC

- `users` 没有 `tenant_id`。成员关系在 `tenant_members`
- `X-Tenant-ID` 只是意愿，必须再查成员
- Permission 全局目录；Role 租户内
- 跨租户资源统一 **404**，不泄露存在性
- 关键写操作后端 `require_permission`，前端隐藏按钮不是安全边界

## 库存语义

- `quantity`：仓库实数
- `reserved_quantity`：已预占未出库
- `available_quantity` **不落库** = `quantity - reserved_quantity`
- 订单确认只加 reserved，不减 quantity
- 出库同时减 quantity 和 reserved

## 前端

- 租户 Query Key：`['tenant', tenantId, ...]`
- 全局：`current-user`、`my-tenants`
- Zustand 只放认证 / 租户 UI / 微前端必要状态
- Mutation 后精准 invalidate List / Detail / Inventory / Analytics
- 日期 `YYYY-MM-DD`，日期时间 `YYYY-MM-DD HH:mm:ss`，中文 Locale

## 注释

- 业务含义不直观的 Schema / Swagger 字段写中文 description
- 复杂 Service 方法写中文 docstring 和关键步骤注释
- 不要为统一 comment 大规模建无意义 migration

## Agent

查询可走现有只读 API。写操作必须：Tool → ERP API / Service → TenantContext → RBAC → 状态机 → DB。
高风险写操作未来需要预览 → 用户确认 → 执行。V15 不开发 Agent。

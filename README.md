# Neorvion ERP

多租户跨境电商 ERP。当前仓库按里程碑持续迭代，**不要为每个版本重建项目**。

当前里程碑：**V2.1.1**（V2.1 认证 + 配置化路由 / Refresh 白名单）。

## 技术栈

- 前端：React 19 + TypeScript strict + Vite + Wujie + Ant Design 6 + Tailwind CSS 4 + SCSS Modules + Zustand + TanStack Query
- 后端：Python 3.12 + uv + FastAPI + SQLAlchemy 2.x + Alembic + MySQL 8 + Redis
- 仓库：pnpm workspace 管理 `apps/*` 与 `packages/shared`

## 目录结构

```text
neorvion-erp/
├── apps/
│   ├── shell/                 # 微前端主应用（登录、租户、整体导航）
│   └── erp/                   # ERP 子应用（业务菜单与页面，可独立启动）
├── packages/shared/           # 主应用路由常量、API 类型、Query Key、ApiError
├── backend/
│   ├── app/
│   │   ├── api/               # HTTP 路由
│   │   ├── core/              # 配置、异常、日志、安全、租户上下文
│   │   ├── db/                # Engine / Session / Mixin
│   │   ├── models/            # SQLAlchemy ORM
│   │   ├── schemas/           # Pydantic
│   │   ├── repositories/      # 持久化，禁止自行 commit
│   │   ├── services/          # 业务规则与事务边界
│   │   ├── agents/            # AI Agent 预留
│   │   └── tasks/             # Celery 预留
│   ├── alembic/
│   └── tests/
├── docs/
├── nginx/
├── docker-compose.yml
└── .env.example
```

没有单独的 `modules/` 目录，避免与 `services/`、`repositories/` 职责重叠。后续业务按领域文件扩展，例如 `services/inventory.py`、`repositories/inventory.py`。

## 本地运行

### 1. 环境变量

```bash
cp .env.example .env
cp .env.example backend/.env
cp apps/shell/.env.example apps/shell/.env
cp apps/erp/.env.example apps/erp/.env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
Copy-Item .env.example backend\.env
Copy-Item apps\shell\.env.example apps\shell\.env
Copy-Item apps\erp\.env.example apps\erp\.env
```

### 2. 启动 MySQL 与 Redis

推荐使用 Docker Compose（只需基础设施）：

```bash
docker compose up -d mysql redis
```

如果本机已经有 MySQL / Redis，把 `backend/.env` 中的连接信息改成实际值。

### 3. 启动后端（端口 8011）

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8011
```

验证：

- Swagger：http://localhost:8011/docs
- 健康检查：http://localhost:8011/api/v1/health

### 4. 启动前端

在仓库根目录：

```bash
pnpm install
pnpm dev
```

- 主应用：http://localhost:8015 （工作台，不含 ERP 业务页）
- ERP 子应用独立运行：http://localhost:8016
- 主应用接入 ERP：http://localhost:8015/erp

分别启动：

```bash
pnpm dev:shell
pnpm dev:erp
```

### 5. 测试与检查

```bash
cd backend
uv run pytest
uv run ruff check app tests
```

```bash
pnpm --filter @neorvion/shell build
pnpm --filter @neorvion/erp build
```

## V2.1.1

- ERP 菜单与 React Router 共用 `apps/erp/src/router/routes.ts`
- Refresh 明确为公开接口，不校验 Access Token
- 前端 `ApiError` 统一业务错误；无 `debugger` 语句

## V2.1 完成内容

- 全局 `users` 表与 Alembic 迁移
- 注册、登录、Refresh Cookie、退出登录、`/me`
- Argon2id 密码哈希 + RSA-OAEP 传输加密 + Access/Refresh JWT
- Shell 登录/注册页、路由守卫、Axios 单飞刷新
- ERP 不重复登录，只接收主应用传入的 token
- pytest 使用独立测试库 `neorvion_erp_test`

本地注意：

- 后端端口固定 8011，避免和本机其他 FastAPI（常见 8001）冲突。
- MySQL 必须指向独立库 `neorvion_erp`，不要使用其他项目的业务库。
- 无界依赖 iframe 沙箱，请用系统 Chrome 打开主应用验证嵌入。

## 尚未开始

多租户、RBAC、商品库存、采购、销售订单。这些从 V2.2 起在同一仓库扩展。

更细的说明见 `docs/development.md`、`docs/architecture.md`、`docs/auth.md` 与 `docs/routing.md`。

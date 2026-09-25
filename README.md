# Neorvion ERP

多租户跨境电商 ERP。当前仓库按里程碑持续迭代，**不要为每个版本重建项目**。

当前里程碑：**M1 项目初始化与基础设施**。

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
├── packages/shared/           # 前后端共享的路由常量、API 类型、Query Key
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

### 3. 启动后端（端口 8001）

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

验证：

- Swagger：http://localhost:8001/docs
- 健康检查：http://localhost:8001/api/v1/health

### 4. 启动前端

在仓库根目录：

```bash
pnpm install
pnpm dev
```

- 主应用：http://localhost:5173
- ERP 子应用独立运行：http://localhost:5174/erp/dashboard
- 主应用接入 ERP：http://localhost:5173/erp/dashboard

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

## M1 完成内容

- 主应用基础布局、工作台、`/erp` 微前端接入
- ERP 子应用基础布局、业务菜单占位页，可独立运行
- Tailwind CSS 4 + SCSS CSS Modules + Ant Design Design Token
- FastAPI、SQLAlchemy 2.x、Alembic、健康检查
- Docker Compose（MySQL / Redis / Backend）
- 基础 pytest（Swagger、健康检查响应结构、OpenAPI 路径）

本地注意：

- 后端端口固定 8001。若本机 `127.0.0.1:8001` 已被其他项目占用，请先释放端口。
- MySQL 账号以 `.env` 为准；未创建 `neorvion` 用户时，健康检查会返回 `mysql: unavailable`，Alembic 也无法升级。
- 无界依赖 iframe 沙箱，请用系统 Chrome 打开主应用验证嵌入；ERP 可先在 5174 独立确认。

## M1 不包含

用户认证、RBAC、商品库存、采购、销售订单。这些从 M2 开始在同一仓库扩展。

更细的说明见 `docs/development.md` 与 `docs/architecture.md`。

# Neorvion ERP

多租户跨境电商 ERP。当前仓库按里程碑持续迭代，**不要为每个版本重建项目**。

当前里程碑：**V4**。

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
uv run python -m app.scripts.seed_permissions
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
pnpm test
```

## V4

- 仓库档案：名称、编码、类型、地址、联系人、启停、默认仓库
- 未填编码时服务端生成 `WH` + 10 位 id；`(tenant_id, code)` 唯一
- 默认仓切换同一事务 + `SELECT ... FOR UPDATE`，每租户最多一个默认仓
- ERP 菜单「仓库管理」：列表 + Drawer；权限 `warehouse:read/create/update/disable/delete`
- 版本文档：`docs/versions/v4.md`，业务说明：`docs/warehouses.md`

## V3

- 商品档案：类目（最多三级）、品牌、SPU、SKU（`spec_values` JSON）
- 创建商品时 SPU + SKU 同一事务；列表按租户隔离，SKU 数量用 SQL 聚合
- ERP 菜单：商品列表 / 类目管理 / 品牌管理；新增和编辑为独立页面
- 权限沿用 `product:read/create/update/delete`，类目和品牌不另拆编码
- 版本文档：`docs/versions/v3.md`，业务说明：`docs/products.md`

## V2.3.5

- 企业内 `TenantMember.display_name`，回退 `User.display_name`；改一家企业不影响全局账号
- 成员/角色细粒度权限；旧 `*:manage` 迁移保留兼容
- 角色授权改为菜单 + 按钮权限树；权限目录只读
- 自定义角色编辑/删除（使用中返回 `ROLE_IN_USE`）；系统角色后端保护
- 版本文档：`docs/versions/v2.3.5.md`

## V2.3.4

- 成员：添加已有账号、代建新账号（一次性临时密码）、查看、改角色、启用/禁用、移出企业
- 角色：自定义角色编辑/删除、系统预置角色配置权限（OWNER 冻结）
- 权限目录只读页；角色权限按模块勾选，保存后菜单和按钮立即生效
- `users.must_change_password` + `POST /auth/change-password`；临时账号 40350
- 版本文档：`docs/versions/v2.3.4.md`

## V2.3.3

- ERP 按当前成员有效权限生成菜单；无权限隐藏，空父级分组自动隐藏
- 页面 `PermissionGuard`：加载中不放行，无权限显示 403，不登出、不 Refresh
- 按钮 `<Can permission="..." />`；成员/角色页已接入
- `GET /api/v1/tenants/current/my-permissions`；Query Key 带 tenantId
- 版本文档：`docs/versions/v2.3.3.md`

## V2.3.2

- 企业成员管理闭环：按邮箱添加已注册用户、分配多个角色、启停成员
- ERP「系统管理」：成员管理、角色管理页面；按钮按权限编码控制
- 成员角色替换使用行锁；OWNER 保护仍在后端强制执行
- 版本文档：`docs/versions/v2.3.2.md`

## V2.3.1

- RBAC：`permissions` / `roles` / `member_roles` / `role_permissions`
- 权限目录幂等初始化；创建租户时生成 OWNER / ADMIN / OPERATOR / WAREHOUSE / VIEWER
- `require_permission` / `require_any_permission`；角色管理 API
- 历史租户 OWNER 成员回填系统角色，保留 `tenant_members.role` 与 `created_by`

## V2.2.4

- Shell 接入 V2.2.1 租户接口：创建企业、选择工作空间、切换企业
- 当前租户只保存在 Shell `tenant-store`；ERP 通过 Wujie props 与 `shell:tenant-changed` 同步
- Axios 按精确跳过名单自动附加 `X-Tenant-ID`；React Query 用 `['tenant', tenantId, ...]` 隔离缓存
- 租户切换不 `destroyApp`、不重新登录、不 Refresh；离开 ERP 再进入仍保活
- 上次选择按用户写入 `localStorage`（`neorvion:last-tenant-id:{userId}`），只作偏好，仍以后端成员关系为准

## V2.2.1

- 共享库多租户：`tenants`、`tenant_members`
- `X-Tenant-ID` + `TenantContext`；创建者预留 OWNER
- 一个用户可加入多家企业；成员管理最小权限

## V2.1.2

- 公钥改为公开接口 `GET /api/crypto/public-key`
- 认证状态：`initializing` / `authenticated` / `unauthenticated`
- 独立 `authClient`；登录成功不立刻 Refresh；ERP 不轮换 Refresh

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

完整菜单权限组件已在 V2.3.5 收尾。V3 完成商品档案。V4 完成仓库档案。尚未开始：OWNER 转移、操作日志、库存数量、采购、销售订单。

更细的说明见 `docs/development.md`、`docs/architecture.md`、`docs/auth.md`、`docs/multi-tenancy.md`、`docs/rbac.md`、`docs/products.md`、`docs/versions/v3.md`、`docs/routing.md`、`docs/micro-frontend-integration.md` 与 `docs/micro-frontend-interview.md`。

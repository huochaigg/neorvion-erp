# 开发说明（M1）

## 前置

- Node.js 22+
- pnpm 12+
- Python 3.12
- uv
- Docker Desktop（推荐，用于 MySQL / Redis）

## 日常命令

安装前端依赖：

```bash
pnpm install
```

同时启动主应用与 ERP：

```bash
pnpm dev
```

安装并启动后端：

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

数据库迁移：

```bash
cd backend
uv run alembic current
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "your message"
```

M1 的初始迁移是空结构，只验证 Alembic 链路。M2 才会创建 `users`、`tenants` 等表。

代码检查：

```bash
cd backend
uv run ruff check app tests
uv run pytest
```

```bash
pnpm lint
pnpm build
```

## 验证清单

1. 打开 http://localhost:5173 ，工作台能显示。
2. 点击「ERP 业务」，能加载子应用，地址为 `/erp/dashboard`。
3. 刷新 `/erp/products` 不应丢失子应用。
4. 直接打开 http://localhost:5174/erp/dashboard ，子应用可独立运行。
5. http://localhost:8001/docs 可打开 Swagger。
6. `/api/v1/health` 返回统一 `{ code, message, data }`。
7. Tailwind 布局类生效；ERP 页头使用 SCSS Module。
8. 主应用与子应用样式没有明显互相污染。

## 常见问题

**本机 8001 已被其他进程占用**

Neorvion 后端必须使用 8001。如果 `127.0.0.1:8001` 已经被别的 FastAPI 占用，浏览器访问 `localhost:8001/docs` 会看到旧应用。请先结束占用进程，再启动本仓库后端：

```powershell
Get-NetTCPConnection -LocalPort 8001 | Select-Object OwningProcess,State
```

**子应用白屏**

- 确认 ERP 已启动在 5174。
- 确认 CORS 与 `server.origin` 仍为 `http://localhost:5174`。
- 确认入口调用了 `window.__WUJIE.mount()`。
- 无界依赖 iframe 沙箱。部分内嵌浏览器会拦截 iframe 的 `contentWindow`，请用系统 Chrome 打开 http://localhost:5173/erp/dashboard。
- 子应用本身可用 http://localhost:5174/erp/dashboard 独立验证。

**MySQL / Redis 为 unavailable**

- 检查 `backend/.env` 账号是否与实际实例一致。
- 本机 3306/6379 可能已被其他服务占用，不要和 Docker 映射冲突。

**Docker 守护进程未启动**

- Compose 文件仍可使用，但需要先启动 Docker Desktop：
  `docker compose up -d mysql redis`
- Alembic 需要能连上 MySQL 后才能 `upgrade head`。M1 初始迁移为空，只打通命令链路。

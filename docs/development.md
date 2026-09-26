# 开发说明

当前里程碑：V2.2.4（多租户前端集成与状态隔离）。

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
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8011
```

数据库迁移：

```bash
cd backend
uv run alembic current
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "your message"
```

M1 的初始迁移为空。V2.1 增加 `users` 表，执行：

```bash
cd backend
uv run alembic upgrade head
```

生成本地 RSA 密钥（私钥不会提交到 Git）：

```bash
cd backend
uv run python scripts/generate_rsa_keys.py --key-id v1
```

把输出的 `RSA_KEY_ID` / `RSA_PRIVATE_KEY_PATH` / `RSA_PUBLIC_KEY_PATH` 写入 `backend/.env`。生产环境改为从密钥管理系统加载同一路径变量，不要把 PEM 打进镜像。

代码检查：

```bash
cd backend
uv run ruff check app tests
uv run pytest
```

```bash
pnpm lint
pnpm build
pnpm test
```

## 验证清单

1. 打开 http://localhost:8015/login 可以注册并登录。
2. 登录后进入工作台，刷新页面应仍保持登录。
3. 未登录访问 `/erp/dashboard` 会跳到登录页，成功后回到原地址。
4. 直接打开 http://localhost:8016 或 http://localhost:8016/dashboard ，子应用可独立运行。
5. http://localhost:8011/docs 可打开 Swagger。
6. `/api/v1/health` 与 `/api/v1/auth/me` 可用。
7. 未登录打开主应用时，Network 里 `/auth/refresh` 可能 401，这表示没有 Refresh Cookie，属于预期，不应弹窗。
8. 公钥走 `GET /api/crypto/public-key`，不要求登录。
9. ERP 侧栏由 `apps/erp/src/router/routes.ts` 生成。
10. 登录成功后 Network 里不应立刻再出现 `/auth/refresh`；刷新页面才应恢复会话。
11. 登录后若没有企业，会进入 `/workspaces/create`；只有一家有效企业会自动进入；多家则优先恢复 `localStorage` 中该用户上次选择，失效则进入 `/workspaces`。
12. `POST /api/v1/tenants` 可创建企业；`GET /api/v1/tenants` 只返回自己加入的企业。创建企业不需要 `X-Tenant-ID`。
13. 业务接口用请求头 `X-Tenant-ID`，服务端会校验成员关系。切换企业不会调用登录或 Refresh。
14. 离开 `/erp` 再进入应恢复上次 ERP 页面；在 ERP 内切换企业后，保活探测输入应被清空，且 Network 里后续请求的 `X-Tenant-ID` 变为新企业。

多租户说明见 `docs/multi-tenancy.md`。路由配置说明见 `docs/routing.md`。认证流程见 `docs/auth.md`。

## 浏览器进 debugger

业务错误会 `Promise.reject(ApiError)`。若一报错就停在 Sources 面板，检查 DevTools → Pause on exceptions，以及 Cursor/VS Code 调试器的 Caught Exceptions。代码里没有 `debugger`。

## 常见问题

**本机 8011 已被其他进程占用**

Neorvion 后端必须使用 8011。如果该端口已被占用，浏览器访问 `localhost:8011/docs` 会看到别的应用。请先结束占用进程，再启动本仓库后端：

```powershell
Get-NetTCPConnection -LocalPort 8011 | Select-Object OwningProcess,State
```

**子应用白屏**

- 确认 ERP 已启动在 8016。
- 确认 CORS 与 `server.origin` 仍为 `http://localhost:8016`。
- 确认入口调用了 `window.__WUJIE.mount()`。
- 无界依赖 iframe 沙箱。部分内嵌浏览器会拦截 iframe 的 `contentWindow`，请用系统 Chrome 打开 http://localhost:8015/erp。
- 子应用本身可用 http://localhost:8016 独立验证。

**MySQL / Redis 为 unavailable**

- 检查 `backend/.env` 账号是否与实际实例一致。FastAPI 只读取 `backend/.env`，仓库根目录 `.env` 给 Docker Compose 使用，二者可以不同。
- 业务库必须是 `neorvion_erp`，测试库是 `neorvion_erp_test`，不要复用其他项目数据库。
- 本机 3306/6379 可能已被其他服务占用，不要和 Docker 映射冲突。

**Docker 守护进程未启动**

- Compose 文件仍可使用，但需要先启动 Docker Desktop：
  `docker compose up -d mysql redis`
- Alembic 需要能连上 MySQL 后才能 `upgrade head`。M1 初始迁移为空，只打通命令链路。

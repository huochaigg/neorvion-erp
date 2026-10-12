# 本地 / 演示 Docker 部署

腾讯云第一次生产上线请看 **[`docs/deployment-production.md`](deployment-production.md)**，不要用本文件代替。

本文面向开发机 Docker Compose（`docker-compose.yml`）。不做 Kubernetes。

## 依赖

- Docker / Docker Compose
- 或：MySQL 8、Redis 7、Python 3.12、Node 22、Nginx、HTTPS 证书

## 公网原则

只开放 **80 / 443**。SSH 限制来源。MySQL、Redis、FastAPI 8011 **不对公网**。流量经 Nginx。

## Docker

```bash
docker compose up -d mysql redis backend worker
```

可选网关（把 `/api` 反代到 backend，`/` 指向本机 Shell）：

```bash
docker compose --profile gateway up -d nginx
```

当前 `docker-compose.yml` 仍映射 `8011:8011` 方便本地调试。生产应去掉该端口映射，只留 Nginx。

`backend` 启动时执行 `alembic upgrade head`，**不会**自动 `seed_demo`。

Worker 与 API 共用同一镜像，命令为 `python -m app.tasks.worker`。健康状态看 Redis 键 `erp:worker:heartbeat`，`GET /api/v1/health` 的 `worker` 字段。

## 环境变量

复制 `.env.example`。生产必须改：

| 变量 | 要求 |
| --- | --- |
| `APP_ENV` | `production`（关闭 debug 日志、收紧 CORS） |
| `SECRET_KEY` | 强随机，不要用示例值 |
| `REFRESH_COOKIE_SECURE` | HTTPS 下 true |
| `CORS_ORIGINS` | 精确前端源，不要 `*` |
| `MYSQL_*` / `REDIS_*` | 内网地址 |
| `RSA_*_PATH` | 私钥在宿主机或密钥系统，不打进镜像 |
| `DEMO_EMAIL` / `DEMO_PASSWORD` | 仅演示环境用平台 Secret，不要写进 README/Git |

生产 `Settings.is_production` 会强制 Cookie Secure。

## Nginx

仓库 `nginx/nginx.conf` 是本地 gateway 示例：`/api` → backend:8011，`/` → Shell。生产应：

- 监听 443，HTTP 跳转 HTTPS
- 静态资源 gzip + 长期缓存 hash 文件
- `/erp` 与 `/` 同源或按微前端实际入口
- 预留 `/agent/` 给未来 Copilot / SSE，不要再暴露新公网端口
- `client_max_body_size` 保持有上限（当前 20m）

## 迁移与 Seed

```bash
uv run alembic upgrade head
uv run python -m app.scripts.seed_permissions
# 仅开发/演示：DEMO_EMAIL + DEMO_PASSWORD 后
uv run python -m app.scripts.seed_demo
```

生产禁止启动时自动灌演示数据。

## 日志

进程 stdout。带 `request_id` / `tenant_id` / `user_id`。不要把 Token、密码、RSA 私钥打进日志。

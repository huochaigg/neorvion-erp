# 生产运维与排障

前提：第一次部署已按 `docs/deployment-production.md` 完成。下面命令默认【服务器 SSH / deploy】。

```bash
export NEORVION_ENV_FILE=/opt/neorvion/env/.env.production
alias dc='docker compose --env-file /opt/neorvion/env/.env.production -f /opt/neorvion/src/deploy/compose/docker-compose.production.yml'
```

## 日常

```bash
dc ps
dc logs -f erp-api
dc logs -f worker
dc logs --tail=100 mysql
docker stats
docker images
docker volume ls
docker volume inspect neorvion_mysql_data
docker network ls
dc exec mysql sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -e "SELECT 1"'
dc restart erp-api
dc restart worker
```

不要用宝塔 Docker GUI 当唯一手段。

**禁止日常**：`docker system prune -a`（会删掉回滚所需的旧镜像）。最多 `docker image prune -f` 清 dangling。

**【危险操作】** `docker compose down -v` 会删 Named Volume，MySQL/Redis/Postgres 数据没了。正常更新 **不要**带 `-v`。

## 日志

- FastAPI / Worker：`dc logs`
- 容器日志已轮转：max-size 20m × 5
- 宝塔 Nginx：网站 → 日志，或 `/www/wwwlogs/`
- 改 Nginx 后：`/www/server/nginx/sbin/nginx -t` 成功再 `-s reload`

## 磁盘

```bash
df -h
du -sh /opt/neorvion/backups /opt/neorvion/releases /var/lib/docker
docker system df
```

增长来源：数据库 volume、镜像、备份、日志、导出文件。

## 资源 / OOM

```bash
free -h
docker stats --no-stream
dmesg -T | tail -n 50
journalctl -k -n 50 --no-pager
dc ps
```

容器 `OOMKilled`：`docker inspect neorvion-erp-api --format '{{.State.OOMKilled}} {{.State.Status}}'`

长期内存 >80%：升级 2C4G，不要再加 Worker 数量。

## 502 Bad Gateway

1. `dc ps`（erp-api 是否 running / healthy）
2. `curl -sS http://127.0.0.1:8011/api/v1/health`
3. `dc logs --tail=150 erp-api`
4. 宝塔 error.log
5. Nginx 是否 `proxy_pass http://127.0.0.1:8011`（端口是 **8011**）

## 数据库连不上

- mysql 是否 healthy
- `.env.production` 的 `MYSQL_HOST=mysql`（容器内主机名，不是 127.0.0.1）
- 用户是 `neorvion` 不是 root
- 库名 `neorvion_erp`
- 是否在 `neorvion_internal` 网络：`docker network inspect neorvion_internal`

## Alembic

```bash
dc run --rm --no-deps erp-api uv run --no-dev alembic current
dc run --rm --no-deps erp-api uv run --no-dev alembic heads
dc run --rm --no-deps erp-api uv run --no-dev alembic history
```

多个 head：**不要**盲目 merge。先看是哪两次 migration 分叉，再决定。

失败则停止发布，保留旧容器。

## Redis

```bash
dc exec redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'
dc logs worker
```

任务状态在 MySQL `async_tasks`。Redis 只是队列。AOF 丢了可以重试任务，**不能**当库存真相。

## Postgres

```bash
dc exec postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT extname FROM pg_extension WHERE extname='"'"'vector'"'"';"'
```

Postgres 挂了 **不应**让 ERP `/health` 变失败。当前 health 只探 MySQL / Redis / Worker。

## 【危险操作】MySQL 恢复

会发生什么：当前 ERP 数据被备份文件覆盖。

1. `dc stop erp-api worker`
2. `ls /opt/neorvion/backups/mysql` 选文件
3. `gunzip -c /opt/neorvion/backups/mysql/neorvion-YYYYMMDD-HHMMSS.sql.gz | dc exec -T mysql sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"'`
4. `dc start erp-api worker`
5. `curl http://127.0.0.1:8011/api/v1/health`

不要让自动 Deploy 自己 restore。不要 `DROP DATABASE` 除非你明确知道。

## 应用回滚

```bash
export IMAGE_REPO=ghcr.io/YOUR_OWNER/neorvion-erp/erp-api
export ROLLBACK_SHA=上一个commit
/opt/neorvion/src/scripts/rollback-app.sh
```

不执行 `alembic downgrade`。若旧代码跑不了新表结构：用备份恢复，而不是 downgrade。

## 发布失败对照

| 阶段 | 先查 |
| --- | --- |
| CI | GitHub Actions 日志 |
| 镜像构建 | Dockerfile、uv.lock |
| GHCR | packages 权限、login |
| SSH | deploy 用户、密钥、安全组 22 |
| 备份 | mysql healthy、磁盘 |
| Migration | alembic current/heads |
| 容器起不来 | `dc logs`、OOM、RSA 文件是否 600 且已挂载 |
| Health | mysql/redis 字段、worker 心跳 |
| 前端白屏 | `VITE_ERP_ENTRY` 是否还是 localhost；`/erp/assets` 是否 200；Wujie 控制台 |
| 登录失败 | `/api/crypto/public-key`、RSA 挂载、Cookie Secure + HTTPS |

## 宝塔安全（上线后尽快做）

【宝塔网页】面板设置：

- 修改默认入口（安全入口）
- 强密码
- 绑定 IP / 授权 IP（只留你的公网 IP）
- 8888 在腾讯云安全组也限制来源

不要让全网扫描默认 8888 面板。

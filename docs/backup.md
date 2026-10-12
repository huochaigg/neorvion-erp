# 备份与恢复

生产机请用 `scripts/backup-mysql.sh`（以及可选的 `scripts/backup-postgres.sh`），步骤见 `docs/deployment-production.md` 与 `docs/server-operations.md`。

下面是开发机 / 通用说明。不是自动备份平台。

## MySQL

逻辑备份：

```bash
mysqldump -u neorvion -p --single-transaction --routines --triggers neorvion_erp > backup.sql
```

Docker：

```bash
docker exec neorvion-mysql mysqldump -uneorvion -pneorvion_dev --single-transaction neorvion_erp > backup.sql
```

恢复前先确认目标库，避免覆盖生产。

## Redis

当前用途：任务队列、Refresh 会话、RSA challenge、Worker 心跳。Compose 已开 AOF。

- Refresh / challenge 丢失：用户重新登录即可
- 队列中的 `task_id` 丢失：任务表仍在 MySQL，可按状态人工重试
- **不要**把库存数量当作 Redis 数据来备份

## 文件

- `backend/var/exports`：异步导出文件，可随磁盘备份
- RSA 私钥：必须单独保管，丢失则无法解密进行中的登录 challenge；轮换 key_id 比找回旧私钥更现实

## 环境变量

备份 `.env` 到密钥管理系统，不要提交 Git。包含 `SECRET_KEY`、DB 密码、RSA 路径。

## 恢复顺序

1. 启动 MySQL / Redis
2. 恢复数据库
3. `alembic upgrade head`（若备份落后于代码）
4. 放置 RSA 私钥并核对路径
5. 启动 API 与 Worker
6. 用 `/api/v1/health` 确认 mysql / redis / worker

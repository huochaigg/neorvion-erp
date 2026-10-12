# 异步任务中心

长任务（例如报表导出）不能放在普通 HTTP 请求里同步跑完：超时、网关断开、进程重启都会让调用方以为失败而服务器仍在写。

FastAPI `BackgroundTasks` 也不适合关键持久任务：它活在当前进程里，重启即丢。

## V14 选择

评估后使用 **MySQL 任务表 + Redis List 队列 + 独立 Worker**（`uv run python -m app.tasks.worker`）。

- 已有 `redis-py`，SQLAlchemy 为同步 Session。
- Celery 对本阶段过重（额外部署）。
- ARQ 是 asyncio，和现有 Session 不匹配。
- Dramatiq 可用，但会再引入一套框架；任务状态仍要以 MySQL 为准。

Redis 只投递 `task_id`。状态、进度、结果、错误以 `async_tasks` 为准。入队失败则保持 `PENDING`，可人工重新入队。

## 状态机

`PENDING → QUEUED → RUNNING → SUCCESS | FAILED`  
`PENDING / QUEUED` 可 `CANCELLED`。不假装中断正在运行的 Python 函数。

`FAILED` 且 `retry_count < max_retries` 可 Retry：锁行后仍走同一 `task_id`，不另开一条无关任务。两个管理员同时 Retry，只有一次能改状态。

`idempotency_key` 已预留，V14 不强制。

## 进度与日志

`progress` 0–100，按阶段更新（20/60/90/100），不要每行 UPDATE。`async_task_logs` 保存用户可理解的步骤，不含完整 traceback。`error_message` 脱敏。

## 报表导出

`POST /api/v1/analytics/*/export-tasks` 创建 `REPORT_EXPORT`。Worker 生成 CSV 到受控目录，下载走 `GET /tasks/{task_id}/download`（校验租户、SUCCESS、任务类型）。同步 CSV 接口仍保留。

未来 Agent 可复用同一套 `task_id / status / progress / result / logs`。V14 不开发 Agent。

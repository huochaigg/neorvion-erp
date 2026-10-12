# 事件与任务

## Event 和 OperationLog 不一样

Event：领域里发生了什么（订单已确认），给后续消费者 / Outbox。OperationLog：谁在哪个请求里点了什么，给审计。

## 为什么需要 Outbox

事件必须和库存同一事务写入。先 commit 业务再调 Redis/MQ 会丢事件。先发消息再 commit 会发假消息。Outbox 行与业务同事务，Worker 再投递。

## 为什么关键 Task 不用 BackgroundTasks

进程一关请求级后台任务就丢。报表导出、Outbox 投递需要可重试、可查询的 `async_tasks` + 独立 Worker。

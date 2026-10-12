# 事件中心

`SystemEvent` 记录「系统发生了什么业务事实」，存在 MySQL `system_events`，同时承担第一版 Outbox。

它不是操作日志：操作日志回答「谁点了什么」。它也不是通知中心：通知要投递给某个人看，V14 不做。

## 为什么用 Outbox

订单确认已经预占库存并改了状态。如果主事务 commit 后再 `Redis.publish`，发布失败时业务已成功、下游永远看不到事件，状态不明确。

V14：`event_publisher.record()` 与主业务写在同一事务。业务成功，事件行一定存在（`status=PENDING`）。Worker 再消费。Redis 只是唤醒，失败不回滚业务。

## 字段

- `event_id`：全局唯一，`evt_` + UUID，供去重和跨系统追踪。
- `event_type`：稳定枚举，见下文。不要把所有 CRUD 都变成事件。
- `event_source`：`ERP` / `SYSTEM` / `TASK`。
- `aggregate_type` / `aggregate_id`：主业务对象，例如一张销售订单。
- `reference_type` / `reference_id`：补充关联，语义与库存流水一致。
- `payload`：必要快照 JSON。禁止 password / token / Authorization。
- `status`：Outbox 生命周期 `PENDING → PROCESSING → PROCESSED / FAILED`。

## 第一批 event_type

销售：`SALES_ORDER_CREATED` / `CONFIRMED` / `CANCELLED` / `COMPLETED`  
采购：`PURCHASE_ORDER_CREATED` / `APPROVED`、`PURCHASE_RECEIPT_CONFIRMED`  
履约：`OUTBOUND_CONFIRMED`、`SHIPMENT_SHIPPED` / `DELIVERED`  
库存：`INVENTORY_ADJUSTED`、`INVENTORY_LOW`、`STOCK_TRANSFER_COMPLETED`  
售后：`AFTER_SALE_CREATED` / `APPROVED` / `COMPLETED`、`REFUND_SUCCESS`  
采购退货：`PURCHASE_RETURN_COMPLETED`  
任务：`TASK_COMPLETED` / `TASK_FAILED`

## Consumer

Worker 用 `SELECT ... FOR UPDATE SKIP LOCKED` 领取 PENDING，最大重试 3 次。第一版只标记 `PROCESSED`，验证 Outbox 生命周期。按 `event_id` 幂等。

未来 Agent 应调用事件查询 API，不要直接当 Event Consumer 去拼 SQL。V14 不调用大模型。

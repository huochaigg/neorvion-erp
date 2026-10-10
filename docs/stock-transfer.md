# 库存调拨

当前里程碑 **V10**。调拨是同一租户两个启用仓库之间移动库存。不支持跨租户；跨公司应走采购或销售。

## 为什么调出和调入不是同一个动作

深圳仓今天发货，广州仓可能明天才收到。如果同时 `A -20 / B +20`，广州仓账面会提前出现还没到的货。所以拆成：

```text
DRAFT → PENDING_OUTBOUND → IN_TRANSIT → COMPLETED
DRAFT / PENDING_OUTBOUND → CANCELLED
```

- 确认调出：源仓 `quantity` 减少，写 `TRANSFER_OUT`。目标仓不变。
- 在途：货物已离开源仓，尚未进入目标仓。第一版不建独立 `inventory_in_transit` 表，用 `IN_TRANSIT` + `outbound_quantity` 表示。
- 确认调入：目标仓 `quantity` 增加，写 `TRANSFER_IN`。`received_quantity` 默认等于 `outbound_quantity`，暂不处理运输损耗。

在途后不能普通取消。货物已从源仓扣减，撤回应创建反向调拨。

## 为什么只能动 available inventory

账面 100、预占 80、可用 20。那 80 已经卖给销售订单。最多只能调 20。调拨不能释放源仓预占，也不能给目标仓增加预占。

确认调出使用 `InventoryService.deduct_available_within_transaction`：条件 UPDATE 要求 `quantity - reserved >= 调拨数量`。

## 目标仓没有该 SKU

广州仓第一次调入 SKU-A 时，复用收货入库的安全创建：先插入 `quantity=0`，撞上 `UNIQUE(tenant_id, warehouse_id, sku_id)` 只回滚保存点，再增加数量。

## 事务、并发、幂等

调出：调拨单、明细、源仓库存、`TRANSFER_OUT` 流水同一事务。任一 SKU 不足整单回滚。

调入：调拨单、明细、目标仓库存、`TRANSFER_IN` 流水同一事务。

重复确认调出 → `STOCK_TRANSFER_ALREADY_OUTBOUND`。重复确认调入 → `STOCK_TRANSFER_ALREADY_RECEIVED`。两张调拨单同时抢同一 SKU 时，条件 UPDATE 保证不能超扣，也不能让 `quantity < reserved`。

明细按 `sku_id` 排序后再处理库存，降低死锁概率。Repository 不自行 commit。

## 单号与权限

单号：`TR` + 年份 + 6 位 id。调出仓不能等于调入仓。草稿允许库存不足，真正校验在确认调出。

权限：`stock_transfer:read/create/update/submit/outbound/receive/cancel`。调出和调入单独授权。

## API

- `GET/POST /api/v1/stock-transfers`
- `GET/PATCH /api/v1/stock-transfers/{id}`
- `POST /api/v1/stock-transfers/{id}/submit|confirm-outbound|confirm-receive|cancel`

不要开放 `PATCH status`。

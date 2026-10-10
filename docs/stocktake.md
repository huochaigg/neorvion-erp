# 库存盘点

当前里程碑 **V10**。盘点比较的是创建任务时的账面快照和仓库实盘数量。确认后按差异调整当前 `Inventory.quantity`，并追加 `STOCKTAKE_ADJUSTMENT` 流水。

## 账面、实盘、盘盈、盘亏

| 概念 | 含义 |
| --- | --- |
| 账面库存 | 系统里该仓库 + SKU 的 `Inventory.quantity`。创建盘点时写入 `system_quantity` |
| 账面预占 | 当时的 `reserved_quantity` 快照 |
| 实盘数量 | 仓库人员实际盘到的数量 `counted_quantity` |
| 差异 | `counted_quantity - system_quantity` |
| 盘盈 | 差异 > 0 |
| 盘亏 | 差异 < 0 |
| 一致 | 差异 = 0 |

不能只在页面上实时读当前 `Inventory.quantity`。10:00 创建时账面 100，10:05 采购入库变成 120，10:10 实盘 100。如果用实时账面计算，会得到错误的 -20。所以明细必须保存 `system_quantity`。

## 为什么确认用差异，而不是覆盖成实盘数

确认时库存可能已经变了。创建快照 100，期间入库 +20，当前 120，实盘 98，差异 -2。

正确结果：`120 + (-2) = 118`。

如果执行 `Inventory.quantity = 98`，会把正常入库的 20 件也抹掉。因此 `confirm_stocktake()` 只把 `difference_quantity` 加到**当前**账面。

## 为什么盘点期间不能一直锁库存

盘点可能持续几小时。`SELECT ... FOR UPDATE` 只能用于短事务。创建任务时只读快照，不加行锁等人填数。确认才锁盘点单和对应库存行，同一事务改库存、写流水、改状态。

## 状态

```text
COUNTING → PENDING_CONFIRMATION → CONFIRMED
COUNTING / PENDING_CONFIRMATION → CANCELLED
```

本版创建后直接进入 `COUNTING`，不单独做 start。已确认不能取消。

范围：`ALL`（整仓）或 `SELECTED_SKU`。不做库区、库位、批次盘点。

## 确认时不能破坏预占

调整后必须 `new_quantity >= reserved_quantity`。盘点不能自行释放销售订单预占。否则返回 `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`，整单回滚。

## 单号与权限

单号：`ST` + 年份 + 6 位 id，例如 `ST2026000001`。不用 `MAX+1`。租户内唯一。

权限：`stocktake:read/create/update/submit/confirm/cancel`。确认会改库存，单独授权。

## API

- `GET/POST /api/v1/stocktakes`
- `GET/PATCH /api/v1/stocktakes/{id}`
- `PUT /api/v1/stocktakes/{id}/items` 批量保存实盘
- `PATCH /api/v1/stocktakes/{id}/items/{item_id}`
- `POST /api/v1/stocktakes/{id}/submit|confirm|cancel`

保存实盘不改库存。重复确认返回 `STOCKTAKE_ALREADY_CONFIRMED`。

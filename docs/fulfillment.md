# 履约：采购收货与销售出库

当前里程碑 **V8**。采购单和销售订单描述计划，收货单和出库单描述仓库实际做了什么。库存数字只在确认收货、确认出库时变化。

## 四种单据

| 单据 | 回答的问题 | 会不会改库存 |
| --- | --- | --- |
| 采购单 PurchaseOrder | 计划向供应商买什么 | 不会。审核通过只到待收货 |
| 收货单 PurchaseReceipt | 这次仓库实际收到多少 | 草稿不会。确认收货才增加 `quantity` |
| 销售订单 SalesOrder | 卖给客户什么，以及已经预占多少 | 确认订单只增加预占。正式扣减发生在出库 |
| 出库单 OutboundOrder | 这次仓库实际发出多少 | 拣货不会。确认出库才同时减少 `quantity` 和 `reserved_quantity` |

不能在前端直接改 `PurchaseOrderItem.received_quantity`。也不能用 `SalesOrder.status` 代替仓库动作。计划和实物分开，才能做部分收货、部分出库，以及失败时整单回滚。

## 采购链路

```text
采购单草稿 → 提交审核 → 待收货 WAITING_RECEIPT
  → 创建收货草稿（不改库存、不改已收数量）
  → 确认收货
  → Inventory.quantity 增加，reserved 不变
  → INBOUND 流水
  → 部分收货 PARTIALLY_RECEIVED，或一次收完 RECEIVED
```

只有 `WAITING_RECEIPT` 和 `PARTIALLY_RECEIVED` 能创建收货单。仓库必须是采购单上的仓库，不能在收货时换成别的仓。

收货单状态：`DRAFT` 可改数量、可作废；`CONFIRMED` 已入库，不能再改、不能取消（取消入库要等以后的采购退货）；`CANCELLED` 作废，不能再确认。

单号：flush 拿到 id 后写成 `PR` + 年份 + 6 位 id，例如 `PR2026000001`。不用 `MAX+1`。租户内唯一。

### 部分收货

采购 SKU-A × 100。第一次实收 60：明细 `received_quantity` 从 0 变成 60，采购单进入 `PARTIALLY_RECEIVED`。第二次再收 40：`received_quantity = 100`，采购单进入 `RECEIVED`。一次收满则从 `WAITING_RECEIPT` 直接到 `RECEIVED`。

累计已收不能超过采购数量。两张草稿各收 60、同时确认时，会锁采购明细重新读已收数量，只有一张能成功。

### 入库时库存怎么变

当前实际 100、预占 30、可用 70。采购入库 50：

```text
quantity 100 → 150
reserved 30 → 30
available 70 → 120
```

入库的是新到的货，不是把已经卖出预占的货还回去，所以 `reserved_quantity` 不动。

流水：`type=INBOUND`，`change_quantity=+50`，`reference_type=PURCHASE_RECEIPT`，`reference_id=收货单 id`。

仓库 + SKU 还没有库存行时，确认收货会创建 `quantity=实收`、`reserved=0`，并写同一条 INBOUND。创建使用保存点：先插入，若撞上 `UNIQUE(tenant_id, warehouse_id, sku_id)` 就回滚保存点，再走增加数量。不能只靠「先 SELECT 没有再 INSERT」，两个请求会同时认为不存在。

重复确认已入库的收货单返回 `PURCHASE_RECEIPT_ALREADY_CONFIRMED`，库存只加一次。

## 销售链路

```text
销售订单草稿 → 提交 → 确认
  → reserved 增加，quantity 不变
  → 待出库 WAITING_OUTBOUND
  → 同一事务自动生成第一张出库单（计划数量 = 当前预占）
  → 拣货（不改库存）
  → 确认出库
  → quantity 和 reserved 同时减少
  → OUTBOUND 流水
  → 部分出库 PARTIALLY_SHIPPED，或一次出完 SHIPPED
```

一张销售订单可以有多张出库单。历史数据里已经是待出库、但没有出库单的订单，用 `POST /api/v1/outbound-orders` 补一张，迁移脚本不批量造业务单据。

确认订单时自动生成第一张，是因为仓库、SKU、预占数量这时已经确定。补单和「继续出库」走同一个创建接口，不另做一套。

出库单状态：`PENDING_PICKING` → `PICKED` → `CONFIRMED`。待拣货和已拣货都可以取消，因为库存仍只是预占。已确认不能取消，以后走销售退货。

单号：`OUT` + 年份 + 6 位 id，例如 `OUT2026000001`。

未确认的出库单会占用计划数量。同一订单剩余可分配 = 明细 `reserved_quantity` − 未完成出库单的 `planned_quantity`。第一张如果计划了全部预占，必须等它确认或取消后，才能为剩余量再开一张。

### 为什么拣货不扣库存

拣货只记录仓库把货拿到了发货区，货还在账上。同一次出库可以分多次拣：计划 5 件时先拣 3、再拣 2，明细上的 `picked_quantity` 仍是累计 5，另外每次都会追加一条拣货记录，记下本次数量、拣前累计、拣后累计、时间和操作人。订单详情和出库单详情都展示这些记录。未点「完成拣货」且还没拣满时，出库单保持待拣货。拣满或完成拣货后才变成已拣货。确认出库仍按累计 `picked_quantity` 扣库存，不按单条记录再扣一次。

确认出库使用拣货数量作为 `outbound_quantity`。拣少了的部分仍留在销售订单的预占上，确认后可以再开出库单。

### 出库时数量为什么这样变

出库前：实际 100、预占 10、可用 90。本次发出此前已经预占的 6 件：

```text
quantity 100 → 94
reserved 10 → 4
available 90 → 90
```

可用量不变，是因为这 6 件在确认订单时已经从可用量里划走了。现在只是从「还在仓库、但已被订单占用」变成「正式离开仓库」。如果出库只减 `quantity`、不减 `reserved`，预占会大于实际库存。

流水：`type=OUTBOUND`，`change_quantity=-6`，同时记下变化前后的实际和预占。`reference_type=OUTBOUND_ORDER`，`reference_id=出库单 id`。

重复确认返回 `OUTBOUND_ALREADY_CONFIRMED`，不能再扣一次。

### 订单明细的三个数量

| 字段 | 含义 |
| --- | --- |
| `quantity` | 订单要卖的数量 |
| `reserved_quantity` | 还没出库、但已经预占的数量 |
| `shipped_quantity` | 累计已经正式出库的数量 |

V7 的约束 `shipped_quantity <= reserved_quantity` 在出库后不成立。例如买 10、出 6 之后是预占 4、已出库 6。

V8 的长期约束：

```text
reserved_quantity >= 0
shipped_quantity >= 0
reserved_quantity + shipped_quantity <= quantity
```

订单全部预占且尚未出库时，`reserved + shipped = quantity`。出库 6 件后：预占 4、已出库 6，两者之和仍是 10。

一旦有任何 `shipped_quantity > 0`，不能再取消整张销售订单。待出库、且尚未出库时取消，会在同一事务里作废未完成出库单并释放预占。

## 状态机

采购单在 V6 之后增加：

```text
WAITING_RECEIPT → PARTIALLY_RECEIVED → RECEIVED
WAITING_RECEIPT → RECEIVED
```

销售订单在 V7 之后增加：

```text
WAITING_OUTBOUND → PARTIALLY_SHIPPED → SHIPPED
WAITING_OUTBOUND → SHIPPED
```

`PARTIALLY_SHIPPED` 和 `SHIPPED` 不能取消。

## 事务、锁、幂等

`confirm_receipt` 和 `confirm_outbound` 都在一个数据库事务里做完。任一步失败，单据状态和库存一起回滚。确认失败时收货单仍是草稿，出库单仍是已拣货，不会出现「单据已确认但库存没变」。

加锁顺序固定，避免死锁：

1. 先锁履约单据（收货单或出库单）
2. 再锁来源单据（采购单或销售订单）
3. 明细和库存按 `sku_id` 升序处理

不能一张事务先锁 SKU-A 再锁 SKU-B，另一张反过来。

库存规则仍在 `InventoryService`：

- `inbound_within_transaction`：增加 `quantity`，不改预占，写 INBOUND。不自己 commit。
- `deduct_within_transaction`：复用 V5 的「实际和预占都够才减」条件 UPDATE，写 OUTBOUND。不自己 commit。

业务接口使用 `purchase:receipt:confirm` 和 `outbound:confirm`。不要求用户再同时拥有 `inventory:inbound` / `inventory:outbound`。底层库存权限保留，给库存调整等原有入口。

条件 UPDATE 之后会 `expire_all()`，所以确认流程先把计划数量复制出来，做完库存，再重新锁定单据写状态。

## API

采购收货：

- `GET/POST /api/v1/purchase-receipts`
- `GET/PATCH /api/v1/purchase-receipts/{id}`
- `POST /api/v1/purchase-receipts/{id}/confirm`
- `POST /api/v1/purchase-receipts/{id}/cancel`

销售出库：

- `GET/POST /api/v1/outbound-orders`
- `GET /api/v1/outbound-orders/{id}`
- `POST /api/v1/outbound-orders/{id}/pick`
- `POST /api/v1/outbound-orders/{id}/confirm`
- `POST /api/v1/outbound-orders/{id}/cancel`

创建入口只有上面的 POST。不另做 `/purchase-orders/{id}/receipts` 或 `/sales-orders/{id}/outbound`。

## 本版不做

物流公司、运单、轨迹、签收、采购退货、销售退货、退款、售后、财务、真实平台同步。

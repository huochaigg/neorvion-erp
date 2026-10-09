# 物流与发货

当前里程碑 **V9**。销售订单、出库单、物流单是三张不同的单据。确认发货 **不再** 修改库存。

## 三种单据

| 单据 | 回答的问题 | 会不会改库存 |
| --- | --- | --- |
| 销售订单 SalesOrder | 客户买了什么 | 确认时增加预占。出库时才扣实际库存 |
| 出库单 OutboundOrder | 仓库实际拣货、出库了什么 | 确认出库时 `quantity` 和 `reserved` 一起减少 |
| 物流单 Shipment | 这次交给承运商发走了什么 | 不会。货在出库时已经离开账面 |

16:00 仓库确认出库，17:30 快递员揽收，是两个时间点。`confirm_outbound()` 不能代表物流已发货。

长期模型：

```text
SalesOrder 1 → N OutboundOrder
SalesOrder 1 → N Shipment
Shipment 可以关联一个或多个 OutboundOrder
```

V9 第一版限制：一张物流单对应一张出库单。同一张出库单可以拆成多张物流单（部分发货）。以后可以扩展合并发货。

## 销售链路

```text
创建销售订单 → 提交 → 确认预占
  → 创建出库 → 拣货 → 正式出库（这里扣库存）
  → 创建 Shipment 草稿（不改库存、不推进发货状态）
  → 填写物流商 / 运单号
  → 确认发货（累加 shipped_quantity，不改 Inventory）
  → 手工追加物流轨迹
  → 确认签收
  → 全部签收后 SalesOrder COMPLETED
```

## 数量字段

`SalesOrderItem`：

| 字段 | 含义 |
| --- | --- |
| `quantity` | 下单数量 |
| `reserved_quantity` | 当前已预占、尚未正式出库 |
| `outbound_quantity` | 累计已从库存正式出库 |
| `shipped_quantity` | 累计已交给承运商 |

约束：

```text
reserved_quantity >= 0
outbound_quantity >= 0
shipped_quantity >= 0
reserved_quantity + outbound_quantity <= quantity
shipped_quantity <= outbound_quantity
```

V8 曾把 `shipped_quantity` 当成已出库数量，状态 `PARTIALLY_SHIPPED` / `SHIPPED` 表示仓库出库。V9 迁移：旧值拷到 `outbound_quantity`，`shipped_quantity` 清零；历史状态改成 `PARTIALLY_OUTBOUND` / `OUTBOUNDED`。V9 的 `PARTIALLY_SHIPPED` / `SHIPPED` 只表示物流。

## 为什么确认发货不再扣库存

订单确认：增加 `reserved`。

出库确认：`quantity` 减少，`reserved` 减少。

物流发货：货已经离开仓库，只是交给快递员。如果这里再减一次 `quantity`，账面会少一倍。

创建草稿、确认发货、追加轨迹、签收，都不调用 `InventoryService`。

## 物流商 Carrier

基础资料，不调用顺丰 / DHL / UPS API。

类型：`DOMESTIC_EXPRESS` / `INTERNATIONAL_EXPRESS` / `FREIGHT_FORWARDER` / `PLATFORM_LOGISTICS` / `OTHER`。

编码不填时 flush 拿到 id，写成 `CAR` + 10 位数字。不用 `MAX+1`。租户内唯一。创建后只读。

未被物流单引用可删除。已经产生物流单只能停用。停用后不能新建或确认物流单，历史单据仍显示当时的物流商名称。

## Shipment

单号：`SHP` + 年份 + 6 位 id。租户内唯一。

`tracking_no` 是承运商运单号。草稿可空，确认发货前必须有。唯一约束是 `(tenant_id, carrier_id, tracking_no)`，因为不同公司可能出现相同格式号码。MySQL 把多个 NULL 视为互不相等，多张草稿可以暂时不填运单号。

状态：

| 状态 | 中文 |
| --- | --- |
| `DRAFT` | 草稿，可改物流商、运单号、数量 |
| `SHIPPED` | 已发货 |
| `IN_TRANSIT` | 运输中 |
| `DELIVERED` | 已签收 |
| `CANCELLED` | 已取消，仅发货前允许 |

已发货后不能改承运商、运单号、数量，也不能取消。撤回以后走异常物流 / 退货。

## ShipmentItem

一张出库明细可以拆成多个包裹。例如出库 SKU-A × 10，Shipment A 发 6，Shipment B 发 4。

`quantity > 0`。同一出库明细上所有未取消物流单的数量合计，不能超过 `outbound_quantity`。创建时草稿也占用剩余可发，避免把 10 件计划成两张各 6 的草稿。确认时重新统计已经正式发货的数量，防止并发超发。

## confirm_shipment()

1. `SELECT FOR UPDATE` 锁物流单。
2. 必须仍是 `DRAFT`。重复确认返回 `SHIPMENT_ALREADY_CONFIRMED`，不再累加 `shipped_quantity`。
3. 必须有运单号，承运商必须启用。
4. 至少一条明细。
5. 锁出库明细，按 `sku_id` 升序，避免和别的物流单交叉加锁。
6. 重新计算已 `SHIPPED` / `IN_TRANSIT` / `DELIVERED` 的数量，本次不能超过剩余。
7. 增加 `SalesOrderItem.shipped_quantity`。
8. 物流单变成 `SHIPPED`，记下 `shipped_at` / `shipped_by`。
9. 按数量更新销售订单发货状态。一次 commit。不改库存。

部分发货：订单进入 `PARTIALLY_SHIPPED`。全部交给承运商：`SHIPPED`。

## 轨迹与签收

轨迹只追加，普通用户不能改历史事件。错误时再写一条纠正事件。

只有 `SHIPPED` / `IN_TRANSIT` 可以添加轨迹。加入揽收 / 在途 / 到达转运中心 / 派送中后，物流单可以从 `SHIPPED` 变成 `IN_TRANSIT`。签收不要走轨迹接口，走 `POST /shipments/{id}/deliver`。

签收：锁物流单，写成 `DELIVERED`，自动追加一条签收轨迹。整张物流单签收，不做某个 SKU 部分签收。

销售订单 `COMPLETED` 只能由系统根据履约结果决定，前端不能 `PATCH status = COMPLETED`。必须：所有购买数量都已出库、都已发货，并且所有正式物流单都已签收。两张物流单只签收一张时，订单仍是部分发货或已发货。

## 并发与幂等

同一张物流单两个请求同时确认：只能成功一次。靠物流单行锁和确认前再次检查状态。

两张物流单竞争同一条出库明细：创建时草稿占用剩余；确认时按 `sku_id` 升序锁出库明细，再算已发数量。不能把出库 10 发成 12。

失败则整单 rollback。草稿仍是草稿，`shipped_quantity` 不增加。

## 本版不做

真实承运商 API、电子面单、自动拉轨迹、Amazon / Shopify 发货回传、运费结算、退货物流、售后退款。

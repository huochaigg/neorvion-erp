# 物流发货与库存盘点

物流单回答「货是否已经交给承运商」。盘点单回答「账面和实盘差多少、确认时怎么改当前库存」。两者都会出现 `IN_TRANSIT`、`DRAFT`、`confirm` 之类容易撞车的词，但库存效果完全不同。

本文转写 `docs/shipping.md`、`docs/stocktake.md` 以及对应 Model / Service / 测试，不接入真实承运商 API，也不把盘点做成 WMS 库位盘点。

## 出库已经离开账面，发货只是交给承运商

16:00 仓库确认出库，17:30 快递员揽收，是两个时间点。`confirm_outbound()` 不能代表物流已发货。确认发货不再调用 `InventoryService`。

| 单据 | 回答的问题 | 库存 |
| --- | --- | --- |
| 销售订单 | 客户买了什么、是否已预占 | 确认时增加预占；出库时才扣实际库存 |
| 出库单 | 仓库实际拣了、出了什么 | 拣货不改；确认出库同时减 `quantity` 和 `reserved_quantity` |
| 物流单 | 这次交给承运商发走了什么 | 不改。货在出库时已经离开账面 |

V9 第一版：一张物流单对应一张出库单。同一张出库单可以拆成多张物流单（部分发货）。以后才考虑合并多张出库到一张物流单。

销售链路在出库之后：

```text
创建 Shipment 草稿（不改库存、不推进销售发货状态）
  → 填写物流商 / 运单号
  → 确认发货（累加 shipped_quantity，不改 Inventory）
  → 手工追加物流轨迹
  → 确认签收
  → 全部签收后 SalesOrder COMPLETED
```

## 物流单状态与轨迹

`ShipmentStatus`：

| 状态 | 英文标识 | 能否改承运商 / 运单号 / 数量 | 库存 |
| --- | --- | --- | --- |
| 草稿 | `DRAFT` | 可以 | 不改 |
| 已发货 | `SHIPPED` | 不能 | 不改 |
| 运输中 | `IN_TRANSIT` | 不能 | 不改 |
| 已签收 | `DELIVERED` | 不能 | 不改 |
| 已取消 | `CANCELLED` | 仅发货前允许 | 不改 |

物流单号：`SHP` + 年份 + 6 位 id，例如 `SHP2026000001`。租户内唯一。这不是出库单的 `OUT` 前缀，也不是调拨单的 `TR`。

`tracking_no` 是承运商运单号。草稿可空，确认发货前必须有。唯一约束是 `(tenant_id, carrier_id, tracking_no)`。MySQL 把多个 NULL 视为互不相等，多张草稿可以暂时不填运单号。

`TrackingEventStatus`：`PICKED_UP` / `IN_TRANSIT` / `ARRIVED_AT_HUB` / `OUT_FOR_DELIVERY` / `DELIVERED` / `EXCEPTION` / `OTHER`。轨迹只追加。只有 `SHIPPED` / `IN_TRANSIT` 可以添加轨迹。签收不要走轨迹接口，走 `POST /shipments/{id}/deliver`。

物流单上的 `IN_TRANSIT` 表示包裹在承运商手里。调拨单上的 `IN_TRANSIT` 表示货已离开源仓、尚未进入目标仓，源仓 `quantity` 已经减少。两个英文标识相同，一个不改库存，一个已经改了源仓库存。

## 确认发货不扣库存

`confirm_shipment()` 会：

1. `SELECT FOR UPDATE` 锁物流单，必须仍是 `DRAFT`。重复确认返回 `SHIPMENT_ALREADY_CONFIRMED`，不再累加 `shipped_quantity`。
2. 必须有运单号，承运商必须启用。
3. 锁出库明细，按 `sku_id` 升序。
4. 重新计算已 `SHIPPED` / `IN_TRANSIT` / `DELIVERED` 的数量，本次不能超过剩余已出库数量。
5. 增加 `SalesOrderItem.shipped_quantity`。
6. 物流单变成 `SHIPPED`。按数量更新销售订单为 `PARTIALLY_SHIPPED` 或 `SHIPPED`。一次 commit。

超额时 `error` 为 `SHIPMENT_EXCEEDS_OUTBOUND`。测试 `test_shipping.py` 断言该码。它不是 `OUTBOUND_EXCEEDS_RESERVED`（出库超过订单预占），也不是 `OUTBOUND_PICK_EXCEEDS_PLAN`（拣货超过本张出库单计划）。

创建草稿时草稿数量也占用剩余可发，避免把出库 10 件计划成两张各 6 的草稿。失败则整单 rollback，草稿仍是草稿。

权限：`shipment:read/create/update/confirm/tracking:update/deliver/cancel`。物流商是独立资源 `carrier:*`。

## 物流商 Carrier

基础资料，不调用顺丰 / DHL / UPS API。类型：`DOMESTIC_EXPRESS` / `INTERNATIONAL_EXPRESS` / `FREIGHT_FORWARDER` / `PLATFORM_LOGISTICS` / `OTHER`。

编码不填时 flush 拿到 id，写成 `CAR` + 10 位数字。创建后只读。未被物流单引用可删除。已经产生物流单只能停用。停用后不能新建或确认物流单，历史单据仍显示当时的物流商名称。

承运商状态或类型不合法时，Carrier 服务使用 HTTP 业务码 `40097`。销售、采购、调拨、盘点、售后在仓库未启用时也会返回 `40097`，销售路径还会带 `data.error = WAREHOUSE_DISABLED`。同一数字码不是同一业务结论，检索必须连错误数据和中文消息一起看。

本版不做：真实承运商 API、电子面单、自动拉轨迹、平台发货回传、运费结算、退货物流。

## 盘点比较的是快照，不是实时账面

盘点任务创建时把当时的 `Inventory.quantity` 写入明细 `system_quantity`，把当时的预占写入账面预占快照。仓库人员填写 `counted_quantity`。差异：

```text
difference_quantity = counted_quantity - system_quantity
```

不能只在页面上实时读当前 `Inventory.quantity`。10:00 创建时账面 100，10:05 采购入库变成 120，10:10 实盘 100。如果用实时账面计算，会得到错误的 -20。

## 确认时把差异加到当前账面

确认时库存可能已经变了。创建快照 100，期间入库 +20，当前 120，实盘 98，差异 -2。

正确结果：`120 + (-2) = 118`。

如果执行 `Inventory.quantity = 98`，会把正常入库的 20 件也抹掉。因此 `confirm_stocktake()` 只把 `difference_quantity` 加到**当前**账面，流水类型 `STOCKTAKE_ADJUSTMENT`。

盘点期间不锁库存行。盘点可能持续几小时，`SELECT ... FOR UPDATE` 只能用于短事务。确认才锁盘点单和对应库存行，同一事务改库存、写流水、改状态。保存实盘不改库存。

## 盘点状态机

`StocktakeOrderStatus`：

```text
COUNTING → PENDING_CONFIRMATION → CONFIRMED
COUNTING / PENDING_CONFIRMATION → CANCELLED
```

本版创建后直接进入 `COUNTING`。枚举里保留 `DRAFT`，注释写明留给以后「先建任务再开始」。当前创建接口不要把它理解成销售订单那种可编辑、未预占的草稿。

已确认不能取消。重复确认返回 `STOCKTAKE_ALREADY_CONFIRMED`。

范围：`ALL`（整仓）或 `SELECTED_SKU`。不做库区、库位、批次盘点。单号：`ST` + 年份 + 6 位 id。权限：`stocktake:read/create/update/submit/confirm/cancel`。

## 盘点不能破坏预占

调整后必须 `new_quantity >= reserved_quantity`。账面 100、预占 80、实盘 70：差异会把实际调到低于预占，确认失败。错误码是 `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`。测试 `test_stocktake.py` 断言该码。

盘点不能悄悄调用销售订单的释放路径。释放超额是另一个码 `INSUFFICIENT_RESERVED_INVENTORY`。出库超额是 `OUTBOUND_EXCEEDS_RESERVED`。三个码都和「预占」有关，路径不同。

停用仓库不能新建或确认盘点，业务码 `40097`，中文「只能对启用中的仓库做盘点」。

## 物流 IN_TRANSIT 和调拨 IN_TRANSIT

| 对象 | 状态 | 到达该状态时库存 |
| --- | --- | --- |
| 物流单 | `IN_TRANSIT` | 出库时已经扣过；轨迹阶段不再改 |
| 调拨单 | `IN_TRANSIT` | 源仓 `quantity` 已减少，目标仓尚未增加 |

问「IN_TRANSIT 会不会改库存」时，必须指定单据。单靠英文标识不够。

问「DRAFT 能不能改数量」时：物流草稿可以改发货数量；盘点枚举虽有 `DRAFT`，本版任务创建后已在 `COUNTING`；销售草稿改的是购买数量且尚未预占。

## 一张出库明细拆成多个包裹

出库 SKU-A × 10 后，Shipment A 可以发 6，Shipment B 发 4。`ShipmentItem.quantity > 0`。同一出库明细上所有未取消物流单的数量合计，不能超过该出库明细的 `outbound_quantity`。

V9 曾经历字段迁移：V8 把 `shipped_quantity` 当成已出库数量，`PARTIALLY_SHIPPED` / `SHIPPED` 当时表示仓库出库。V9 把旧值拷到 `outbound_quantity`，`shipped_quantity` 清零；历史状态改成 `PARTIALLY_OUTBOUND` / `OUTBOUNDED`。现在的 `PARTIALLY_SHIPPED` / `SHIPPED` 只表示物流。检索「SHIPPED」时必须看它写在销售订单上还是物流单上。

销售订单进入 `COMPLETED` 只能由系统根据履约结果决定，前端不能 `PATCH status = COMPLETED`。必须：所有购买数量都已出库、都已发货，并且所有正式物流单都已签收。两张物流单只签收一张时，订单仍是部分发货或已发货。

签收锁物流单，写成 `DELIVERED`，自动追加一条签收轨迹。整张物流单签收，不做某个 SKU 部分签收。已发货后不能改承运商、运单号、数量，也不能取消。撤回以后走异常物流或售后退货，不在本物流单上倒扣库存。

## 盘点明细字段

| 字段 | 含义 |
| --- | --- |
| `system_quantity` | 创建任务时的账面 `quantity` 快照 |
| 账面预占快照 | 当时的 `reserved_quantity` |
| `counted_quantity` | 仓库实盘 |
| `difference_quantity` | 实盘减快照 |

范围 `ALL` 会为该仓当时有库存行的 SKU 生成明细。`SELECTED_SKU` 只包含选中的 SKU。保存实盘走 `PUT /stocktakes/{id}/items` 或单行 PATCH，都不改 `Inventory`。

提交后进入 `PENDING_CONFIRMATION`，普通盘点人员不能再改数量。确认权限 `stocktake:confirm` 单独授予，因为确认会改库存。

盘盈：差异 > 0，确认后 `quantity` 增加。盘亏：差异 < 0，确认后减少，但仍须 `new_quantity >= reserved_quantity`。一致：差异 = 0，仍写流水或按实现跳过零差异，以 Service 为准；状态会变成 `CONFIRMED`。

停用仓不能盘点。查询历史已确认盘点单不因为仓库后来停用而删除。

## 接口与幂等

盘点：`GET/POST /api/v1/stocktakes`，`GET/PATCH /api/v1/stocktakes/{id}`，批量保存实盘 `PUT /api/v1/stocktakes/{id}/items`，提交 / 确认 / 取消走 `POST .../submit|confirm|cancel`。保存实盘不改库存。重复确认 `STOCKTAKE_ALREADY_CONFIRMED`。

物流确认发货、追加轨迹、签收都是物流单自己的 POST。轨迹接口不能代替签收。同一张物流单两个请求同时确认：行锁保证只成功一次。两张物流单竞争同一出库明细：创建时草稿占用剩余，确认时再按 `sku_id` 升序锁明细。

承运商编码前缀 `CAR`，物流单 `SHP`，盘点 `ST`。不要把 `ST` 当成库存流水类型；流水类型是 `STOCKTAKE_ADJUSTMENT`。


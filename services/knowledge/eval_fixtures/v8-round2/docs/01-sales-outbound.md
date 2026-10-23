# 销售订单与出库履约

本文转写 Neorvion ERP 当前已实现的销售订单、出库单和物流发货边界。状态名、字段名和错误码均来自源码与对应测试，不引入平台同步或未实现的换货流程。

销售订单回答「卖给客户什么、是否已经预占」。出库单回答「这次仓库实际发出多少」。物流单回答「货是否已经交给承运商」。三张单据不能互相替代。

## 销售订单状态机

`SalesOrderStatus` 只能经提交、确认、取消以及后续出库/发货动作流转，不要直接改 `status` 列。

| 状态 | 英文标识 | 代码注释中的含义 | 库存 |
| --- | --- | --- | --- |
| 草稿 | `DRAFT` | 可改客户、仓库、收货信息和明细；可提交或取消 | 未预占 |
| 待确认 | `PENDING_CONFIRMATION` | 已提交、等待审核。确认才会预占；也可取消且不动库存 | 未预占 |
| 待出库 | `WAITING_OUTBOUND` | 已确认并预占。尚未正式出库时可以整单取消并释放预占 | 已预占 |
| 部分出库 | `PARTIALLY_OUTBOUND` | 已经扣过库存，不能整单取消 | 部分已出库 |
| 已出库 | `OUTBOUNDED` | 购买数量都已离开库存账面，尚未全部交给承运商 | 已出库 |
| 部分发货 | `PARTIALLY_SHIPPED` | 已经有物流单确认发货 | 库存不再变化 |
| 已发货 | `SHIPPED` | 订单数量都已交给承运商 | 库存不再变化 |
| 已完成 | `COMPLETED` | 全部物流单都已签收 | 库存不再变化 |
| 已取消 | `CANCELLED` | 终态，不能再流转 | 若曾预占则已释放 |

来源枚举 `SalesOrderSource` 只做标记：`MANUAL` / `AMAZON` / `SHOPIFY` / `TIKTOK` / `OTHER`。当前版本不连接这些平台的 API。

## 为什么草稿和提交都不预占

用户可能先建单，再去补货。创建和保存 `DRAFT` 只写订单自己的表。库存不足可以提示，不能阻止保存草稿。

提交（`DRAFT` → `PENDING_CONFIRMATION`）同样不预占。提交只表示业务上可以交给审核人，仓库还没有被这张单占住。权限是 `order:submit`。

真正的库存校验发生在确认。确认接口是 `POST /sales-orders/{id}/confirm`，权限 `order:audit`。可用库存不足时，接口数据里的 `error` 为 `INSUFFICIENT_AVAILABLE_INVENTORY`。该错误码也出现在调拨确认调出、采购退货出库等「只能动可用库存」的路径，不要把它理解成出库超额。

## 确认时库存怎么变

确认表示订单已经成立，对应数量不能再卖给别人。货还没有离开仓库，所以：

- `Inventory.quantity` 不变
- `Inventory.reserved_quantity` 增加购买数量
- 明细 `SalesOrderItem.reserved_quantity = quantity`
- 流水类型 `RESERVE`，`reference_type = SALES_ORDER`，`reference_id` 为订单 id

可用库存不单独落库，查询时计算：

```text
available_quantity = quantity - reserved_quantity
```

例：确认前实际 100、预占 0、可用 100。购买 10 件后：实际仍 100，预占 10，可用 90。货仍在仓里。

订单号在 flush 拿到 id 后写成 `SO` + 年份 + 6 位 id，租户内唯一，不用 `MAX+1`。收货人、电话、国家、省、城市、地址写在订单自己的列上，是下单当时的快照。客户以后改档案，已保存的订单仍显示当时的收件信息。

明细同一订单同一 SKU 只能一行。约束包括 `reserved_quantity + outbound_quantity <= quantity`，以及后续发货的 `shipped_quantity <= outbound_quantity`。

## 哪些状态可以整单取消

`DRAFT` 和 `PENDING_CONFIRMATION` 可以取消，库存未被预占，取消不动库存。

`WAITING_OUTBOUND` 尚未正式出库，可以整单取消并释放预占。释放走库存 `release`，流水类型 `RELEASE`。释放数量超过 `reserved_quantity` 时，错误码是 `INSUFFICIENT_RESERVED_INVENTORY`。那是库存释放路径，不是出库路径。

`PARTIALLY_OUTBOUND` 已经扣过库存，不能整单取消。后续退货走独立售后领域，不回退本表的购买数量，也不把状态改回 `WAITING_OUTBOUND`。

停用客户不能创建新订单，错误数据为 `CUSTOMER_DISABLED`。客户已被销售订单引用时不能删除，只能停用，错误数据为 `CUSTOMER_IN_USE`。

## 出库单是仓库动作

一张销售订单可以有多张出库单，对应多次部分出库。确认销售订单时，同一事务自动生成第一张出库单，计划数量等于当时的预占。历史数据里已经是待出库但没有出库单的订单，用 `POST /api/v1/outbound-orders` 补一张。

`OutboundOrderStatus`：

| 状态 | 英文标识 | 库存 | 能否取消 |
| --- | --- | --- | --- |
| 待拣货 | `PENDING_PICKING` | 仍只是销售预占 | 可以 |
| 已拣货 | `PICKED` | 仍只是销售预占 | 可以 |
| 已确认出库 | `CONFIRMED` | 已扣 `quantity` 并释放预占 | 不能，退货走售后 |
| 已取消 | `CANCELLED` | 不碰库存；预占仍挂在销售订单上 | 终态 |

出库单号：`OUT` + 年份 + 6 位 id。权限：`outbound:read/create/pick/confirm/cancel`。业务确认不要求操作人再同时拥有 `inventory:outbound`。

未确认的出库单会占用计划数量。同一订单剩余可分配 = 明细 `reserved_quantity` − 未完成出库单的 `planned_quantity`。第一张如果计划了全部预占，必须等它确认或取消后，才能为剩余量再开一张。

## 为什么拣货不扣库存

拣货只记录仓库把货拿到了发货区，货还在账上。同一次出库可以分多次拣：计划 5 件时先拣 3、再拣 2，明细上的 `picked_quantity` 仍是累计 5，另外每次都会追加一条拣货记录。

未点「完成拣货」且还没拣满时，出库单保持 `PENDING_PICKING`。拣满或完成拣货后才变成 `PICKED`。确认出库仍按累计 `picked_quantity` 扣库存，不按单条记录再扣一次。

拣货数量超过计划时，接口数据里的 `error` 为 `OUTBOUND_PICK_EXCEEDS_PLAN`。它和出库超额、释放超额不是同一个码。

## 确认出库时库存怎么变

确认出库使用拣货数量作为本次 `outbound_quantity`。拣少了的部分仍留在销售订单的预占上，确认后可以再开出库单。

出库前：实际 100、预占 10、可用 90。本次发出此前已经预占的 6 件：

```text
quantity 100 → 94
reserved 10 → 4
available 90 → 90
```

可用量不变，是因为这 6 件在确认订单时已经从可用量里划走。现在只是从「还在仓库、但已被订单占用」变成「正式离开仓库」。如果只减 `quantity`、不减 `reserved`，预占会大于实际库存。

流水：`type=OUTBOUND`，`change_quantity` 为负，`reference_type=OUTBOUND_ORDER`。全部预占出完后，销售订单进入 `OUTBOUNDED`；只出一部分则进入 `PARTIALLY_OUTBOUND`。

出库数量超过已预占数量时，接口数据里的 `error` 为 `OUTBOUND_EXCEEDS_RESERVED`。该码不是 `INSUFFICIENT_RESERVED_INVENTORY`，后者出现在释放预占超过 `reserved_quantity` 的库存路径。

## 发货不再改库存

物流单表示货交给承运商。出库已经把账面库存扣掉，确认发货、更新轨迹、签收都不再改 `Inventory`。

`ShipmentStatus`：`DRAFT` / `SHIPPED` / `IN_TRANSIT` / `DELIVERED` / `CANCELLED`。发货数量不能超过已出库数量，超额时 `error` 为 `SHIPMENT_EXCEEDS_OUTBOUND`。

权限：`shipment:read/create/update/confirm/tracking:update/deliver/cancel` 与独立的 `carrier:*`。销售订单在有物流单确认发货后进入 `PARTIALLY_SHIPPED` 或 `SHIPPED`，全部签收后进入 `COMPLETED`。

## 权限与编号对照

| 动作 | 权限码 | 单号前缀 |
| --- | --- | --- |
| 查看 / 创建 / 修改销售订单 | `order:read` / `order:create` / `order:update` | `SO` |
| 提交 | `order:submit` | 同上 |
| 确认（预占） | `order:audit` | 同上 |
| 取消订单 | `order:cancel` | 同上 |
| 出库拣货 / 确认 / 取消 | `outbound:pick` / `outbound:confirm` / `outbound:cancel` | `OUT` |
| 确认发货 | `shipment:confirm` | 物流单独立编号 |

不要用 `SalesOrder.status` 代替仓库是否已经拣货。计划和实物分开，才能做部分出库，以及失败时整单回滚。

## 明细字段与约束

同一订单同一 SKU 只能一行：`UNIQUE(tenant_id, sales_order_id, sku_id)`。前后端都拒绝重复 SKU。

| 字段 | 说明 |
| --- | --- |
| `quantity` | 购买数量，必须大于 0 |
| `reserved_quantity` | 当前已预占、尚未正式出库 |
| `outbound_quantity` | 累计仓库已出库 |
| `shipped_quantity` | 累计已交给承运商 |
| `unit_price` | 可空 |

约束：`reserved_quantity + outbound_quantity <= quantity`，`shipped_quantity <= outbound_quantity`。买 10、出 6、发 4 之后可以是预占 4、已出库 6、已发货 4。

金额不落库。行金额和订单总额在读出时计算。不做税、折扣、运费。`currency_code` 默认 `CNY`，本版不做汇率。

## 允许和不允许的流转

允许：

- `DRAFT` → `PENDING_CONFIRMATION`（提交）
- `PENDING_CONFIRMATION` → `WAITING_OUTBOUND`（确认并预占，并生成第一张出库单）
- `WAITING_OUTBOUND` → `PARTIALLY_OUTBOUND` 或 `OUTBOUNDED`（确认出库）
- `PARTIALLY_OUTBOUND` / `OUTBOUNDED` → `PARTIALLY_SHIPPED` 或 `SHIPPED`（确认发货）
- `PARTIALLY_SHIPPED` → `SHIPPED` → `COMPLETED`（全部签收）
- `DRAFT` / `PENDING_CONFIRMATION` / `WAITING_OUTBOUND` → `CANCELLED`（已有出库数量时不能取消）

不允许任意 `PATCH status`。不能 `PATCH status = COMPLETED`，完成只能由签收结果决定。已取消不能再确认。待确认之后不能改客户、仓库、收货信息和明细。没有驳回或撤回提交。

只有草稿可以编辑。改明细时锁订单、校验 SKU 与重复行、删掉旧明细、插入新明细。草稿还没预占，所以不碰库存。

提交前检查：客户启用、仓库启用、至少一条明细、SKU 有效、数量大于 0、收件人和详细地址已填。

## 多 SKU 原子预占

确认整单是一个事务，由 `SalesOrderService.confirm_order()` 提交。`InventoryService.reserve_within_transaction()` 使用条件 UPDATE（`quantity - reserved_quantity >= qty`，看 `rowcount`），自己不 commit，也不要求 `inventory:adjust`。对外的手动预占测试接口仍检查 `inventory:adjust` 并自行提交，库存页面行为不变。

任一 SKU 可用不足，整单回滚，订单仍停在 `PENDING_CONFIRMATION`，不会出现只预占了部分明细的中间态。明细按 `sku_id` 排序后再预占，降低与其他单据交叉锁的死锁概率。

`SALES_ORDER_REFERENCE` 常量值为 `SALES_ORDER`，写在预占流水的 `reference_type` 上，用来区分「这次预占来自哪张销售订单」。出库流水的 `reference_type` 则是 `OUTBOUND_ORDER`。

## 部分出库的剩余可分配

确认订单购买 10 件后，第一张出库单计划数量等于当时预占 10。未确认时这 10 已经占住可分配额度。仓库如果只拣了 6 并确认出库：

- 销售明细 `outbound_quantity = 6`，`reserved_quantity = 4`
- 订单进入 `PARTIALLY_OUTBOUND`
- 剩余可再开出库单的数量是仍挂在订单上的预占 4

不能在第一张仍是 `PENDING_PICKING` 时再开一张也计划 10 的出库单。取消未完成出库单后，计划占用释放，预占仍在销售订单上。

拣货记录是追加的。计划 5 件时先拣 3、再拣 2，累计 `picked_quantity` 为 5。确认出库按累计拣货数量扣库存，不按每条拣货记录再扣一次。超过计划返回 `OUTBOUND_PICK_EXCEEDS_PLAN`。

## 仓库停用与客户停用

创建或确认销售订单时，仓库必须 `ACTIVE`。停用仓失败：HTTP 业务码 `40097`，`data.error = WAREHOUSE_DISABLED`，中文「只能使用启用中的仓库」。客户停用是另一条路径：`CUSTOMER_DISABLED`。客户已被引用不能删除，只能停用：`CUSTOMER_IN_USE`。

物流发货阶段的超额是 `SHIPMENT_EXCEEDS_OUTBOUND`，发生在 `shipped_quantity` 将要超过 `outbound_quantity` 时。那时库存早已在出库确认时扣过，发货接口不再碰 `Inventory`。详细状态见物流与盘点文档。

## 确认失败必须整单回滚

订单含 SKU-A × 8 和 SKU-B × 5。仓内 A 可用 20、B 可用 3。确认时按 `sku_id` 排序预占。B 可用不足时，A 即使已经在本事务里预占成功，也会随事务回滚。接口返回 `INSUFFICIENT_AVAILABLE_INVENTORY`。订单仍停在 `PENDING_CONFIRMATION`，没有出库单，流水里不应留下半截 `RESERVE`。

这与出库确认失败相同：拣货已记录但确认出库发现预占不足时，不能只扣一部分 SKU。出库超额码是 `OUTBOUND_EXCEEDS_RESERVED`，不要写成库存释放码 `INSUFFICIENT_RESERVED_INVENTORY`。

`WAITING_OUTBOUND` 整单取消会释放预占。`PARTIALLY_OUTBOUND` 不能走这条取消。已经出库的 6 件若要回来，只能开售后，不能把订单状态改回待出库。

出库确认权限是 `outbound:confirm`。库存目录里的 `inventory:outbound` 是预留编码，业务确认出库不要求操作人同时拥有它。手动库存调整走 `inventory:adjust`，与出库确认不是同一条路径。


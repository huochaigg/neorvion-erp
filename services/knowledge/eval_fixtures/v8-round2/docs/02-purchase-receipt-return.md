# 采购、收货与采购退货

采购单是计划，收货单是仓库实际收到多少，采购退货是收货之后把货退给供应商。三张单据独立，确认收货才增加 `quantity`，确认采购退货出库才减少 `quantity`。审核通过不改库存。

## 采购单状态机

`PurchaseOrderStatus` 只能经提交、审核、收货、取消流转，不要直接改 `status` 列。

| 状态 | 英文标识 | 含义 | 库存 |
| --- | --- | --- | --- |
| 草稿 | `DRAFT` | 可改供应商、仓库和明细；可提交审核或取消 | 未入库 |
| 待审核 | `PENDING_APPROVAL` | 可批准进入待收货、驳回，或取消 | 未入库 |
| 待收货 | `WAITING_RECEIPT` | 审核已通过，等待收货入库。可部分收货或一次收完；本版本不可取消 | 仍未入库 |
| 部分收货 | `PARTIALLY_RECEIVED` | 已有收货单入库，但仍有未收完的明细 | 已部分入库 |
| 已收货 | `RECEIVED` | 全部明细收齐。终态 | 已入库 |
| 已驳回 | `REJECTED` | 可改单后重新提交，或取消 | 未入库 |
| 已取消 | `CANCELLED` | 终态 | 未入库 |

批准同事务直达待收货，**无单独 `APPROVED`**。采购单批准和销售订单确认不是同一件事：采购批准不增加库存，销售确认才预占库存。

权限：`purchase:read/create/update/submit/audit/cancel`。供应商是独立资源，使用 `supplier:*`，不要把供应商权限写进采购单接口凑数。

采购单号：`PO` + 年份 + 6 位 id，租户内唯一。仓库和供应商必须属于同一租户，复合外键拒绝跨企业挂载。

## 收货单

只有 `WAITING_RECEIPT` 和 `PARTIALLY_RECEIVED` 能创建收货单。仓库必须是采购单上的仓库，不能在收货时换成别的仓。

`PurchaseReceiptStatus`：

| 状态 | 英文标识 | 能否改数量 | 库存 |
| --- | --- | --- | --- |
| 草稿 | `DRAFT` | 可以，也可作废 | 不改 |
| 已确认 | `CONFIRMED` | 不能再改、不能取消 | 已增加 `quantity` |
| 已作废 | `CANCELLED` | 不能再确认 | 不改 |

收货单号：`PR` + 年份 + 6 位 id。权限：`purchase:receipt:read/create/update/confirm/cancel`。业务确认不要求再同时拥有 `inventory:inbound`。

不能在前端直接改 `PurchaseOrderItem.received_quantity`。已收数量只在确认收货的同一事务里更新。

## 部分收货与超额

采购 SKU-A × 100。第一次实收 60：明细 `received_quantity` 从 0 变成 60，采购单进入 `PARTIALLY_RECEIVED`。第二次再收 40：`received_quantity = 100`，采购单进入 `RECEIVED`。一次收满则从 `WAITING_RECEIPT` 直接到 `RECEIVED`。

累计已收不能超过采购数量。两张草稿各收 60、同时确认时，会锁采购明细重新读已收数量，只有一张能成功。超额时 `error` 为 `PURCHASE_RECEIPT_EXCEEDS_REMAINING`。

重复确认已入库的收货单返回 `PURCHASE_RECEIPT_ALREADY_CONFIRMED`，库存只加一次。

## 确认收货时库存怎么变

当前实际 100、预占 30、可用 70。采购入库 50：

```text
quantity 100 → 150
reserved 30 → 30
available 70 → 120
```

入库的是新到的货，不是把已经卖出预占的货还回去，所以 `reserved_quantity` 不动。确认时只加 `quantity`，不改 `reserved`。确认逻辑不自己 `commit`，由调用方与采购进度同一事务提交。

流水：`type=INBOUND`，`change_quantity` 为正，`reference_type=PURCHASE_RECEIPT`。

仓库 + SKU 还没有库存行时，确认收货会创建 `quantity=实收`、`reserved=0`。创建使用保存点：先插入，若撞上 `UNIQUE(tenant_id, warehouse_id, sku_id)` 就回滚保存点，再走增加数量。不能只靠「先 SELECT 没有再 INSERT」，两个请求会同时认为不存在。

草稿收货单不入库。这与销售订单确认不同：销售确认写的是预占，采购收货确认增加的是 `quantity`。

## 采购退货是独立逆向领域

采购退货不修改原 `PurchaseOrderItem.quantity` / `received_quantity`，也不把已收货采购单改回其他收货状态。`quantity` 是当初计划采购多少的事实，`received_quantity` 是后来实际入库多少。退 20 件记在 `PurchaseReturnItem`，原采购明细仍是计划 100、已收 100。

可退数量：

```text
returnable_quantity = received_quantity - 有效采购退货占用
```

上限是已经成功收货入库的数量，不是采购计划数量。计划 100、只收到 60，最多退 60。超过时 `error` 为 `PURCHASE_RETURN_EXCEEDS_RETURNABLE`。

占用状态：`PENDING_APPROVAL`、`WAITING_OUTBOUND`、`PARTIALLY_RETURNED`、`WAITING_REFUND`、`COMPLETED`。`DRAFT` 不占用。`REJECTED` / `CANCELLED` 不占用。审核前按申请数量占用；审核后按批准数量占用。批准数量不能超过申请数量，否则 `APPROVED_RETURN_EXCEEDS_REQUESTED`。

## 采购退货状态机

`PurchaseReturnStatus`：

```text
DRAFT → PENDING_APPROVAL → WAITING_OUTBOUND → PARTIALLY_RETURNED / WAITING_REFUND / COMPLETED
                          ↘ REJECTED
DRAFT / PENDING_APPROVAL → CANCELLED
```

审核通过不保留 `APPROVED`：同事务进入 `WAITING_OUTBOUND`。这里的 `WAITING_OUTBOUND` 表示等待把货退给供应商，不是销售订单确认后的待出库。两个英文标识相同，业务对象不同。

结算类型 `PurchaseReturnSettlementType`：

| 类型 | 英文标识 | 全部出库后 |
| --- | --- | --- |
| 需要供应商退款 | `REFUND` | 进入 `WAITING_REFUND` |
| 只退货 | `NO_REFUND` | 直接 `COMPLETED`，`refund_status=NONE` |

单号：采购退货 `PRT`，退货出库 `PRO`，供应商退款 `SRF`，均为年份 + 6 位 id。

权限：`purchase_return:read/create/update/submit/approve/reject/cancel/outbound` 与 `supplier_refund:read/create/confirm`。

## 退供应商只能动 available

采购退货没有销售预占。账面 100、预占 60、可用 40 时，最多退 40。那 60 已经承诺给客户，采购退货不能释放销售订单预占。可用不足必须失败，错误码是 `INSUFFICIENT_AVAILABLE_INVENTORY`，与销售确认不足是同一码，原因都是「只能动可用库存」。

确认出库后：

```text
quantity 100 → 80
reserved 30 → 30
available 70 → 50
```

流水：`type=PURCHASE_RETURN_OUTBOUND`，`change_quantity` 为负，`reference_type=PURCHASE_RETURN`。复用 `InventoryService.deduct_available_within_transaction`。

采购退货单回答「计划退多少」。退货出库单回答「这次仓库实际退走多少」。批准 10、第一次出库 6、第二次 4，各有独立 `purchase_return_outbounds` 记录。草稿出库不改库存。确认出库才扣减。未确认可取消。本次出库超过剩余批准量时，`error` 为 `PURCHASE_RETURN_OUTBOUND_EXCEEDS_REMAINING`。

## 供应商退款

`settlement_type=REFUND` 时，全部批准数量出库后进入 `WAITING_REFUND`。每一次尝试是 `supplier_refund_records` 里的一行。失败后新建，不能覆盖失败历史。确认退款不修改库存。超过批准金额时 `error` 为 `SUPPLIER_REFUND_EXCEEDS_APPROVED`。

本版只做 ERP 内人工确认，不接银行或应付结算。

## 和销售链路不要合成一句

| 动作 | 是否改 `quantity` | 是否改 `reserved_quantity` |
| --- | --- | --- |
| 采购批准 | 否 | 否 |
| 采购收货确认 | 增加 | 否 |
| 采购退货出库确认 | 减少 | 否 |
| 销售订单确认 | 否 | 增加 |
| 销售出库确认 | 减少 | 减少 |

「确认」在采购收货、采购退货出库、销售订单上的库存效果不同，不能写成一条通用规则。

## 采购单字段与审核

`expected_arrival_date` 可空。`remark` 最长 255。提交后记录 `submitted_at`。批准记录 `approved_at` / `approved_by`。驳回记录 `rejected_at` / `rejected_by` / `reject_reason`。取消记录 `cancelled_at` / `cancelled_by` / `cancel_reason`。

`WAITING_RECEIPT` 本版本不可取消：审核已通过，仓库可能已经按这张单准备收货。要退供应商必须走采购退货，不能把待收货单直接改回取消。

`REJECTED` 可改单后重新提交。改单仍只动采购单自己的表，不碰库存。没有单独的「撤回提交」动作把 `PENDING_APPROVAL` 退回 `DRAFT`。

不要开放 `PATCH status`。批准不是把状态写成一个不存在的 `APPROVED` 再另一步变待收货。

## 收货单明细

收货单仓库在创建时从采购单拷贝，确认时再次校验仍是同一仓。明细 `received_quantity` 是本次实收，不是采购累计。累计写在采购明细上，由确认事务更新。

收货草稿可以改本次数量或作废。作废后不能再确认。已确认不能取消，退货必须另开采购退货单。这与销售出库已确认不能取消、退货走售后是同一类边界：正向确认一旦改了库存，逆向用独立单据。

确认收货时锁采购明细，按当前 `received_quantity` 计算剩余可收，再累加本次实收。并发两张收货单抢最后 40 件时，只有一张能把采购单推到 `RECEIVED`。

## 采购退货占用与出库拆分

草稿不占用可退数量，所以同一采购单上可以同时存在多张退货草稿。一旦提交进入 `PENDING_APPROVAL`，申请数量开始占用。审核通过后改按批准数量占用。

退货出库单是另一张表。不能只改采购退货明细上的累计出库字段而丢掉「第一次退 6、第二次退 4」的过程。未确认的退货出库占用剩余批准量，确认后才扣 `Inventory.quantity`。

`NO_REFUND` 在全部批准数量出库后直接完成。`REFUND` 必须再走供应商退款记录。确认供应商退款不回补库存；货已经退走。

## 采购单与供应商

供应商是独立主数据，权限 `supplier:*`。采购单上的供应商和仓库必须属于同一租户，复合外键拒绝跨企业挂载。停用供应商后不能再创建指向它的新采购单；历史采购单仍保存当时的供应商 id。

采购明细同一采购单同一 SKU 通常一行。数量必须大于 0。已收数量不能在页面上直接改，只能通过确认收货累加。采购计划数量在收货后也不因采购退货而回写。

## 收货确认的幂等与并发

已确认收货单再次确认：`PURCHASE_RECEIPT_ALREADY_CONFIRMED`，`quantity` 只加一次。两张草稿同时抢最后 40 件：锁采购明细后重新读 `received_quantity`，超额的那张得到 `PURCHASE_RECEIPT_EXCEEDS_REMAINING`。

仓库 + SKU 尚无库存行时，确认收货会插入新行。插入使用保存点：撞上 `UNIQUE(tenant_id, warehouse_id, sku_id)` 只回滚保存点，再走增加数量。两个收货请求同时为新 SKU 建行时，不能先 SELECT 判断不存在再 INSERT。

采购退货出库超额是 `PURCHASE_RETURN_OUTBOUND_EXCEEDS_REMAINING`。它限制的是「这次退走多少不能超过剩余批准量」，不是收货剩余，也不是销售出库预占。

## 待收货不能当销售待出库取消

销售 `WAITING_OUTBOUND` 可以整单取消并释放预占。采购 `WAITING_RECEIPT` 本版本不可取消。两个状态都表示「下一步是仓库动作」，取消规则相反。

原因：采购批准不预占、不扣库存，但仓库可能已经按这张单准备收货；要退供应商必须等货入过库再走采购退货。销售待出库则已经预占，取消是把还没发出的承诺还回去。

因此「待收货能不能取消」的证据应落在采购文档，而不是销售取消章节。把两个 `WAITING_*` 拼成一句「等待仓库时都可以取消」是错误结论。

## 供应商退款与客户退款

供应商退款记录挂在采购退货上，单号前缀 `SRF`。权限 `supplier_refund:read/create/confirm`。`supplier_refund:confirm` 属于 ERP 高风险集合，回源 IAM。客户退款权限是 `refund:confirm`，也是高风险，但是另一条码。

超额码：供应商 `SUPPLIER_REFUND_EXCEEDS_APPROVED`，客户 `REFUND_EXCEEDS_APPROVED`。两者都是「超过批准剩余」，单据不同。失败后新建一行，不覆盖失败历史。确认退款无论客户还是供应商都不回补 `Inventory.quantity`。


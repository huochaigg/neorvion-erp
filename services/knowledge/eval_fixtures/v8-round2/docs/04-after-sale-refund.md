# 销售售后、退货入库与退款

售后是独立领域，不改 `SalesOrderItem.quantity`，也不回退销售履约状态。客户买 10 件、后来退 3 件，历史购买数量仍是 10。本次售后记在 `AfterSaleItem.return_quantity`，原购买数量快照在 `original_quantity`。

正向销售订单仍然是：订单 → 预占 → 出库 → 发货 → 签收 → 完成。售后挂在旁边。

## 三种类型

`AfterSaleType`：

| 类型 | 英文标识 | 审核后 | 是否改库存 | 是否退款 |
| --- | --- | --- | --- | --- |
| 仅退款 | `REFUND_ONLY` | 进入待退款 | 否 | 是 |
| 退货并退款 | `RETURN_AND_REFUND` | 生成退货单 | 入库时 `GOOD` 增加 `quantity` | 退货处理完成后再退款 |
| 只回收商品 | `RETURN_ONLY` | 生成退货单 | 同上 | 否 |

不要把退款和退货当成一件事。少量补偿走 `REFUND_ONLY`。换货重新发货本版不做。

## 哪些订单可以申请

只允许已经产生实际履约的销售订单：

`PARTIALLY_OUTBOUND` / `OUTBOUNDED` / `PARTIALLY_SHIPPED` / `SHIPPED` / `COMPLETED`

`DRAFT` / `PENDING_CONFIRMATION` / `WAITING_OUTBOUND` 应取消订单、释放预占，不能创建退货售后。尚未出库的货还在预占里，正确动作是取消销售订单，不是开售后。

## 可退数量与并发

```text
returnable_quantity = outbound_quantity - 有效售后已占用数量
```

上限是已经正式出库的数量，不是购买数量，也不是 `reserved_quantity`。只出库 6 件，最多退 6。超过时 `error` 为 `AFTER_SALE_EXCEEDS_RETURNABLE`。测试 `test_after_sales.py` 断言该码。

占用状态：`PENDING_APPROVAL`、`WAITING_RETURN`、`WAITING_REFUND`、`COMPLETED`。拒绝或取消后释放。待审核就占用，避免两张单同时各退 8、订单只有 10。

审核前按申请数量占用；审核后按批准数量占用。批准数量或金额超过申请时，`error` 为 `AFTER_SALE_APPROVED_EXCEEDS_REQUESTED`。

`create_after_sale()` 先锁销售订单，再按 `sku_id` 稳定顺序 `SELECT FOR UPDATE` 相关 `SalesOrderItem`，重新汇总有效售后占用，再判断 `existing + requested <= outbound_quantity`。两个请求同时退 8 只能成功一个。创建售后不改库存、不改原销售明细。

## 金额

没有复杂优惠分摊。可退金额约等于 `outbound_quantity × unit_price`，再减去有效售后已占用金额。币种沿用 `SalesOrder.currency_code`，售后单保存快照，不允许改币种。超过可退金额时 `error` 为 `AFTER_SALE_EXCEEDS_REFUNDABLE`。

申请金额 `requested_refund_amount`；审核金额 `approved_refund_amount` 可以更小，不能更大。真正退款不能超过批准剩余，否则 `REFUND_EXCEEDS_APPROVED`。

售后单号：`AS` + 年份 + 6 位 id。权限：`after_sale:read/create/approve/reject/cancel`。

## 售后状态机

`AfterSaleStatus`：`PENDING_APPROVAL` / `REJECTED` / `WAITING_RETURN` / `WAITING_REFUND` / `COMPLETED` / `CANCELLED`。

仅退款：`PENDING_APPROVAL` → `WAITING_REFUND` → `COMPLETED`（拒绝或取消可离开待审核）。

退货退款：`PENDING_APPROVAL` → `WAITING_RETURN` →（收货入库）→ `WAITING_REFUND` → `COMPLETED`。

仅退货：`PENDING_APPROVAL` → `WAITING_RETURN` →（收货入库）→ `COMPLETED`。

`refund_status` 是汇总：`NONE` / `PENDING` / `SUCCESS`。`FAILED` 记在 `RefundRecord` 上，售后仍保持待退款，不把汇总改成失败终态。

## 退货单：收到不等于入库

需要退货的售后在审核通过时创建退货单。一张售后对应一张退货单，唯一约束在 `(tenant_id, after_sale_order_id)`。

退货单号：`RT` + 年份 + 6 位 id。必须选择当前租户的启用仓库，可以和原履约仓不同，不能跨租户。停用仓会失败，错误码 `40097`。

`ReturnOrderStatus`：`WAITING_RETURN` → `PARTIALLY_RECEIVED` / `RECEIVED` → `PARTIALLY_INBOUNDED` / `INBOUNDED`。允许分多次收货。累计 `received_quantity` 不能超过 `expected_quantity`。

权限：`return_order:read/receive/inbound`。

## 质量状态决定能否入普通库存

`ReturnCondition`：

| 值 | 含义 | 是否进入普通 `Inventory.quantity` |
| --- | --- | --- |
| `GOOD` | 正常可售 | 可以，`inbound_quantity` 对应已收的良品 |
| `DAMAGED` | 损坏 | 可记已收，默认不入普通库存 |
| `UNSELLABLE` | 不可销售 | 不入普通库存 |
| `OTHER` | 其他 | 同残次品，本版不入普通库存 |

当前 `Inventory` 只有 `quantity` / `reserved_quantity`，没有残次品台账。V11 不把库存扩成 WMS 多维度。

客户退回的是已经正式出库的商品。原订单预占在确认出库时已经和实际库存一起扣掉。退货回来只补 `quantity`，`reserved_quantity` 不变。如果把 reserved 加回去，会凭空制造待出库库存。

流水：`type=RETURN_INBOUND`，`reference_type=RETURN_ORDER`。

## 退款记录不能覆盖失败历史

`RefundRecord` 是一次具体退款动作。V11 只做 ERP 内人工确认，不接支付宝、微信或 Stripe。第一次失败、第二次成功必须两条记录。

`RefundRecordStatus`：`PENDING` / `SUCCESS` / `FAILED`。权限：`refund:read/create/confirm`。高风险确认退款回源 IAM `internal/authorize`，不是只信 Redis 快照。

`RETURN_ONLY` 不创建退款。`RETURN_AND_REFUND` 必须先完成退货入库，才能进入待退款。

## 和采购退货的相似点

销售售后占用的是已出库数量；采购退货占用的是已收货数量。两者都不改正向单据的计划数量。两者都可能出现「EXCEEDS_RETURNABLE」家族错误码，前缀不同：`AFTER_SALE_EXCEEDS_RETURNABLE` 对客户退货，`PURCHASE_RETURN_EXCEEDS_RETURNABLE` 对供应商退货。检索时命中其中一个不能当成另一个的证据。

## 售后明细占用

`AfterSaleItem` 保存 `original_quantity` 快照和本次 `return_quantity`。有效占用按 SKU 汇总后与该销售明细的 `outbound_quantity` 比较。审核把申请数量改小时，占用跟着批准数量走，多出来的可退份额立即还给后续售后。

拒绝或取消后占用释放，销售订单履约状态不变。`PARTIALLY_OUTBOUND` 不会因为售后完成而变回 `WAITING_OUTBOUND`。

`AFTER_SALE_REFERENCE` 值为 `AFTER_SALE`。退货入库流水的 `reference_type` 是 `RETURN_ORDER`。退款记录是 `REFUND`。不要把售后单 id 写进库存流水却用错 reference。

## 收货与入库是两步

仓库先把客户退回的货记为实收，再决定哪些以 `GOOD` 入普通库存。实收可以分多次。残次品可以记在 `received_quantity` 里，同时 `inbound_quantity` 保持 0。当前没有残次品仓，残次数量不会出现在 `inventories.quantity` 里。

入库确认只增加目标仓 `quantity`。目标仓可以和原销售履约仓不同，但仍必须是本租户启用仓库。跨租户退货入库没有接口。

退货退款类型必须等退货单到达已入库（所需良品入库完成）后，售后才进入 `WAITING_REFUND`。未入库完成就去确认退款，应被 Service 拒绝。

## 退款尝试

`RefundRecord` 有独立 `refund_no`。状态 `PENDING` 表示 ERP 内已登记、等待人工确认外部已退。`SUCCESS` 表示确认成功。`FAILED` 保留失败原因，下一次再插入新行。售后汇总 `refund_status` 在存在未完成或失败尝试时保持 `PENDING`，全部成功后才到 `SUCCESS`。

确认退款是高风险动作，走 IAM `internal/authorize`，权限 `refund:confirm`。

## 三种类型对库存和退款的交叉

| 问题 | `REFUND_ONLY` | `RETURN_AND_REFUND` | `RETURN_ONLY` |
| --- | --- | --- | --- |
| 审核通过后 | 待退款 | 生成退货单 `RT` | 生成退货单 `RT` |
| 是否必须收货入库 | 否 | 是，良品入完才能待退款 | 是，入完即完成 |
| `Inventory.quantity` | 不变 | 仅 `GOOD` 增加 | 仅 `GOOD` 增加 |
| `reserved_quantity` | 不变 | 不变 | 不变 |
| 退款记录 | 需要 | 入库完成后需要 | 不创建 |

尚未出库的订单应取消销售订单。售后占用的是 `outbound_quantity`。因此「买了 10、只出了 6、预占还剩 4」时，最多退 6；那 4 仍应通过取消待出库来释放，而不是开售后。

退货仓停用：售后服务抛出业务码 `40097`，中文「只能退回到启用中的仓库」。销售创建订单时停用仓会带 `WAREHOUSE_DISABLED`。检索「40097」必须看中文消息和 `data.error`，不能把售后退货仓和承运商类型错误当成同一证据。

已 `INBOUNDED` 的退货单再次确认入库必须拒绝，库存不能加两次。`confirm_return_inbound()` 锁退货单，明细按 `sku_id` 排序，`GOOD` 的 `received - inbound` 增量入库，残次品 `inbound_quantity` 保持 0。

## 正向履约状态不被售后改写

客户买 10、出 10、发 10、签收完成后订单是 `COMPLETED`。之后退 3 件：

- 销售明细 `quantity` 仍是 10，`outbound_quantity` 仍是 10，`shipped_quantity` 仍是 10
- 订单状态仍是 `COMPLETED`
- 售后单记录退 3；退货入库后目标仓 `quantity` 增加 3（若为 `GOOD`）

不要把完成态销售订单改回 `PARTIALLY_OUTBOUND` 或 `WAITING_OUTBOUND`。详情页可以展示售后列表，那是旁路单据。

`RETURN_AND_REFUND` 在退货入库完成前不能确认客户退款。`REFUND_ONLY` 不生成 `RT` 单。供应商退款走 `SRF` 记录，权限是 `supplier_refund:confirm`，与客户 `refund:confirm` 不是同一个高风险码。

## 退货单状态不要写成采购收货

`ReturnOrderStatus`：`WAITING_RETURN` / `PARTIALLY_RECEIVED` / `RECEIVED` / `PARTIALLY_INBOUNDED` / `INBOUNDED` / `CANCELLED`。

采购收货单只有 `DRAFT` / `CONFIRMED` / `CANCELLED`，没有「已收货再入库」两段。销售退货先实收再入库，所以会出现 `RECEIVED` 但仍未 `INBOUNDED`。检索「PARTIALLY_RECEIVED」必须看单据：采购正向收货进度，或售后退货实收进度。

`expected_quantity` 是审核批准后预期客户退回的数量。累计实收不能超过它。`inbound_quantity` 不能超过已收的良品数量。残次品可以实收，默认不入普通库存。

退货入库复用 `InventoryService.inbound_within_transaction`，`tx_type=RETURN_INBOUND`，不要另写一套加法。流水 `reference_type=RETURN_ORDER`。预占前后相同。两个请求同时确认同一张退货单，只能成功一次。

售后审核权限 `after_sale:approve` / `after_sale:reject`。拒绝后占用释放，不改库存。取消待审核同样释放。已经进入 `WAITING_RETURN` 后能否取消，以当前 `AfterSaleService` 实现为准；一旦退货入库改了 `quantity`，不能靠取消售后把库存倒扣回去，应继续用库存调整或后续业务流程处理。换货重新发货本版不做。



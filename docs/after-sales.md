# 销售售后

当前里程碑 **V11**。售后是独立领域，不回退原销售订单的履约状态，也不修改 `SalesOrderItem.quantity`。

```text
已履约销售订单
  → 售后申请（占用可退数量）
  → 审核通过 / 拒绝 / 取消
  → 需要退货则生成退货单
  → 仓库收货、确认入库
  → 需要退款则登记 RefundRecord
  → 人工确认外部退款成功
  → 售后完成
```

正向销售订单仍然是：订单 → 预占 → 出库 → 发货 → 签收 → 完成。售后挂在旁边，详情页可以展示售后列表。

## 为什么不改 SalesOrderItem.quantity

`SalesOrderItem` 是当时卖了多少的业务事实。客户买 10 件、后来退 3 件，历史购买数量仍是 10。本次售后记在 `AfterSaleItem.return_quantity`，原购买数量快照在 `original_quantity`。

可退、已退通过售后记录聚合，不把销售明细改成 7。

## 三种类型

| 类型 | 含义 | 审核后 | 是否改库存 | 是否退款 |
| --- | --- | --- | --- | --- |
| `REFUND_ONLY` | 仅退款，不要求客户退货 | 进入待退款 | 否 | 是 |
| `RETURN_AND_REFUND` | 退货并退款 | 生成退货单 | 入库时 GOOD 增加 `quantity` | 退货处理完成后再退款 |
| `RETURN_ONLY` | 只回收商品 | 生成退货单 | 同上 | 否 |

不要把退款和退货当成一件事。少量补偿走 `REFUND_ONLY`。换货重新发货本版不做。

## 哪些订单可以申请

只允许已经产生实际履约的销售订单：

`PARTIALLY_OUTBOUND` / `OUTBOUNDED` / `PARTIALLY_SHIPPED` / `SHIPPED` / `COMPLETED`

`DRAFT` / `PENDING_CONFIRMATION` / `WAITING_OUTBOUND` 应取消订单、释放预占，不能创建退货售后。

## 可退数量

```text
returnable_quantity = outbound_quantity - 有效售后已占用数量
```

上限是已经正式出库的数量，不是购买数量，也不是 `reserved_quantity`。只出库 6 件，最多退 6。

占用状态：`PENDING_APPROVAL`、`WAITING_RETURN`、`WAITING_REFUND`、`COMPLETED`。拒绝或取消后释放。待审核就占用，避免两张单同时各退 8、订单只有 10。

审核前按申请数量占用；审核后按批准数量占用。

## 并发创建

`create_after_sale()` 先锁销售订单，再按 `sku_id` 稳定顺序 `SELECT FOR UPDATE` 相关 `SalesOrderItem`，重新汇总有效售后占用，再判断 `existing + requested <= outbound_quantity`。两个请求同时退 8 只能成功一个。

创建售后不改库存、不改原销售明细。

## 金额

没有复杂优惠分摊。可退金额约等于 `outbound_quantity × unit_price`，再减去有效售后已占用金额。币种沿用 `SalesOrder.currency_code`，售后单保存快照，不允许改币种。

申请金额 `requested_refund_amount`；审核金额 `approved_refund_amount` 可以更小，不能更大。真正退款不能超过批准剩余。

## RefundRecord

售后单上的 `refund_status` 是汇总：`NONE` / `PENDING` / `SUCCESS`。具体每一次尝试是 `refund_records` 里的一行。

第一次失败、第二次成功必须两条记录。不能覆盖失败历史。V11 的确认退款表示 ERP 内人工确认“外部已经退了”，不调用支付宝 / 微信 / Stripe。

`RETURN_ONLY` 不创建退款。`RETURN_AND_REFUND` 必须先完成退货入库，才能进入待退款。

## 状态机

仅退款：`PENDING_APPROVAL` → `WAITING_REFUND` → `COMPLETED`（拒绝/取消可离开待审核）。

退货退款：`PENDING_APPROVAL` → `WAITING_RETURN` →（收货入库）→ `WAITING_REFUND` → `COMPLETED`。

仅退货：`PENDING_APPROVAL` → `WAITING_RETURN` →（收货入库）→ `COMPLETED`。

完成后台根据类型自动进入 `COMPLETED`，前端不能 `PATCH status`。

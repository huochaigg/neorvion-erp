# 采购退货

当前里程碑 **V12**。采购退货是独立逆向领域，不修改原 `PurchaseOrderItem.quantity` / `received_quantity`，也不把已收货采购单改回其他收货状态。

```text
已收货采购单
  → 创建采购退货草稿（不占用可退、不改库存）
  → 提交审核（开始占用可退数量）
  → 审核通过进入待出库 / 拒绝释放占用
  → 创建退货出库草稿（不改库存）
  → 确认出库：Inventory.quantity 减少，reserved 不变
  → NO_REFUND 全部出库后完成；REFUND 进入待退款
  → 人工确认供应商退款后完成
```

正向采购仍然是：采购单 → 审核 → 收货 → 入库。采购退货挂在旁边，采购单详情可以展示累计退货和可退数量。

## 为什么必须独立于 PurchaseOrder

`PurchaseOrderItem.quantity` 是当初计划采购多少的事实。`received_quantity` 是后来实际入库多少。采购退货发生在收货之后，如果把计划数量改小，历史采购事实就被破坏。

退 20 件必须记在 `PurchaseReturnItem`，原采购明细仍是计划 100、已收 100。

## 可退数量

```text
returnable_quantity = received_quantity - 有效采购退货占用
```

上限是已经成功收货入库的数量，不是采购计划数量。计划 100、只收到 60，最多退 60。

占用状态：`PENDING_APPROVAL`、`WAITING_OUTBOUND`、`PARTIALLY_RETURNED`、`WAITING_REFUND`、`COMPLETED`。

`DRAFT` 不占用，草稿可以随意改。`REJECTED` / `CANCELLED` 不占用。

审核前按申请数量占用；审核后按批准数量占用。

## 为什么退供应商只能用 available

采购退货没有销售预占。账面 100、预占 60、可用 40 时，最多退 40。那 60 已经承诺给客户，采购退货不能偷偷释放销售订单预占。可用不足必须失败，由业务人员先处理其他单据。

确认出库后：

```text
quantity 100 → 80
reserved 30 → 30
available 70 → 50
```

流水：`type=PURCHASE_RETURN_OUTBOUND`，`change_quantity` 为负，`reference_type=PURCHASE_RETURN`，`reference_id` 为采购退货单 id。复用 `InventoryService.deduct_available_within_transaction`。

## PurchaseReturn 与 Outbound

采购退货单回答「计划退多少」。退货出库单回答「这次仓库实际退走多少」。批准 10、第一次出库 6、第二次 4，各有独立 `purchase_return_outbounds` 记录，不能只改累计字段丢掉过程。

草稿出库不改库存。确认出库才扣减。未确认可取消。

单号：`PRT` / `PRO` / `SRF` + 年份 + 6 位 id。不用 MAX+1。

## 供应商退款

`settlement_type=REFUND` 时，全部批准数量出库后进入 `WAITING_REFUND`。每一次尝试是 `supplier_refund_records` 里的一行。失败后新建，不能覆盖失败历史。确认退款不修改库存。

`NO_REFUND`：全部出库后直接 `COMPLETED`，`refund_status=NONE`。

本版只做 ERP 内人工确认，不接银行或应付结算。

## 状态机

```text
DRAFT ──submit──► PENDING_APPROVAL ──approve──► WAITING_OUTBOUND
  │                      │                         │
  └──cancel──► CANCELLED └──reject──► REJECTED      ├── 部分出库 ► PARTIALLY_RETURNED
                                                    └── 全部出库 ► WAITING_REFUND 或 COMPLETED
WAITING_REFUND ──退款完成──► COMPLETED
```

不要开放任意 PATCH status。完成条件由出库和退款业务判断。

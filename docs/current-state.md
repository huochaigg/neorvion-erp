# 当前状态

有效里程碑：**V13**。以本文件和当前代码为准。旧版本文档只描述当时范围。

## 已完成

- V3 商品 / SPU / SKU / 类目 / 品牌
- V4 仓库
- V5 库存、流水、条件预占 / 释放 / 扣减预占、调整锁
- V6 供应商、采购单、采购状态机（审核不改库存）
- V6.1 ERP 布局、Table、主题、中文日期
- V7 客户、销售订单、确认预占、取消释放
- V8 采购收货入库、销售拣货与确认出库、部分收货 / 部分出库
- V9 物流商、物流单、确认发货、手工轨迹、签收、销售订单完成
- V10 库存盘点、跨仓调拨
- V11 销售售后、退货入库、退款状态
- V12 采购退货、退货出库、供应商退款状态
- V13 经营总览、销售 / 采购 / 库存 / 售后报表、统一统计口径、CSV 导出

## 报表

Analytics 当前实时从 MySQL 聚合。暂未引入汇总表、OLAP、Redis Analytics Cache。口径见 `docs/analytics.md`。为后续 V14 / Agent 提供稳定只读统计 API。

## 采购正向与逆向

正向：采购单 → 审核 → 收货 → 入库。审核通过仍不增加库存。

逆向：采购退货申请 → 审核 → 退货出库 → 供应商退款 → 完成。

采购退货不修改原 `PurchaseOrderItem.quantity` / `received_quantity`，也不把已收货采购单改回其他收货状态。

可退数量 = `received_quantity` − 有效采购退货占用。占用状态：待审核、待出库、部分退货、待退款、已完成。草稿不占用。拒绝 / 取消释放占用。

退货出库只减少 `Inventory.quantity`，不改 `reserved_quantity`。可用不足则失败，不能偷释放销售预占。流水 `PURCHASE_RETURN_OUTBOUND`，引用采购退货单。

`SupplierRefundRecord` 仅为人工确认供应商退款结果，不接银行。失败记录保留，重试新建一行。`NO_REFUND` 全部出库后直接完成。

## 销售正向与逆向

正向：订单 → 预占 → 出库 → 发货 → 签收 → 完成。

逆向：售后申请 → 审核 → 退货 → 收货 → 入库 → 退款 → 售后完成。

售后不修改原 `SalesOrderItem.quantity`，也不把销售订单从 `COMPLETED` 改回其他履约状态。

可退数量 = `outbound_quantity` − 有效售后占用。占用状态：待审核、待退货、待退款、已完成。拒绝 / 取消释放占用。

退货入库只增加 `Inventory.quantity`，不恢复 reserved。只有 `GOOD` 进入普通库存。`DAMAGED` / `UNSELLABLE` 可记已收，inbound 为 0。

`RefundRecord` 当前仅为人工确认外部退款结果，不接真实支付渠道。失败记录保留，重试新建一行。

## 当前库存能力

初始化、调整、预占、释放、采购入库、销售出库、盘点差异调整、跨仓调拨、销售退货入库、采购退货出库、库存流水。

## 库存字段

| 字段 | 含义 |
| --- | --- |
| `quantity` | 仓库里的实际数量 |
| `reserved_quantity` | 已被订单占用、尚未出库 |
| `available_quantity` | 不入库，等于 `quantity - reserved_quantity` |

## 下一版可复用

- `inbound_within_transaction`（采购入库、调拨调入、退货入库）
- `deduct_available_within_transaction`（采购退货出库、调拨调出）
- 售后 / 采购退货可退数量占用与 `SELECT FOR UPDATE`
- RefundRecord / SupplierRefundRecord 预留给支付渠道对账
- Analytics 只读聚合 API（销售 / 采购 / 库存 / 售后 summary、趋势、Top N）

## 明确未做

真实银行退款、应付账款、采购发票、财务凭证、税务、采购换货、补货单、次品库存台账、复杂质检、平台售后同步、换货重新发货、真实承运商 API、库位批次、日报表、OLAP、AI Agent。

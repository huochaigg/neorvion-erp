# 当前状态

有效里程碑：**V10**。以本文件和当前代码为准。旧版本文档只描述当时范围。

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

## 当前库存能力

初始化、调整、预占、释放、采购入库、销售出库、盘点差异调整、跨仓调拨、库存流水。

盘点状态：`COUNTING` → `PENDING_CONFIRMATION` → `CONFIRMED`。确认按差异调整当前账面，不是覆盖成实盘数。

调拨状态：`DRAFT` → `PENDING_OUTBOUND` → `IN_TRANSIT` → `COMPLETED`。在途不建独立库存表，用调拨单状态和 `outbound_quantity` 表示。

## 采购

采购 → 收货 → 入库。审核通过仍不增加库存。库存增加只发生在收货单确认。

## 销售

订单 → 预占 → 拣货 → 出库 → 物流发货 → 签收 → 完成。确认发货不再改库存。有正式出库后不能取消整张销售订单。

## 库存字段

| 字段 | 含义 |
| --- | --- |
| `quantity` | 仓库里的实际数量 |
| `reserved_quantity` | 已被订单占用、尚未出库 |
| `available_quantity` | 不入库，等于 `quantity - reserved_quantity` |

## 下一版可复用

- `inbound_within_transaction` / `deduct_within_transaction` / `apply_delta_within_transaction` / `deduct_available_within_transaction`
- 收货、出库、盘点、调拨按 `sku_id` 升序加锁
- 盘点差异算法和调拨在途模型
- Carrier 档案和手工轨迹模型

## 明确未做

真实承运商 API、电子面单、自动轨迹、Amazon / Shopify / TikTok 同步、退货、退款、售后、财务结算、库位、批次、序列号、独立在途库存表、AI Agent。

# 数据看板与报表中心（V13）

第一版对 V3–V12 业务表做 **实时 / 准实时 MySQL 聚合**。不建 `daily_*_summary`，不引入 Redis Analytics Cache、物化视图或 OLAP。CSV 导出对以 `= + - @` 开头的单元格加前缀，避免 Excel Formula Injection。

报表日期边界按业务库 **naive 本地墙钟时间**（与 `datetime.now()` 一致），不是 UTC。

区间：`[start_date 当天 00:00:00, end_date 次日 00:00:00)`。不要写成 `23:59:59.999999`。

未传日期时默认最近 30 天（含今天）。最长 366 天。`start_date > end_date` 返回 `40600`。

所有 SQL 显式 `tenant_id`。不接受 query 里的 `tenant_id`。

## 销售口径

有效销售订单：`status NOT IN (DRAFT, CANCELLED)`，按 `SalesOrder.created_at`。

- `gross_sales_amount`：`SUM(COALESCE(unit_price,0) * quantity)`，仅有效订单
- `refund_amount`：`RefundRecord.status = SUCCESS`，时间 `COALESCE(refunded_at, created_at)`。PENDING / FAILED 不扣
- `net_sales_amount` = 毛销售额 − 成功退款
- `average_order_value` = 毛销售额 ÷ 有效订单数，分母为 0 时返回 0
- `return_rate` / 售后率 = `COUNT(DISTINCT 有效售后.sales_order_id)` ÷ 有效销售订单数  
  不是售后单数量 ÷ 订单数量。一张订单多张售后只计一次。有效售后排除 `REJECTED`、`CANCELLED`。

Top SKU / SPU / Customer 只统计有效销售订单。客户净销售再扣该客户成功退款。

## 采购口径

有效采购单：排除 `DRAFT`、`REJECTED`、`CANCELLED`，按 `PurchaseOrder.created_at`。

- `purchase_amount`：`SUM(COALESCE(unit_price,0) * quantity)`
- `received_quantity`：确认收货单 `CONFIRMED` 的实收合计，时间 `COALESCE(received_at, created_at)`
- `pending_receipt_order_count`：当前 `WAITING_RECEIPT` + `PARTIALLY_RECEIVED`，**快照**，不受时间筛选
- `purchase_return_quantity`：库存流水 `PURCHASE_RETURN_OUTBOUND` 的 `|change_quantity|`
- `supplier_refund_amount`：仅 `SupplierRefundRecord.status = SUCCESS`，时间 `COALESCE(received_at, created_at)`

## 库存口径

库存 KPI 是 **当前台账快照**，不按报表日期过滤。流水趋势与仓库期内出入库才用时间范围。

- `total_quantity` = `SUM(quantity)`
- `total_reserved_quantity` = `SUM(reserved_quantity)`
- `total_available_quantity` = `SUM(quantity - reserved_quantity)`，不落库第三份
- **零库存**：`available_quantity == 0`。账面 10、预占 10 也算零可用，因为无可销售库存
- **低库存**：`available_quantity <= low_stock_threshold`（默认 10），且 SKU `ACTIVE`、仓库 `ACTIVE`

列表页 `inventoryStockStatus` 仍把 `quantity == 0` 视为 ZERO，与报表「零可用」略有差别，报表以 available 为准。

## 售后口径

有效售后排除 `REJECTED`、`CANCELLED`。`reason` 当前是自由文本，第一版不做原因 Top N，按 `type` 分布。

退货数量优先 `approved_return_quantity`，空则 `return_quantity`。

## Top N 与趋势

默认 Top 10，最大 20。名称通过 JOIN 一次返回，不循环查。

趋势按 `DATE(created_at)`（或对应业务时间）分组。Service 补齐区间内每一天，缺失填 0，避免折线图断轴。

## 为什么第一版不用汇总表

当前租户数据量和访问量不足以证明实时 `SUM/COUNT/GROUP BY` 不可接受。先把口径做对。

未来若 EXPLAIN 显示全表扫描且查询变慢，再考虑：

1. 为高频 `tenant_id + created_at` 补复合索引（多数主表已有）
2. Redis 短 TTL 缓存 overview
3. 按日汇总表 / 物化视图
4. OLAP / ClickHouse

V13 现有索引已够用：`sales_orders` / `purchase_orders` / `after_sale_orders` / `inventory_transactions` 的 `tenant_id + created_at`，以及库存 `tenant_id + warehouse_id`。未新增汇总表，也未为报表单独加几十个索引。

## 权限

| 编码 | 角色 |
| --- | --- |
| `analytics:overview:read` | OWNER / ADMIN / OPERATOR / WAREHOUSE / VIEWER |
| `analytics:sales:read` | OWNER / ADMIN / OPERATOR / VIEWER |
| `analytics:purchase:read` | OWNER / ADMIN / OPERATOR / VIEWER |
| `analytics:inventory:read` | OWNER / ADMIN / WAREHOUSE / VIEWER |
| `analytics:after_sale:read` | OWNER / ADMIN / VIEWER |

导出沿用对应 read，不另设 `analytics:export`。同步 CSV 仍保留，最大 10000 行。大数据量请走 V14 异步导出：`POST /api/v1/analytics/*/export-tasks` 创建 `REPORT_EXPORT` 任务，结果从任务中心下载。详见 `docs/async-tasks.md`。

## Agent

后续 Copilot 应调用这些受控 API，不要让 Agent 拼统计 SQL。V13 / V14 本身不开发 Agent。

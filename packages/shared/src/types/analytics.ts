/** V13 报表类型。金额为后端 float JSON；前端绘图时转 number。 */

export interface SalesSummary {
  order_count: number;
  completed_order_count: number;
  cancelled_order_count: number;
  draft_order_count: number;
  gross_sales_amount: number;
  refund_amount: number;
  net_sales_amount: number;
  average_order_value: number;
  after_sale_order_count: number;
  after_sale_sales_order_count: number;
  return_rate: number;
}

export interface SalesTrendPoint {
  date: string;
  order_count: number;
  sales_amount: number;
  refund_amount: number;
}

export interface StatusCount {
  status: string;
  count: number;
}

export interface TopSku {
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_id: number;
  product_name: string;
  spec_values: Record<string, unknown>;
  sales_quantity: number;
  sales_amount: number;
  order_count: number;
}

export interface TopProduct {
  product_id: number;
  product_name: string;
  sales_quantity: number;
  sales_amount: number;
  sku_count: number;
}

export interface TopCustomer {
  customer_id: number;
  customer_name: string;
  order_count: number;
  sales_amount: number;
  refund_amount: number;
  net_sales_amount: number;
}

export interface PurchaseSummary {
  purchase_order_count: number;
  purchase_amount: number;
  received_quantity: number;
  pending_receipt_order_count: number;
  purchase_return_order_count: number;
  purchase_return_quantity: number;
  purchase_return_amount: number;
  supplier_refund_amount: number;
}

export interface PurchaseTrendPoint {
  date: string;
  purchase_order_count: number;
  purchase_amount: number;
  received_quantity: number;
  purchase_return_quantity: number;
}

export interface TopSupplier {
  supplier_id: number;
  supplier_name: string;
  purchase_order_count: number;
  purchase_amount: number;
  received_quantity: number;
  purchase_return_quantity: number;
}

export interface InventorySummary {
  inventory_record_count: number;
  sku_count: number;
  warehouse_count: number;
  total_quantity: number;
  total_reserved_quantity: number;
  total_available_quantity: number;
  zero_stock_sku_count: number;
  low_stock_sku_count: number;
  low_stock_threshold: number;
}

export interface WarehouseInventorySummary {
  warehouse_id: number;
  warehouse_name: string;
  sku_count: number;
  quantity: number;
  reserved_quantity: number;
  available_quantity: number;
  inbound_quantity: number;
  outbound_quantity: number;
  transfer_in_quantity: number;
  transfer_out_quantity: number;
  stocktake_adjustment_quantity: number;
}

export interface InventorySkuRow {
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  warehouse_id: number;
  warehouse_name: string;
  quantity: number;
  reserved_quantity: number;
  available_quantity: number;
}

export interface TransactionTrendPoint {
  date: string;
  inbound_quantity: number;
  outbound_quantity: number;
  adjustment_quantity: number;
  transfer_in_quantity: number;
  transfer_out_quantity: number;
}

export interface TransactionTypePoint {
  type: string;
  quantity: number;
}

export interface AfterSaleSummary {
  after_sale_count: number;
  refund_only_count: number;
  return_only_count: number;
  return_and_refund_count: number;
  refund_amount: number;
  return_quantity: number;
  after_sale_rate: number;
  after_sale_sales_order_count: number;
  valid_sales_order_count: number;
}

export interface AfterSaleTrendPoint {
  date: string;
  after_sale_count: number;
  return_quantity: number;
  refund_amount: number;
}

export interface AfterSaleTypeCount {
  type: string;
  count: number;
}

export interface PendingCounts {
  pending_confirmation_order_count: number;
  waiting_outbound_order_count: number;
  pending_receipt_order_count: number;
  pending_after_sale_count: number;
  waiting_refund_after_sale_count: number;
  pending_purchase_return_count: number;
  low_stock_sku_count: number;
  low_stock_threshold: number;
}

export interface AnalyticsOverview {
  sales: SalesSummary;
  purchases: PurchaseSummary;
  inventory: InventorySummary;
  after_sales: AfterSaleSummary;
  pending: PendingCounts;
}

export const ANALYTICS_STALE_TIME_MS = 30_000;

export function formatAnalyticsAmount(value: number | null | undefined): string {
  const amount = Number(value ?? 0);
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatAnalyticsRate(value: number | null | undefined): string {
  const rate = Number(value ?? 0);
  return `${(rate * 100).toFixed(2)}%`;
}

export function toChartNumber(value: number | string | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

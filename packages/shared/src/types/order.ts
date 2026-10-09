/** 与后端客户 / 销售订单 Schema 对齐。确认才预占库存，不减少实际库存。 */

export const CUSTOMER_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const SALES_ORDER_STATUS = {
  draft: 'DRAFT',
  pendingConfirmation: 'PENDING_CONFIRMATION',
  waitingOutbound: 'WAITING_OUTBOUND',
  partiallyOutbound: 'PARTIALLY_OUTBOUND',
  outbounded: 'OUTBOUNDED',
  partiallyShipped: 'PARTIALLY_SHIPPED',
  shipped: 'SHIPPED',
  completed: 'COMPLETED',
  cancelled: 'CANCELLED',
} as const;

export const SALES_ORDER_STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  PENDING_CONFIRMATION: '待确认',
  WAITING_OUTBOUND: '待出库',
  PARTIALLY_OUTBOUND: '部分出库',
  OUTBOUNDED: '已出库',
  PARTIALLY_SHIPPED: '部分发货',
  SHIPPED: '已发货',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
};

export const SALES_ORDER_STATUS_OPTIONS = [
  { value: SALES_ORDER_STATUS.draft, label: '草稿' },
  { value: SALES_ORDER_STATUS.pendingConfirmation, label: '待确认' },
  { value: SALES_ORDER_STATUS.waitingOutbound, label: '待出库' },
  { value: SALES_ORDER_STATUS.partiallyOutbound, label: '部分出库' },
  { value: SALES_ORDER_STATUS.outbounded, label: '已出库' },
  { value: SALES_ORDER_STATUS.partiallyShipped, label: '部分发货' },
  { value: SALES_ORDER_STATUS.shipped, label: '已发货' },
  { value: SALES_ORDER_STATUS.completed, label: '已完成' },
  { value: SALES_ORDER_STATUS.cancelled, label: '已取消' },
];

export const SALES_ORDER_SOURCE = {
  manual: 'MANUAL',
  amazon: 'AMAZON',
  shopify: 'SHOPIFY',
  tiktok: 'TIKTOK',
  other: 'OTHER',
} as const;

export const SALES_ORDER_SOURCE_LABEL: Record<string, string> = {
  MANUAL: '手工',
  AMAZON: 'Amazon',
  SHOPIFY: 'Shopify',
  TIKTOK: 'TikTok',
  OTHER: '其他',
};

export const SALES_ORDER_SOURCE_OPTIONS = [
  { value: SALES_ORDER_SOURCE.manual, label: '手工' },
  { value: SALES_ORDER_SOURCE.amazon, label: 'Amazon' },
  { value: SALES_ORDER_SOURCE.shopify, label: 'Shopify' },
  { value: SALES_ORDER_SOURCE.tiktok, label: 'TikTok' },
  { value: SALES_ORDER_SOURCE.other, label: '其他' },
];

export function salesOrderStatusLabel(status: string): string {
  return SALES_ORDER_STATUS_LABEL[status] ?? status;
}

export function salesOrderSourceLabel(source: string): string {
  return SALES_ORDER_SOURCE_LABEL[source] ?? source;
}

export function customerLocation(customer: Pick<Customer, 'country_code' | 'city'>): string {
  const parts = [customer.country_code, customer.city].filter(Boolean);
  return parts.length ? parts.join(' / ') : '-';
}

export function formatSalesAmount(value: number | null | undefined): string {
  if (value == null) {
    return '-';
  }
  return value.toFixed(2);
}

export function salesLineAmount(quantity: number, unitPrice: number | null | undefined): number | null {
  if (unitPrice == null) {
    return null;
  }
  return Math.round(quantity * unitPrice * 100) / 100;
}

export function canEditSalesOrder(status: string): boolean {
  return status === SALES_ORDER_STATUS.draft;
}

export function canSubmitSalesOrder(status: string): boolean {
  return status === SALES_ORDER_STATUS.draft;
}

export function canConfirmSalesOrder(status: string): boolean {
  return status === SALES_ORDER_STATUS.pendingConfirmation;
}

export function canCancelSalesOrder(status: string): boolean {
  return (
    status === SALES_ORDER_STATUS.draft ||
    status === SALES_ORDER_STATUS.pendingConfirmation ||
    status === SALES_ORDER_STATUS.waitingOutbound
  );
}

export function canCreateOutbound(status: string): boolean {
  return (
    status === SALES_ORDER_STATUS.waitingOutbound ||
    status === SALES_ORDER_STATUS.partiallyOutbound ||
    status === SALES_ORDER_STATUS.partiallyShipped
  );
}

export function formatSalesInventoryShortage(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') {
    return fallback;
  }
  const record = data as { error?: string; items?: Array<Record<string, unknown>> };
  if (record.error !== 'INSUFFICIENT_AVAILABLE_INVENTORY' || !Array.isArray(record.items)) {
    return fallback;
  }
  const lines = record.items
    .map((item) => {
      const code = typeof item.sku_code === 'string' ? item.sku_code : '';
      const available = item.available_quantity;
      const requested = item.requested_quantity;
      if (!code || typeof available !== 'number' || typeof requested !== 'number') {
        return '';
      }
      return `${code} 可用库存 ${available}，订单需要 ${requested}。`;
    })
    .filter(Boolean);
  return lines.length ? lines.join('') : fallback;
}

export interface SalesSkuDraft {
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  quantity: number;
  unit_price: number | null;
  remark?: string | null;
}

export function mergeSalesSkuLine(
  items: SalesSkuDraft[],
  incoming: SalesSkuDraft,
): { items: SalesSkuDraft[]; merged: boolean } {
  const index = items.findIndex((item) => item.sku_id === incoming.sku_id);
  if (index < 0) {
    return { items: [...items, incoming], merged: false };
  }
  const current = items[index];
  const next = [...items];
  next[index] = {
    ...current,
    quantity: current.quantity + incoming.quantity,
    unit_price: incoming.unit_price ?? current.unit_price,
  };
  return { items: next, merged: true };
}

export interface Customer {
  id: number;
  tenant_id: number;
  name: string;
  code: string;
  email: string | null;
  phone: string | null;
  country_code: string | null;
  province: string | null;
  city: string | null;
  address: string | null;
  status: string;
  remark: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerList {
  items: Customer[];
  total: number;
  page: number;
  page_size: number;
}

export interface CustomerCreatePayload {
  name: string;
  code?: string | null;
  email?: string | null;
  phone?: string | null;
  country_code?: string | null;
  province?: string | null;
  city?: string | null;
  address?: string | null;
  remark?: string | null;
  status?: string | null;
}

export interface CustomerUpdatePayload {
  name?: string;
  email?: string | null;
  phone?: string | null;
  country_code?: string | null;
  province?: string | null;
  city?: string | null;
  address?: string | null;
  remark?: string | null;
}

export interface SalesOrderItem {
  id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_id: number;
  product_name: string;
  spec_values: Record<string, unknown>;
  quantity: number;
  unit_price: number | null;
  line_amount: number | null;
  reserved_quantity: number;
  outbound_quantity: number;
  shipped_quantity: number;
  remark: string | null;
  current_quantity: number | null;
  current_reserved_quantity: number | null;
  current_available_quantity: number | null;
}

export interface SalesOrderListItem {
  id: number;
  tenant_id: number;
  order_no: string;
  customer_id: number;
  customer_name: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  source: string;
  external_order_no: string | null;
  currency_code: string;
  sku_count: number;
  total_quantity: number;
  total_amount: number | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface SalesOrderList {
  items: SalesOrderListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface SalesOrderDetail extends SalesOrderListItem {
  recipient_name: string | null;
  recipient_phone: string | null;
  country_code: string | null;
  province: string | null;
  city: string | null;
  address: string | null;
  remark: string | null;
  submitted_at: string | null;
  confirmed_at: string | null;
  confirmed_by: number | null;
  confirmed_by_name: string | null;
  cancelled_at: string | null;
  cancelled_by: number | null;
  cancelled_by_name: string | null;
  cancel_reason: string | null;
  items: SalesOrderItem[];
  picks: SalesOrderPick[];
}

export interface SalesOrderPickLine {
  id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  quantity: number;
  picked_before: number;
  picked_after: number;
}

export interface SalesOrderPick {
  id: number;
  outbound_order_id: number;
  outbound_no: string;
  outbound_status: string;
  picked_at: string;
  picked_by_name: string | null;
  lines: SalesOrderPickLine[];
}

export interface SalesOrderItemInput {
  sku_id: number;
  quantity: number;
  unit_price?: number | null;
  remark?: string | null;
}

export interface SalesOrderCreatePayload {
  customer_id: number;
  warehouse_id: number;
  source?: string | null;
  external_order_no?: string | null;
  currency_code?: string | null;
  recipient_name?: string | null;
  recipient_phone?: string | null;
  country_code?: string | null;
  province?: string | null;
  city?: string | null;
  address?: string | null;
  remark?: string | null;
  items: SalesOrderItemInput[];
}

export interface SalesOrderUpdatePayload extends SalesOrderCreatePayload {}

export interface SkuAvailability {
  warehouse_id: number;
  sku_id: number;
  quantity: number;
  reserved_quantity: number;
  available_quantity: number;
  initialized: boolean;
}

export interface SkuAvailabilityList {
  items: SkuAvailability[];
}

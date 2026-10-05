/** 与后端供应商 / 采购单 Schema 对齐。采购审核不改库存。 */

export const SUPPLIER_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const PURCHASE_ORDER_STATUS = {
  draft: 'DRAFT',
  pendingApproval: 'PENDING_APPROVAL',
  waitingReceipt: 'WAITING_RECEIPT',
  rejected: 'REJECTED',
  cancelled: 'CANCELLED',
} as const;

export const PURCHASE_ORDER_STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  PENDING_APPROVAL: '待审核',
  WAITING_RECEIPT: '待收货',
  REJECTED: '已驳回',
  CANCELLED: '已取消',
};

export const PURCHASE_ORDER_STATUS_OPTIONS = [
  { value: PURCHASE_ORDER_STATUS.draft, label: '草稿' },
  { value: PURCHASE_ORDER_STATUS.pendingApproval, label: '待审核' },
  { value: PURCHASE_ORDER_STATUS.waitingReceipt, label: '待收货' },
  { value: PURCHASE_ORDER_STATUS.rejected, label: '已驳回' },
  { value: PURCHASE_ORDER_STATUS.cancelled, label: '已取消' },
];

export function purchaseOrderStatusLabel(status: string): string {
  return PURCHASE_ORDER_STATUS_LABEL[status] ?? status;
}

export function supplierLocation(supplier: Pick<Supplier, 'country_code' | 'city'>): string {
  const parts = [supplier.country_code, supplier.city].filter(Boolean);
  return parts.length ? parts.join(' / ') : '-';
}

export function formatPurchaseAmount(value: number | null | undefined): string {
  if (value == null) {
    return '-';
  }
  return value.toFixed(2);
}

export function purchaseLineAmount(quantity: number, unitPrice: number | null | undefined): number | null {
  if (unitPrice == null) {
    return null;
  }
  return Math.round(quantity * unitPrice * 100) / 100;
}

export function canEditPurchaseOrder(status: string): boolean {
  return status === PURCHASE_ORDER_STATUS.draft || status === PURCHASE_ORDER_STATUS.rejected;
}

export function canSubmitPurchaseOrder(status: string): boolean {
  return status === PURCHASE_ORDER_STATUS.draft || status === PURCHASE_ORDER_STATUS.rejected;
}

export function canApprovePurchaseOrder(status: string): boolean {
  return status === PURCHASE_ORDER_STATUS.pendingApproval;
}

export function canRejectPurchaseOrder(status: string): boolean {
  return status === PURCHASE_ORDER_STATUS.pendingApproval;
}

export function canCancelPurchaseOrder(status: string): boolean {
  return (
    status === PURCHASE_ORDER_STATUS.draft ||
    status === PURCHASE_ORDER_STATUS.pendingApproval ||
    status === PURCHASE_ORDER_STATUS.rejected
  );
}

export interface PurchaseSkuDraft {
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  quantity: number;
  unit_price: number | null;
  remark?: string | null;
}

export function mergePurchaseSkuLine(
  items: PurchaseSkuDraft[],
  incoming: PurchaseSkuDraft,
): { items: PurchaseSkuDraft[]; merged: boolean } {
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

export interface Supplier {
  id: number;
  tenant_id: number;
  name: string;
  code: string;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  country_code: string | null;
  province: string | null;
  city: string | null;
  address: string | null;
  status: string;
  remark: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupplierList {
  items: Supplier[];
  total: number;
  page: number;
  page_size: number;
}

export interface SupplierCreatePayload {
  name: string;
  code?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  country_code?: string | null;
  province?: string | null;
  city?: string | null;
  address?: string | null;
  remark?: string | null;
  status?: string | null;
}

export interface SupplierUpdatePayload {
  name?: string;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  country_code?: string | null;
  province?: string | null;
  city?: string | null;
  address?: string | null;
  remark?: string | null;
}

export interface PurchaseOrderItem {
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
  received_quantity: number;
  remark: string | null;
}

export interface PurchaseOrderListItem {
  id: number;
  tenant_id: number;
  order_no: string;
  supplier_id: number;
  supplier_name: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  sku_count: number;
  total_quantity: number;
  total_amount: number | null;
  expected_arrival_date: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrderList {
  items: PurchaseOrderListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface PurchaseOrderDetail extends PurchaseOrderListItem {
  remark: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  approved_by: number | null;
  approved_by_name: string | null;
  rejected_at: string | null;
  rejected_by: number | null;
  rejected_by_name: string | null;
  reject_reason: string | null;
  cancelled_at: string | null;
  cancelled_by: number | null;
  cancelled_by_name: string | null;
  cancel_reason: string | null;
  items: PurchaseOrderItem[];
}

export interface PurchaseOrderItemInput {
  sku_id: number;
  quantity: number;
  unit_price?: number | null;
  remark?: string | null;
}

export interface PurchaseOrderCreatePayload {
  supplier_id: number;
  warehouse_id: number;
  expected_arrival_date?: string | null;
  remark?: string | null;
  items: PurchaseOrderItemInput[];
}

export interface PurchaseOrderUpdatePayload {
  supplier_id?: number;
  warehouse_id?: number;
  expected_arrival_date?: string | null;
  remark?: string | null;
  items?: PurchaseOrderItemInput[];
}

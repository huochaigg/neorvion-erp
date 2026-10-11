/** 与后端采购退货 / 出库 / 供应商退款 Schema 对齐。 */

export const PURCHASE_RETURN_SETTLEMENT = {
  refund: 'REFUND',
  noRefund: 'NO_REFUND',
} as const;

export const PURCHASE_RETURN_SETTLEMENT_LABEL: Record<string, string> = {
  REFUND: '退货退款',
  NO_REFUND: '只退货',
};

export const PURCHASE_RETURN_SETTLEMENT_OPTIONS = [
  {
    value: PURCHASE_RETURN_SETTLEMENT.refund,
    label: '退货退款',
    description: '商品退给供应商后，还需要等待供应商返还对应款项。',
  },
  {
    value: PURCHASE_RETURN_SETTLEMENT.noRefund,
    label: '只退货',
    description: '只记录退货和库存减少，不跟踪供应商退款。',
  },
];

export const PURCHASE_RETURN_STATUS = {
  draft: 'DRAFT',
  pendingApproval: 'PENDING_APPROVAL',
  waitingOutbound: 'WAITING_OUTBOUND',
  partiallyReturned: 'PARTIALLY_RETURNED',
  waitingRefund: 'WAITING_REFUND',
  completed: 'COMPLETED',
  rejected: 'REJECTED',
  cancelled: 'CANCELLED',
} as const;

export const PURCHASE_RETURN_STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  PENDING_APPROVAL: '待审核',
  WAITING_OUTBOUND: '待出库',
  PARTIALLY_RETURNED: '部分退货',
  WAITING_REFUND: '待退款',
  COMPLETED: '已完成',
  REJECTED: '已拒绝',
  CANCELLED: '已取消',
};

export const PURCHASE_RETURN_STATUS_OPTIONS = [
  { value: PURCHASE_RETURN_STATUS.draft, label: '草稿' },
  { value: PURCHASE_RETURN_STATUS.pendingApproval, label: '待审核' },
  { value: PURCHASE_RETURN_STATUS.waitingOutbound, label: '待出库' },
  { value: PURCHASE_RETURN_STATUS.partiallyReturned, label: '部分退货' },
  { value: PURCHASE_RETURN_STATUS.waitingRefund, label: '待退款' },
  { value: PURCHASE_RETURN_STATUS.completed, label: '已完成' },
  { value: PURCHASE_RETURN_STATUS.rejected, label: '已拒绝' },
  { value: PURCHASE_RETURN_STATUS.cancelled, label: '已取消' },
];

export const PURCHASE_RETURN_REFUND_STATUS = {
  none: 'NONE',
  pending: 'PENDING',
  success: 'SUCCESS',
} as const;

export const PURCHASE_RETURN_REFUND_STATUS_LABEL: Record<string, string> = {
  NONE: '无需退款',
  PENDING: '待退款',
  SUCCESS: '退款成功',
};

export const PURCHASE_RETURN_REFUND_STATUS_OPTIONS = [
  { value: PURCHASE_RETURN_REFUND_STATUS.none, label: '无需退款' },
  { value: PURCHASE_RETURN_REFUND_STATUS.pending, label: '待退款' },
  { value: PURCHASE_RETURN_REFUND_STATUS.success, label: '退款成功' },
];

export const PURCHASE_RETURN_OUTBOUND_STATUS = {
  draft: 'DRAFT',
  confirmed: 'CONFIRMED',
  cancelled: 'CANCELLED',
} as const;

export const PURCHASE_RETURN_OUTBOUND_STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  CONFIRMED: '已确认',
  CANCELLED: '已取消',
};

export const SUPPLIER_REFUND_RECORD_STATUS = {
  pending: 'PENDING',
  success: 'SUCCESS',
  failed: 'FAILED',
} as const;

export const SUPPLIER_REFUND_RECORD_STATUS_LABEL: Record<string, string> = {
  PENDING: '待确认',
  SUCCESS: '成功',
  FAILED: '失败',
};

export function purchaseReturnSettlementLabel(type: string): string {
  return PURCHASE_RETURN_SETTLEMENT_LABEL[type] ?? type;
}

export function purchaseReturnStatusLabel(status: string): string {
  return PURCHASE_RETURN_STATUS_LABEL[status] ?? status;
}

export function purchaseReturnRefundStatusLabel(status: string): string {
  return PURCHASE_RETURN_REFUND_STATUS_LABEL[status] ?? status;
}

export function purchaseReturnOutboundStatusLabel(status: string): string {
  return PURCHASE_RETURN_OUTBOUND_STATUS_LABEL[status] ?? status;
}

export function supplierRefundRecordStatusLabel(status: string): string {
  return SUPPLIER_REFUND_RECORD_STATUS_LABEL[status] ?? status;
}

export function canCreatePurchaseReturn(purchaseStatus: string): boolean {
  return purchaseStatus === 'PARTIALLY_RECEIVED' || purchaseStatus === 'RECEIVED';
}

export function canEditPurchaseReturn(status: string): boolean {
  return status === PURCHASE_RETURN_STATUS.draft;
}

export function canSubmitPurchaseReturn(status: string): boolean {
  return status === PURCHASE_RETURN_STATUS.draft;
}

export function canApprovePurchaseReturn(status: string): boolean {
  return status === PURCHASE_RETURN_STATUS.pendingApproval;
}

export function canRejectPurchaseReturn(status: string): boolean {
  return status === PURCHASE_RETURN_STATUS.pendingApproval;
}

export function canCancelPurchaseReturn(status: string): boolean {
  return status === PURCHASE_RETURN_STATUS.draft || status === PURCHASE_RETURN_STATUS.pendingApproval;
}

export function canCreatePurchaseReturnOutbound(status: string): boolean {
  return (
    status === PURCHASE_RETURN_STATUS.waitingOutbound ||
    status === PURCHASE_RETURN_STATUS.partiallyReturned
  );
}

export function canConfirmPurchaseReturnOutbound(status: string): boolean {
  return status === PURCHASE_RETURN_OUTBOUND_STATUS.draft;
}

export function canCreateSupplierRefund(status: string, settlementType: string): boolean {
  return (
    status === PURCHASE_RETURN_STATUS.waitingRefund &&
    settlementType === PURCHASE_RETURN_SETTLEMENT.refund
  );
}

export function canConfirmSupplierRefund(status: string): boolean {
  return status === SUPPLIER_REFUND_RECORD_STATUS.pending;
}

export function defaultOutboundQuantity(remaining: number, available: number): number {
  return Math.max(Math.min(remaining, available), 0);
}

export interface PurchaseReturnPreviewItem {
  purchase_order_item_id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  ordered_quantity: number;
  received_quantity: number;
  occupied_return_quantity: number;
  returned_quantity: number;
  returnable_quantity: number;
  unit_price: number | null;
  occupied_refund_amount: number;
  refundable_amount: number;
  inventory_quantity: number;
  inventory_reserved: number;
  inventory_available: number;
}

export interface PurchaseReturnPreview {
  purchase_order_id: number;
  purchase_order_no: string;
  supplier_id: number;
  supplier_name: string;
  original_warehouse_id: number;
  original_warehouse_name: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  eligible: boolean;
  items: PurchaseReturnPreviewItem[];
}

export interface PurchaseReturnItem {
  id: number;
  purchase_order_item_id: number;
  purchase_receipt_item_id: number | null;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  original_ordered_quantity: number;
  original_received_quantity: number;
  requested_return_quantity: number;
  approved_return_quantity: number | null;
  returned_quantity: number;
  remaining_return_quantity: number;
  inventory_quantity: number;
  inventory_reserved: number;
  inventory_available: number;
  requested_refund_amount: number | null;
  approved_refund_amount: number | null;
  unit_price: number | null;
  reason: string | null;
}

export interface PurchaseReturnOutboundItemBrief {
  id: number;
  purchase_return_item_id: number;
  sku_id: number;
  sku_code: string;
  quantity: number;
}

export interface PurchaseReturnOutboundBrief {
  id: number;
  outbound_no: string;
  warehouse_id: number;
  status: string;
  remark: string | null;
  confirmed_at: string | null;
  confirmed_by: number | null;
  created_at: string;
  items: PurchaseReturnOutboundItemBrief[];
}

export interface SupplierRefundBrief {
  id: number;
  refund_no: string;
  amount: number;
  status: string;
  external_reference_no: string | null;
  failure_reason: string | null;
  received_at: string | null;
  created_at: string;
}

export interface PurchaseReturnDetail {
  id: number;
  purchase_return_no: string;
  purchase_order_id: number;
  purchase_order_no: string;
  supplier_id: number;
  supplier_name: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  settlement_type: string;
  reason: string;
  description: string | null;
  requested_refund_amount: number;
  approved_refund_amount: number | null;
  refund_status: string;
  sku_count: number;
  requested_return_quantity: number;
  approved_return_quantity: number | null;
  returned_quantity: number;
  created_by: number;
  created_by_name: string | null;
  approved_by: number | null;
  approved_by_name: string | null;
  approved_at: string | null;
  rejected_by: number | null;
  rejected_at: string | null;
  reject_reason: string | null;
  outbound_at: string | null;
  outbound_by: number | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancelled_by: number | null;
  created_at: string;
  updated_at: string;
  items: PurchaseReturnItem[];
  outbounds: PurchaseReturnOutboundBrief[];
  refunds: SupplierRefundBrief[];
}

export interface PurchaseReturnListItem {
  id: number;
  purchase_return_no: string;
  purchase_order_id: number;
  purchase_order_no: string;
  supplier_id: number;
  supplier_name: string;
  warehouse_id: number;
  warehouse_name: string;
  sku_count: number;
  requested_return_quantity: number;
  approved_return_quantity: number | null;
  returned_quantity: number;
  requested_refund_amount: number;
  approved_refund_amount: number | null;
  status: string;
  settlement_type: string;
  refund_status: string;
  created_at: string;
}

export interface PurchaseReturnList {
  items: PurchaseReturnListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface PurchaseReturnItemInput {
  purchase_order_item_id: number;
  purchase_receipt_item_id?: number | null;
  requested_return_quantity: number;
  requested_refund_amount?: number | null;
  reason?: string | null;
}

export interface PurchaseReturnCreatePayload {
  purchase_order_id: number;
  warehouse_id?: number | null;
  settlement_type: string;
  reason: string;
  description?: string | null;
  items: PurchaseReturnItemInput[];
}

export interface PurchaseReturnApproveItemInput {
  item_id: number;
  approved_return_quantity: number;
  approved_refund_amount: number;
}

export interface PurchaseReturnApprovePayload {
  items: PurchaseReturnApproveItemInput[];
}

export interface PurchaseReturnRejectPayload {
  reason: string;
}

export interface PurchaseReturnOutboundItem {
  id: number;
  purchase_return_item_id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  quantity: number;
  approved_return_quantity: number;
  already_returned_quantity: number;
  remaining_return_quantity: number;
  inventory_available: number;
}

export interface PurchaseReturnOutboundDetail {
  id: number;
  outbound_no: string;
  purchase_return_id: number;
  purchase_return_no: string;
  purchase_order_id: number;
  purchase_order_no: string;
  supplier_id: number;
  supplier_name: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  remark: string | null;
  confirmed_at: string | null;
  confirmed_by: number | null;
  confirmed_by_name: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
  items: PurchaseReturnOutboundItem[];
}

export interface PurchaseReturnOutboundListItem {
  id: number;
  outbound_no: string;
  purchase_return_id: number;
  purchase_return_no: string;
  purchase_order_no: string;
  supplier_name: string;
  warehouse_name: string;
  status: string;
  total_quantity: number;
  confirmed_at: string | null;
  created_at: string;
}

export interface PurchaseReturnOutboundList {
  items: PurchaseReturnOutboundListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface PurchaseReturnOutboundCreatePayload {
  remark?: string | null;
  items: { purchase_return_item_id: number; quantity: number }[];
}

export interface SupplierRefundRecord {
  id: number;
  refund_no: string;
  purchase_return_id: number;
  purchase_return_no: string;
  purchase_order_id: number;
  purchase_order_no: string;
  supplier_id: number;
  supplier_name: string;
  amount: number;
  status: string;
  external_reference_no: string | null;
  failure_reason: string | null;
  received_at: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupplierRefundList {
  items: SupplierRefundRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface SupplierRefundCreatePayload {
  amount?: number | null;
  external_reference_no?: string | null;
}

export interface SupplierRefundConfirmPayload {
  external_reference_no?: string | null;
  received_at?: string | null;
}

export interface SupplierRefundFailPayload {
  failure_reason: string;
}

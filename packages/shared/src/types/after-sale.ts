/** 与后端售后 Schema 对齐。售后是独立领域，不改 SalesOrderItem.quantity。 */

export const AFTER_SALE_TYPE = {
  refundOnly: 'REFUND_ONLY',
  returnAndRefund: 'RETURN_AND_REFUND',
  returnOnly: 'RETURN_ONLY',
} as const;

export const AFTER_SALE_TYPE_LABEL: Record<string, string> = {
  REFUND_ONLY: '仅退款',
  RETURN_AND_REFUND: '退货退款',
  RETURN_ONLY: '仅退货',
};

export const AFTER_SALE_TYPE_OPTIONS = [
  { value: AFTER_SALE_TYPE.refundOnly, label: '仅退款', description: '仅退款，不要求客户退回商品。' },
  {
    value: AFTER_SALE_TYPE.returnAndRefund,
    label: '退货退款',
    description: '客户退回商品，退货入库完成后执行退款。',
  },
  { value: AFTER_SALE_TYPE.returnOnly, label: '仅退货', description: '只记录退货和库存回收，不执行退款。' },
];

export const AFTER_SALE_STATUS = {
  pendingApproval: 'PENDING_APPROVAL',
  rejected: 'REJECTED',
  waitingReturn: 'WAITING_RETURN',
  waitingRefund: 'WAITING_REFUND',
  completed: 'COMPLETED',
  cancelled: 'CANCELLED',
} as const;

export const AFTER_SALE_STATUS_LABEL: Record<string, string> = {
  PENDING_APPROVAL: '待审核',
  REJECTED: '已拒绝',
  WAITING_RETURN: '待退货',
  WAITING_REFUND: '待退款',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
};

export const AFTER_SALE_STATUS_OPTIONS = [
  { value: AFTER_SALE_STATUS.pendingApproval, label: '待审核' },
  { value: AFTER_SALE_STATUS.rejected, label: '已拒绝' },
  { value: AFTER_SALE_STATUS.waitingReturn, label: '待退货' },
  { value: AFTER_SALE_STATUS.waitingRefund, label: '待退款' },
  { value: AFTER_SALE_STATUS.completed, label: '已完成' },
  { value: AFTER_SALE_STATUS.cancelled, label: '已取消' },
];

export const AFTER_SALE_REFUND_STATUS = {
  none: 'NONE',
  pending: 'PENDING',
  success: 'SUCCESS',
} as const;

export const AFTER_SALE_REFUND_STATUS_LABEL: Record<string, string> = {
  NONE: '无需退款',
  PENDING: '待退款',
  SUCCESS: '退款成功',
};

export const AFTER_SALE_REFUND_STATUS_OPTIONS = [
  { value: AFTER_SALE_REFUND_STATUS.none, label: '无需退款' },
  { value: AFTER_SALE_REFUND_STATUS.pending, label: '待退款' },
  { value: AFTER_SALE_REFUND_STATUS.success, label: '退款成功' },
];

export function afterSaleTypeLabel(type: string): string {
  return AFTER_SALE_TYPE_LABEL[type] ?? type;
}

export function afterSaleStatusLabel(status: string): string {
  return AFTER_SALE_STATUS_LABEL[status] ?? status;
}

export function afterSaleRefundStatusLabel(status: string): string {
  return AFTER_SALE_REFUND_STATUS_LABEL[status] ?? status;
}

export function canApproveAfterSale(status: string): boolean {
  return status === AFTER_SALE_STATUS.pendingApproval;
}

export function canRejectAfterSale(status: string): boolean {
  return status === AFTER_SALE_STATUS.pendingApproval;
}

export function canCancelAfterSale(status: string): boolean {
  return status === AFTER_SALE_STATUS.pendingApproval;
}

export function canCreateRefund(status: string, type: string): boolean {
  return status === AFTER_SALE_STATUS.waitingRefund && type !== AFTER_SALE_TYPE.returnOnly;
}

export interface AfterSalePreviewItem {
  sales_order_item_id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  original_quantity: number;
  outbound_quantity: number;
  occupied_return_quantity: number;
  returnable_quantity: number;
  unit_price: number | null;
  occupied_refund_amount: number;
  refundable_amount: number;
}

export interface AfterSalePreview {
  sales_order_id: number;
  sales_order_no: string;
  customer_id: number;
  customer_name: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  currency_code: string;
  total_amount: number | null;
  eligible: boolean;
  items: AfterSalePreviewItem[];
}

export interface AfterSaleItem {
  id: number;
  sales_order_item_id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  original_quantity: number;
  outbound_quantity: number;
  return_quantity: number;
  approved_return_quantity: number | null;
  requested_refund_amount: number;
  approved_refund_amount: number | null;
  reason: string | null;
}

export interface AfterSaleDetail {
  id: number;
  after_sale_no: string;
  sales_order_id: number;
  sales_order_no: string;
  customer_id: number;
  customer_name: string;
  type: string;
  status: string;
  reason: string;
  description: string | null;
  currency_code: string;
  requested_refund_amount: number;
  approved_refund_amount: number | null;
  refund_status: string;
  return_quantity: number;
  requested_by: number;
  requested_by_name: string | null;
  approved_by: number | null;
  approved_by_name: string | null;
  approved_at: string | null;
  rejected_by: number | null;
  rejected_at: string | null;
  reject_reason: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancelled_by: number | null;
  created_at: string;
  updated_at: string;
  return_order_id: number | null;
  items: AfterSaleItem[];
}

export interface AfterSaleListItem {
  id: number;
  after_sale_no: string;
  sales_order_id: number;
  sales_order_no: string;
  customer_id: number;
  customer_name: string;
  type: string;
  status: string;
  refund_status: string;
  return_quantity: number;
  requested_refund_amount: number;
  approved_refund_amount: number | null;
  requested_by_name: string | null;
  created_at: string;
}

export interface AfterSaleList {
  items: AfterSaleListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AfterSaleItemInput {
  sales_order_item_id: number;
  return_quantity: number;
  requested_refund_amount: number;
  reason?: string | null;
}

export interface AfterSaleCreatePayload {
  sales_order_id: number;
  type: string;
  reason: string;
  description?: string | null;
  items: AfterSaleItemInput[];
}

export interface AfterSaleApproveItemInput {
  item_id: number;
  approved_return_quantity: number;
  approved_refund_amount: number;
}

export interface AfterSaleApprovePayload {
  warehouse_id?: number | null;
  items: AfterSaleApproveItemInput[];
}

export interface AfterSaleRejectPayload {
  reason: string;
}

/** 与后端退款记录 Schema 对齐。V11 只做 ERP 内人工确认，不接真实支付渠道。 */

export const REFUND_RECORD_STATUS = {
  pending: 'PENDING',
  success: 'SUCCESS',
  failed: 'FAILED',
} as const;

export const REFUND_RECORD_STATUS_LABEL: Record<string, string> = {
  PENDING: '待确认',
  SUCCESS: '成功',
  FAILED: '失败',
};

export const REFUND_RECORD_STATUS_OPTIONS = [
  { value: REFUND_RECORD_STATUS.pending, label: '待确认' },
  { value: REFUND_RECORD_STATUS.success, label: '成功' },
  { value: REFUND_RECORD_STATUS.failed, label: '失败' },
];

export function refundRecordStatusLabel(status: string): string {
  return REFUND_RECORD_STATUS_LABEL[status] ?? status;
}

export function canConfirmRefundRecord(status: string): boolean {
  return status === REFUND_RECORD_STATUS.pending;
}

export function canFailRefundRecord(status: string): boolean {
  return status === REFUND_RECORD_STATUS.pending;
}

export interface RefundRecord {
  id: number;
  refund_no: string;
  after_sale_order_id: number;
  after_sale_no: string;
  sales_order_id: number;
  sales_order_no: string;
  customer_id: number;
  customer_name: string;
  amount: number;
  status: string;
  external_reference_no: string | null;
  failure_reason: string | null;
  refunded_at: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface RefundList {
  items: RefundRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface RefundCreatePayload {
  amount?: number | null;
  external_reference_no?: string | null;
  remark?: string | null;
}

export interface RefundConfirmPayload {
  external_reference_no?: string | null;
  refunded_at?: string | null;
  remark?: string | null;
}

export interface RefundFailPayload {
  failure_reason: string;
}

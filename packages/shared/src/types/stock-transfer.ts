/** 与后端调拨 Schema 对齐。调出扣源仓，调入加目标仓，中间是在途。 */

export const STOCK_TRANSFER_STATUS = {
  draft: 'DRAFT',
  pendingOutbound: 'PENDING_OUTBOUND',
  inTransit: 'IN_TRANSIT',
  completed: 'COMPLETED',
  cancelled: 'CANCELLED',
} as const;

export const STOCK_TRANSFER_STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  PENDING_OUTBOUND: '待调出',
  IN_TRANSIT: '运输中',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
};

export const STOCK_TRANSFER_STATUS_OPTIONS = [
  { value: STOCK_TRANSFER_STATUS.draft, label: '草稿' },
  { value: STOCK_TRANSFER_STATUS.pendingOutbound, label: '待调出' },
  { value: STOCK_TRANSFER_STATUS.inTransit, label: '运输中' },
  { value: STOCK_TRANSFER_STATUS.completed, label: '已完成' },
  { value: STOCK_TRANSFER_STATUS.cancelled, label: '已取消' },
];

export function stockTransferStatusLabel(status: string): string {
  return STOCK_TRANSFER_STATUS_LABEL[status] ?? status;
}

export function canEditStockTransfer(status: string): boolean {
  return status === STOCK_TRANSFER_STATUS.draft;
}

export function canSubmitStockTransfer(status: string, hasItems: boolean): boolean {
  return status === STOCK_TRANSFER_STATUS.draft && hasItems;
}

export function canConfirmTransferOutbound(status: string): boolean {
  return status === STOCK_TRANSFER_STATUS.pendingOutbound;
}

export function canConfirmTransferReceive(status: string): boolean {
  return status === STOCK_TRANSFER_STATUS.inTransit;
}

export function canCancelStockTransfer(status: string): boolean {
  return status === STOCK_TRANSFER_STATUS.draft || status === STOCK_TRANSFER_STATUS.pendingOutbound;
}

export function transferStepIndex(status: string): number {
  if (status === STOCK_TRANSFER_STATUS.draft) {
    return 0;
  }
  if (status === STOCK_TRANSFER_STATUS.pendingOutbound) {
    return 1;
  }
  if (status === STOCK_TRANSFER_STATUS.inTransit) {
    return 2;
  }
  if (status === STOCK_TRANSFER_STATUS.completed) {
    return 3;
  }
  return 0;
}

export interface StockTransferItem {
  id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  quantity: number;
  outbound_quantity: number;
  received_quantity: number;
  source_quantity: number | null;
  source_reserved_quantity: number | null;
  source_available_quantity: number | null;
}

export interface StockTransferDetail {
  id: number;
  transfer_no: string;
  source_warehouse_id: number;
  source_warehouse_name: string;
  target_warehouse_id: number;
  target_warehouse_name: string;
  status: string;
  remark: string | null;
  sku_count: number;
  total_quantity: number;
  created_by: number;
  created_by_name: string | null;
  submitted_at: string | null;
  outbound_at: string | null;
  outbound_by: number | null;
  outbound_by_name: string | null;
  received_at: string | null;
  received_by: number | null;
  received_by_name: string | null;
  cancelled_at: string | null;
  cancelled_by: number | null;
  created_at: string;
  updated_at: string;
  items: StockTransferItem[];
}

export interface StockTransferListItem {
  id: number;
  transfer_no: string;
  source_warehouse_id: number;
  source_warehouse_name: string;
  target_warehouse_id: number;
  target_warehouse_name: string;
  status: string;
  sku_count: number;
  total_quantity: number;
  created_by_name: string | null;
  created_at: string;
}

export interface StockTransferList {
  items: StockTransferListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface StockTransferItemInput {
  sku_id: number;
  quantity: number;
}

export interface StockTransferCreatePayload {
  source_warehouse_id: number;
  target_warehouse_id: number;
  remark?: string | null;
  items: StockTransferItemInput[];
}

export interface TransferSkuDraft {
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  quantity: number;
}

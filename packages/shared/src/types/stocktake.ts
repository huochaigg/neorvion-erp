/** 与后端盘点 Schema 对齐。确认时按差异调整当前库存，不覆盖成实盘数。 */

export const STOCKTAKE_STATUS = {
  draft: 'DRAFT',
  counting: 'COUNTING',
  pendingConfirmation: 'PENDING_CONFIRMATION',
  confirmed: 'CONFIRMED',
  cancelled: 'CANCELLED',
} as const;

export const STOCKTAKE_STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  COUNTING: '盘点中',
  PENDING_CONFIRMATION: '待确认',
  CONFIRMED: '已确认',
  CANCELLED: '已取消',
};

export const STOCKTAKE_STATUS_OPTIONS = [
  { value: STOCKTAKE_STATUS.counting, label: '盘点中' },
  { value: STOCKTAKE_STATUS.pendingConfirmation, label: '待确认' },
  { value: STOCKTAKE_STATUS.confirmed, label: '已确认' },
  { value: STOCKTAKE_STATUS.cancelled, label: '已取消' },
];

export const STOCKTAKE_SCOPE = {
  all: 'ALL',
  selectedSku: 'SELECTED_SKU',
} as const;

export const STOCKTAKE_SCOPE_LABEL: Record<string, string> = {
  ALL: '整仓盘点',
  SELECTED_SKU: '指定 SKU',
};

export function stocktakeStatusLabel(status: string): string {
  return STOCKTAKE_STATUS_LABEL[status] ?? status;
}

export function stocktakeScopeLabel(scope: string): string {
  return STOCKTAKE_SCOPE_LABEL[scope] ?? scope;
}

export function canEditStocktakeCount(status: string): boolean {
  return status === STOCKTAKE_STATUS.counting;
}

export function canSubmitStocktake(status: string, allCounted: boolean): boolean {
  return status === STOCKTAKE_STATUS.counting && allCounted;
}

export function canConfirmStocktake(status: string): boolean {
  return status === STOCKTAKE_STATUS.pendingConfirmation;
}

export function canCancelStocktake(status: string): boolean {
  return (
    status === STOCKTAKE_STATUS.draft ||
    status === STOCKTAKE_STATUS.counting ||
    status === STOCKTAKE_STATUS.pendingConfirmation
  );
}

export function stocktakeDifference(counted: number | null, systemQuantity: number): number | null {
  if (counted == null) {
    return null;
  }
  return counted - systemQuantity;
}

export function stocktakeDifferenceText(difference: number | null): string {
  if (difference == null) {
    return '未盘';
  }
  if (difference > 0) {
    return `盘盈 ${difference}`;
  }
  if (difference < 0) {
    return `盘亏 ${Math.abs(difference)}`;
  }
  return '一致';
}

export interface StocktakeItem {
  id: number;
  inventory_id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  system_quantity: number;
  system_reserved_quantity: number;
  system_available_quantity: number;
  counted_quantity: number | null;
  difference_quantity: number | null;
  remark: string | null;
}

export interface StocktakeDetail {
  id: number;
  stocktake_no: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  scope: string;
  remark: string | null;
  sku_count: number;
  counted_sku_count: number;
  difference_sku_count: number;
  created_by: number;
  created_by_name: string | null;
  submitted_at: string | null;
  confirmed_at: string | null;
  confirmed_by: number | null;
  confirmed_by_name: string | null;
  cancelled_at: string | null;
  cancelled_by: number | null;
  created_at: string;
  updated_at: string;
  items: StocktakeItem[];
}

export interface StocktakeListItem {
  id: number;
  stocktake_no: string;
  warehouse_id: number;
  warehouse_name: string;
  scope: string;
  status: string;
  sku_count: number;
  difference_sku_count: number;
  created_by_name: string | null;
  created_at: string;
}

export interface StocktakeList {
  items: StocktakeListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface StocktakeCreatePayload {
  warehouse_id: number;
  scope: string;
  sku_ids?: number[];
  remark?: string | null;
}

export interface StocktakeItemSavePayload {
  item_id: number;
  counted_quantity: number;
  remark?: string | null;
}

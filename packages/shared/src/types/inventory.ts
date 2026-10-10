/** 与后端库存 Schema 对齐。可用库存不落库，等于 quantity - reserved_quantity。 */

export const INVENTORY_STOCK_STATUS = {
  inStock: 'IN_STOCK',
  zero: 'ZERO',
  low: 'LOW',
} as const;

export const INVENTORY_TRANSACTION_TYPE = {
  initialize: 'INITIALIZE',
  adjustIn: 'ADJUST_IN',
  adjustOut: 'ADJUST_OUT',
  reserve: 'RESERVE',
  release: 'RELEASE',
  inbound: 'INBOUND',
  outbound: 'OUTBOUND',
  stocktakeAdjustment: 'STOCKTAKE_ADJUSTMENT',
  transferOut: 'TRANSFER_OUT',
  transferIn: 'TRANSFER_IN',
} as const;

export const INVENTORY_TRANSACTION_TYPE_LABEL: Record<string, string> = {
  INITIALIZE: '初始化',
  ADJUST_IN: '库存增加',
  ADJUST_OUT: '库存减少',
  RESERVE: '预占',
  RELEASE: '释放',
  INBOUND: '入库',
  OUTBOUND: '出库',
  STOCKTAKE_ADJUSTMENT: '盘点调整',
  TRANSFER_OUT: '调拨调出',
  TRANSFER_IN: '调拨调入',
};

export const INVENTORY_TRANSACTION_TYPE_OPTIONS = [
  { value: INVENTORY_TRANSACTION_TYPE.initialize, label: '初始化' },
  { value: INVENTORY_TRANSACTION_TYPE.adjustIn, label: '库存增加' },
  { value: INVENTORY_TRANSACTION_TYPE.adjustOut, label: '库存减少' },
  { value: INVENTORY_TRANSACTION_TYPE.reserve, label: '预占' },
  { value: INVENTORY_TRANSACTION_TYPE.release, label: '释放' },
  { value: INVENTORY_TRANSACTION_TYPE.inbound, label: '入库' },
  { value: INVENTORY_TRANSACTION_TYPE.outbound, label: '出库' },
  { value: INVENTORY_TRANSACTION_TYPE.stocktakeAdjustment, label: '盘点调整' },
  { value: INVENTORY_TRANSACTION_TYPE.transferOut, label: '调拨调出' },
  { value: INVENTORY_TRANSACTION_TYPE.transferIn, label: '调拨调入' },
];

export function inventoryTransactionTypeLabel(type: string): string {
  return INVENTORY_TRANSACTION_TYPE_LABEL[type] ?? type;
}

export function specValuesLabel(specValues: Record<string, unknown> | null | undefined): string {
  if (!specValues) {
    return '-';
  }
  const parts = Object.entries(specValues)
    .filter(([, value]) => value != null && String(value).trim() !== '')
    .map(([key, value]) => `${key}:${String(value)}`);
  return parts.length ? parts.join(' / ') : '-';
}

export function inventoryStockStatus(item: {
  quantity: number;
  available_quantity: number;
  threshold?: number;
}): 'ZERO' | 'LOW' | 'IN_STOCK' {
  if (item.quantity === 0 || item.available_quantity <= 0) {
    return 'ZERO';
  }
  const threshold = item.threshold ?? 10;
  if (item.available_quantity <= threshold) {
    return 'LOW';
  }
  return 'IN_STOCK';
}

export function canAdjustOut(available: number, quantity: number): boolean {
  return quantity > 0 && quantity <= available;
}

export interface InventoryItem {
  id: number;
  tenant_id: number;
  warehouse_id: number;
  warehouse_name: string;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_id: number;
  product_name: string;
  spec_values: Record<string, unknown>;
  quantity: number;
  reserved_quantity: number;
  available_quantity: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface InventoryList {
  items: InventoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface InventoryTransaction {
  id: number;
  tenant_id: number;
  inventory_id: number;
  warehouse_id: number;
  warehouse_name: string;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  type: string;
  change_quantity: number;
  before_quantity: number;
  after_quantity: number;
  before_reserved_quantity: number;
  after_reserved_quantity: number;
  reference_type: string | null;
  reference_id: number | null;
  remark: string | null;
  operator_user_id: number | null;
  operator_name: string | null;
  created_at: string;
}

export interface InventoryTransactionList {
  items: InventoryTransaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface InventoryDetail extends InventoryItem {
  recent_transactions: InventoryTransaction[];
}

export interface InventoryInitializePayload {
  warehouse_id: number;
  sku_id: number;
  quantity: number;
  remark?: string | null;
}

export interface InventoryAdjustPayload {
  type: 'ADJUST_IN' | 'ADJUST_OUT';
  quantity: number;
  remark?: string | null;
}

export interface SkuOption {
  id: number;
  tenant_id: number;
  product_id: number;
  product_name: string;
  sku_code: string;
  name: string;
  spec_values: Record<string, unknown>;
  status: string;
}

export interface SkuOptionList {
  items: SkuOption[];
  total: number;
  page: number;
  page_size: number;
}

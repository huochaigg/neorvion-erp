/** 与后端仓库模块 Schema 对齐。V4 只存仓库档案，不存库存数量。 */

export const WAREHOUSE_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const WAREHOUSE_TYPE = {
  domestic: 'DOMESTIC',
  overseas: 'OVERSEAS',
  fba: 'FBA',
  thirdParty: 'THIRD_PARTY',
  other: 'OTHER',
} as const;

export const WAREHOUSE_TYPE_LABEL: Record<string, string> = {
  DOMESTIC: '国内仓',
  OVERSEAS: '海外仓',
  FBA: 'FBA',
  THIRD_PARTY: '第三方仓',
  OTHER: '其他',
};

export const WAREHOUSE_TYPE_OPTIONS = [
  { value: WAREHOUSE_TYPE.domestic, label: '国内仓' },
  { value: WAREHOUSE_TYPE.overseas, label: '海外仓' },
  { value: WAREHOUSE_TYPE.fba, label: 'FBA' },
  { value: WAREHOUSE_TYPE.thirdParty, label: '第三方仓' },
  { value: WAREHOUSE_TYPE.other, label: '其他' },
];

export function warehouseTypeLabel(type: string): string {
  return WAREHOUSE_TYPE_LABEL[type] ?? type;
}

export interface Warehouse {
  id: number;
  tenant_id: number;
  name: string;
  code: string;
  type: string;
  country_code: string | null;
  province: string | null;
  city: string | null;
  address: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  is_default: boolean;
  status: string;
  remark: string | null;
  created_at: string;
  updated_at: string;
}

export interface WarehouseList {
  items: Warehouse[];
  total: number;
  page: number;
  page_size: number;
}

export interface WarehouseCreatePayload {
  name: string;
  code?: string | null;
  type: string;
  country_code?: string | null;
  province?: string | null;
  city?: string | null;
  address?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  remark?: string | null;
}

export interface WarehouseUpdatePayload {
  name?: string;
  type?: string;
  country_code?: string | null;
  province?: string | null;
  city?: string | null;
  address?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  remark?: string | null;
}

export function warehouseLocation(warehouse: Pick<Warehouse, 'country_code' | 'city'>): string {
  const parts = [warehouse.country_code, warehouse.city].filter(Boolean);
  return parts.length ? parts.join(' / ') : '-';
}

export function canSetWarehouseDefault(warehouse: Pick<Warehouse, 'is_default' | 'status'>): boolean {
  return !warehouse.is_default && warehouse.status === WAREHOUSE_STATUS.active;
}

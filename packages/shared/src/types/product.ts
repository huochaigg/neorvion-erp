/** 与后端商品模块 Schema 对齐。 */

export const CATALOG_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const PRODUCT_STATUS = {
  draft: 'DRAFT',
  active: 'ACTIVE',
  inactive: 'INACTIVE',
} as const;

export const SKU_STATUS = {
  active: 'ACTIVE',
  inactive: 'INACTIVE',
} as const;

export interface ProductCategory {
  id: number;
  tenant_id: number;
  name: string;
  parent_id: number | null;
  level: number;
  sort: number;
  status: string;
  created_at: string;
  updated_at: string;
  children: ProductCategory[];
}

export interface ProductCategoryCreatePayload {
  name: string;
  parent_id?: number | null;
  sort?: number;
}

export interface ProductCategoryUpdatePayload {
  name?: string;
  sort?: number;
  status?: string;
}

export interface Brand {
  id: number;
  tenant_id: number;
  name: string;
  code: string;
  logo_url: string | null;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface BrandList {
  items: Brand[];
  total: number;
  page: number;
  page_size: number;
}

export interface BrandCreatePayload {
  name: string;
  code: string;
  logo_url?: string | null;
  description?: string | null;
}

export interface BrandUpdatePayload {
  name?: string;
  logo_url?: string | null;
  description?: string | null;
  status?: string;
}

export interface ProductSku {
  id: number;
  tenant_id: number;
  product_id: number;
  sku_code: string;
  name: string;
  barcode: string | null;
  spec_values: Record<string, string>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ProductSkuInput {
  sku_code: string;
  name: string;
  barcode?: string | null;
  spec_values?: Record<string, string>;
  status?: string;
}

export interface ProductSkuUpdatePayload {
  name?: string;
  barcode?: string | null;
  spec_values?: Record<string, string>;
  status?: string;
}

export interface ProductListItem {
  id: number;
  tenant_id: number;
  name: string;
  code: string;
  category_id: number;
  category_name: string;
  brand_id: number | null;
  brand_name: string | null;
  sku_count: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ProductList {
  items: ProductListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProductDetail extends ProductListItem {
  description: string | null;
  skus: ProductSku[];
}

export interface ProductCreatePayload {
  name: string;
  code: string;
  category_id: number;
  brand_id?: number | null;
  description?: string | null;
  status?: string;
  skus: ProductSkuInput[];
}

export interface ProductUpdatePayload {
  name?: string;
  category_id?: number;
  brand_id?: number | null;
  description?: string | null;
  status?: string;
}

export interface SpecEntry {
  key: string;
  value: string;
}

export function specEntriesFromRecord(values: Record<string, unknown> | null | undefined): SpecEntry[] {
  const entries = Object.entries(values ?? {}).map(([key, value]) => ({
    key,
    value: value == null ? '' : String(value),
  }));
  return entries.length ? entries : [{ key: '', value: '' }];
}

export function specRecordFromEntries(entries: Array<{ key?: string; value?: string }> | undefined): Record<string, string> {
  const result: Record<string, string> = {};
  for (const item of entries ?? []) {
    const key = item.key?.trim() ?? '';
    const value = item.value?.trim() ?? '';
    if (key && value) {
      result[key] = value;
    }
  }
  return result;
}

export function flattenProductCategories(nodes: readonly ProductCategory[]): ProductCategory[] {
  const result: ProductCategory[] = [];
  const walk = (items: readonly ProductCategory[]) => {
    for (const item of items) {
      result.push(item);
      if (item.children.length) {
        walk(item.children);
      }
    }
  };
  walk(nodes);
  return result;
}

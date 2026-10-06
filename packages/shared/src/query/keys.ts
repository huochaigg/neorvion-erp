/**
 * React Query key 工厂。租户相关数据第一段为 `tenant`，第二段为 tenantId。
 * 非租户数据（当前用户、我的租户列表）不带 tenantId。
 */
export function currentUserQueryKey() {
  return ['current-user'] as const;
}

export function myTenantsQueryKey() {
  return ['my-tenants'] as const;
}

export function healthQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'health'] as const;
}

export function tenantDetailQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'detail'] as const;
}

export function tenantMembersQueryKey(
  tenantId: number | null,
  filters?: { q?: string; status?: string; page?: number; pageSize?: number },
) {
  return ['tenant', tenantId, 'members', filters ?? {}] as const;
}

export function tenantMemberQueryKey(tenantId: number | null, memberId: number | null) {
  return ['tenant', tenantId, 'member', memberId] as const;
}

export function tenantRolesQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'roles'] as const;
}

export function tenantPermissionsQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'permissions'] as const;
}

export function tenantPermissionTreeQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'permission-tree'] as const;
}

export function tenantContextQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'context'] as const;
}

export function tenantMyPermissionsQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'my-permissions'] as const;
}

export function productCategoriesQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'product-categories'] as const;
}

export function brandsQueryKey(
  tenantId: number | null,
  filters?: { q?: string; status?: string; page?: number; pageSize?: number },
) {
  return ['tenant', tenantId, 'brands', filters ?? {}] as const;
}

export function brandOptionsQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'brand-options'] as const;
}

export function productsQueryKey(
  tenantId: number | null,
  filters?: {
    q?: string;
    skuCode?: string;
    categoryId?: number;
    brandId?: number;
    status?: string;
    page?: number;
    pageSize?: number;
  },
) {
  return ['tenant', tenantId, 'products', filters ?? {}] as const;
}

export function productQueryKey(tenantId: number | null, productId: number | null) {
  return ['tenant', tenantId, 'product', productId] as const;
}

export function warehousesQueryKey(
  tenantId: number | null,
  filters?: {
    q?: string;
    type?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  },
) {
  return ['tenant', tenantId, 'warehouses', filters ?? {}] as const;
}

export function warehouseQueryKey(tenantId: number | null, warehouseId: number | null) {
  return ['tenant', tenantId, 'warehouse', warehouseId] as const;
}

export function ordersQueryKey(tenantId: number | null) {
  return salesOrdersQueryKey(tenantId);
}

export function salesOrdersQueryKey(
  tenantId: number | null,
  filters?: {
    q?: string;
    orderNo?: string;
    externalOrderNo?: string;
    customerId?: number;
    warehouseId?: number;
    skuCode?: string;
    productName?: string;
    status?: string;
    source?: string;
    createdFrom?: string;
    createdTo?: string;
    page?: number;
    pageSize?: number;
  },
) {
  return ['tenant', tenantId, 'sales-orders', filters ?? {}] as const;
}

export function salesOrderQueryKey(tenantId: number | null, orderId: number | null) {
  return ['tenant', tenantId, 'sales-order', orderId] as const;
}

export function customersQueryKey(
  tenantId: number | null,
  filters?: {
    q?: string;
    status?: string;
    countryCode?: string;
    page?: number;
    pageSize?: number;
  },
) {
  return ['tenant', tenantId, 'customers', filters ?? {}] as const;
}

export function customerQueryKey(tenantId: number | null, customerId: number | null) {
  return ['tenant', tenantId, 'customer', customerId] as const;
}

export function skuInventoryQueryKey(
  tenantId: number | null,
  warehouseId: number | null,
  skuIds: readonly number[],
) {
  return ['tenant', tenantId, 'sku-inventory', warehouseId, [...skuIds].sort((a, b) => a - b)] as const;
}

export function inventoryQueryKey(
  tenantId: number | null,
  filters?: {
    q?: string;
    skuCode?: string;
    warehouseId?: number;
    categoryId?: number;
    brandId?: number;
    stockStatus?: string;
    threshold?: number;
    page?: number;
    pageSize?: number;
  },
) {
  return ['tenant', tenantId, 'inventory', filters ?? {}] as const;
}

export function inventoryDetailQueryKey(tenantId: number | null, inventoryId: number | null) {
  return ['tenant', tenantId, 'inventory', inventoryId] as const;
}

export function inventoryTransactionsQueryKey(
  tenantId: number | null,
  filters?: {
    warehouseId?: number;
    skuId?: number;
    inventoryId?: number;
    type?: string;
    createdFrom?: string;
    createdTo?: string;
    page?: number;
    pageSize?: number;
  },
) {
  return ['tenant', tenantId, 'inventory-transactions', filters ?? {}] as const;
}

export function productSkuOptionsQueryKey(
  tenantId: number | null,
  filters?: { q?: string; page?: number; pageSize?: number },
) {
  return ['tenant', tenantId, 'product-skus', filters ?? {}] as const;
}

export function suppliersQueryKey(
  tenantId: number | null,
  filters?: {
    q?: string;
    status?: string;
    countryCode?: string;
    page?: number;
    pageSize?: number;
  },
) {
  return ['tenant', tenantId, 'suppliers', filters ?? {}] as const;
}

export function supplierQueryKey(tenantId: number | null, supplierId: number | null) {
  return ['tenant', tenantId, 'supplier', supplierId] as const;
}

export function purchaseOrdersQueryKey(
  tenantId: number | null,
  filters?: {
    q?: string;
    supplierId?: number;
    warehouseId?: number;
    skuId?: number;
    status?: string;
    createdFrom?: string;
    createdTo?: string;
    expectedFrom?: string;
    expectedTo?: string;
    createdBy?: number;
    page?: number;
    pageSize?: number;
  },
) {
  return ['tenant', tenantId, 'purchase-orders', filters ?? {}] as const;
}

export function purchaseOrderQueryKey(tenantId: number | null, orderId: number | null) {
  return ['tenant', tenantId, 'purchase-order', orderId] as const;
}

export function isTenantScopedQueryKey(queryKey: readonly unknown[]): boolean {
  return queryKey[0] === 'tenant';
}

export function tenantIdFromQueryKey(queryKey: readonly unknown[]): number | null | undefined {
  if (!isTenantScopedQueryKey(queryKey)) {
    return undefined;
  }
  const value = queryKey[1];
  if (value === null) {
    return null;
  }
  return typeof value === 'number' ? value : undefined;
}

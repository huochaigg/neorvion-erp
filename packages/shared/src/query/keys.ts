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

export function tenantMembersQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'members'] as const;
}

export function tenantContextQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'context'] as const;
}

export function productsQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'products'] as const;
}

export function ordersQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'orders'] as const;
}

export function inventoryQueryKey(tenantId: number | null) {
  return ['tenant', tenantId, 'inventory'] as const;
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

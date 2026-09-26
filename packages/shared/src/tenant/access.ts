import { MEMBER_STATUS, TENANT_STATUS, type Tenant } from '../types/tenant';

export function isUsableTenant(tenant: Tenant): boolean {
  return tenant.status === TENANT_STATUS.active && tenant.my_status === MEMBER_STATUS.active;
}

export function listUsableTenants(tenants: Tenant[]): Tenant[] {
  return tenants.filter(isUsableTenant);
}

export type TenantPickResult =
  | { kind: 'none' }
  | { kind: 'choose' }
  | { kind: 'select'; tenantId: number };

/** 登录后选择当前租户。lastTenantId 必须仍在当前用户的有效列表中。 */
export function pickTenantSelection(tenants: Tenant[], lastTenantId: number | null): TenantPickResult {
  const usable = listUsableTenants(tenants);
  if (usable.length === 0) {
    return { kind: 'none' };
  }
  if (lastTenantId !== null && usable.some((item) => item.id === lastTenantId)) {
    return { kind: 'select', tenantId: lastTenantId };
  }
  if (usable.length === 1) {
    return { kind: 'select', tenantId: usable[0].id };
  }
  return { kind: 'choose' };
}

export function lastTenantStorageKey(userId: number): string {
  return `neorvion:last-tenant-id:${userId}`;
}

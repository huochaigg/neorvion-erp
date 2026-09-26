import { lastTenantStorageKey } from '@neorvion/shared';

export function readLastTenantId(userId: number): number | null {
  const raw = window.localStorage.getItem(lastTenantStorageKey(userId));
  if (!raw) {
    return null;
  }
  const tenantId = Number(raw);
  return Number.isInteger(tenantId) && tenantId > 0 ? tenantId : null;
}

export function writeLastTenantId(userId: number, tenantId: number | null) {
  const key = lastTenantStorageKey(userId);
  if (tenantId == null) {
    window.localStorage.removeItem(key);
    return;
  }
  window.localStorage.setItem(key, String(tenantId));
}

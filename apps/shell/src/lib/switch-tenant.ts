import type { QueryClient } from '@tanstack/react-query';
import {
  ApiError,
  currentUserQueryKey,
  listUsableTenants,
  myTenantsQueryKey,
  SHELL_EVENTS,
  type Tenant,
  type TenantChangedPayload,
  type UserProfile,
} from '@neorvion/shared';
import { bus } from 'wujie';
import { isolateTenantQueries } from '@/lib/query-tenant';
import { writeLastTenantId } from '@/lib/tenant-persist';
import { useTenantStore } from '@/stores/tenant-store';

function persistForCurrentUser(queryClient: QueryClient, tenantId: number | null) {
  const user = queryClient.getQueryData<UserProfile>(currentUserQueryKey());
  if (user) {
    writeLastTenantId(user.id, tenantId);
  }
}

export function emitTenantChanged(payload: TenantChangedPayload) {
  bus.$emit(SHELL_EVENTS.tenantChanged, payload);
}

export function applyCurrentTenant(
  queryClient: QueryClient,
  nextTenantId: number | null,
  options?: { persist?: boolean },
) {
  const previousTenantId = useTenantStore.getState().currentTenantId;
  if (previousTenantId === nextTenantId) {
    return;
  }
  isolateTenantQueries(queryClient, previousTenantId);
  useTenantStore.getState().setCurrentTenantId(nextTenantId);
  if (options?.persist !== false) {
    persistForCurrentUser(queryClient, nextTenantId);
  }
  emitTenantChanged({ previousTenantId, currentTenantId: nextTenantId });
}

export function switchTenant(queryClient: QueryClient, nextTenantId: number) {
  const tenants = queryClient.getQueryData<Tenant[]>(myTenantsQueryKey()) ?? [];
  const usable = listUsableTenants(tenants);
  if (!usable.some((item) => item.id === nextTenantId)) {
    throw new ApiError('无权访问该企业', { status: 403, code: 40310 });
  }
  const previousTenantId = useTenantStore.getState().currentTenantId;
  if (previousTenantId === nextTenantId) {
    return;
  }

  useTenantStore.getState().beginSwitch();
  try {
    applyCurrentTenant(queryClient, nextTenantId);
  } finally {
    useTenantStore.getState().endSwitch();
  }
}

export function clearTenantSelection(queryClient: QueryClient, options?: { persist?: boolean }) {
  applyCurrentTenant(queryClient, null, options);
}

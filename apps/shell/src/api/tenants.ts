import type { ApiResponse, Tenant, TenantContextInfo, TenantCreatePayload, TenantMember } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchMyTenants(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<Tenant[]>>('/api/v1/tenants', { signal }));
}

export function createTenant(payload: TenantCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<Tenant>>('/api/v1/tenants', payload));
}

export function fetchTenant(tenantId: number, signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<Tenant>>(`/api/v1/tenants/${tenantId}`, { signal }));
}

export function fetchTenantMembers(tenantId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<TenantMember[]>>(`/api/v1/tenants/${tenantId}/members`, { signal }),
  );
}

export function fetchTenantContext(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<TenantContextInfo>>('/api/v1/tenants/current', { signal }));
}

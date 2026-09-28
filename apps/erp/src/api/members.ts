import type {
  ApiResponse,
  MemberAccountCreatePayload,
  MemberCreatePayload,
  MemberCreated,
  MemberRolesUpdatePayload,
  TenantContextInfo,
  TenantMember,
  TenantMemberDetail,
  TenantMemberList,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchMembers(
  tenantId: number,
  params: { q?: string; status?: string; page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<TenantMemberList>>(`/api/v1/tenants/${tenantId}/members`, {
      params: {
        q: params.q || undefined,
        status: params.status || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchMember(tenantId: number, memberId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<TenantMemberDetail>>(
      `/api/v1/tenants/${tenantId}/members/${memberId}`,
      { signal },
    ),
  );
}

export function addMember(tenantId: number, payload: MemberCreatePayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<TenantMember>>(`/api/v1/tenants/${tenantId}/members`, payload),
  );
}

export function createMemberAccount(tenantId: number, payload: MemberAccountCreatePayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<MemberCreated>>(`/api/v1/tenants/${tenantId}/members/accounts`, payload),
  );
}

export function updateMemberRoles(
  tenantId: number,
  memberId: number,
  payload: MemberRolesUpdatePayload,
) {
  return unwrapApi(
    apiClient.put<ApiResponse<TenantMember>>(
      `/api/v1/tenants/${tenantId}/members/${memberId}/roles`,
      payload,
    ),
  );
}

export function updateMemberStatus(tenantId: number, memberId: number, status: string) {
  return unwrapApi(
    apiClient.patch<ApiResponse<TenantMember>>(
      `/api/v1/tenants/${tenantId}/members/${memberId}`,
      { status },
    ),
  );
}

export function removeMember(tenantId: number, memberId: number) {
  return unwrapApi(
    apiClient.delete<ApiResponse<null>>(`/api/v1/tenants/${tenantId}/members/${memberId}`),
  );
}

export function fetchTenantContext(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<TenantContextInfo>>('/api/v1/tenants/current', { signal }));
}

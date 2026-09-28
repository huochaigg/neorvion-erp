import type {
  ApiResponse,
  PermissionInfo,
  PermissionTreeNode,
  RoleCreatePayload,
  RoleInfo,
  RoleUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchRoles(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<RoleInfo[]>>('/api/v1/roles', { signal }));
}

export function fetchPermissions(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<PermissionInfo[]>>('/api/v1/permissions', { signal }));
}

export function fetchPermissionTree(signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<PermissionTreeNode[]>>('/api/v1/permissions/tree', { signal }),
  );
}

export function createRole(payload: RoleCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<RoleInfo>>('/api/v1/roles', payload));
}

export function updateRole(roleId: number, payload: RoleUpdatePayload) {
  return unwrapApi(apiClient.patch<ApiResponse<RoleInfo>>(`/api/v1/roles/${roleId}`, payload));
}

export function updateRolePermissions(roleId: number, permissionIds: number[]) {
  return unwrapApi(
    apiClient.put<ApiResponse<RoleInfo>>(`/api/v1/roles/${roleId}/permissions`, {
      permission_ids: permissionIds,
    }),
  );
}

export function deleteRole(roleId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/roles/${roleId}`));
}

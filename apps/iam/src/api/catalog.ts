import type { ApiResponse } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export interface IamApplication {
  id: number;
  code: string;
  name: string;
  audience: string;
  status: string;
  description: string;
}

export interface IamMenu {
  id: number;
  application_id: number;
  parent_id: number | null;
  menu_key: string;
  title: string;
  menu_type: string;
  path: string;
  permission_code: string | null;
  sort_no: number;
  visible: boolean;
  locked: boolean;
}

export interface IamAuditLog {
  id: number;
  tenant_id: number | null;
  actor_user_id: number;
  action: string;
  target_type: string;
  target_id: string;
  detail: string;
  created_at: string;
}

export function fetchApplications(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<IamApplication[]>>('/api/v1/applications', { signal }));
}

export function createApplication(payload: {
  code: string;
  name: string;
  audience: string;
  description?: string;
}) {
  return unwrapApi(apiClient.post<ApiResponse<IamApplication>>('/api/v1/applications', payload));
}

export function patchApplication(
  applicationId: number,
  payload: { name?: string; description?: string; status?: string },
) {
  return unwrapApi(
    apiClient.patch<ApiResponse<IamApplication>>(`/api/v1/applications/${applicationId}`, payload),
  );
}

export function fetchMenus(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<IamMenu[]>>('/api/v1/menus', { signal }));
}

export function createMenu(payload: {
  application_id: number;
  parent_id?: number | null;
  menu_key: string;
  title: string;
  menu_type: string;
  path?: string;
  permission_code?: string | null;
  sort_no?: number;
  visible?: boolean;
}) {
  return unwrapApi(apiClient.post<ApiResponse<IamMenu>>('/api/v1/menus', payload));
}

export function updateMenu(
  menuId: number,
  payload: {
    title?: string;
    path?: string;
    visible?: boolean;
    sort_no?: number;
    permission_code?: string | null;
  },
) {
  return unwrapApi(apiClient.patch<ApiResponse<IamMenu>>(`/api/v1/menus/${menuId}`, payload));
}

export function fetchAuditLogs(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<IamAuditLog[]>>('/api/v1/audit-logs', { signal }));
}

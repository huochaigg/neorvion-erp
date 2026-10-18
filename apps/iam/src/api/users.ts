import type { ApiResponse } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export interface IamUser {
  id: number;
  email: string;
  display_name: string;
  status: string;
  created_at: string;
  is_platform_admin?: boolean;
  must_change_password?: boolean;
}

export function fetchUsers(q = '', signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<IamUser[]>>('/api/v1/users', {
      params: { q: q || undefined },
      signal,
    }),
  );
}

export function disableUser(payload: { userId: number; status: 'ACTIVE' | 'DISABLED' }) {
  return unwrapApi(
    apiClient.patch<ApiResponse<IamUser>>(`/api/v1/users/${payload.userId}`, {
      status: payload.status,
    }),
  );
}

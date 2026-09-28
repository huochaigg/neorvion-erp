import {
  tenantMyPermissionsQueryKey,
  type ApiResponse,
  type MyPermissions,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchMyPermissions(signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<MyPermissions>>('/api/v1/tenants/current/my-permissions', {
      signal,
    }),
  );
}

export { tenantMyPermissionsQueryKey };

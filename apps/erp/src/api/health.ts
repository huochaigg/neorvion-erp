import type { ApiResponse, HealthCheckData } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchHealth(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<HealthCheckData>>('/api/v1/health', { signal }));
}

export type { HealthCheckData };

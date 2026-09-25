import type { ApiResponse, HealthCheckData } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchHealth() {
  return unwrapApi(apiClient.get<ApiResponse<HealthCheckData>>('/api/v1/health'));
}

export type { HealthCheckData };

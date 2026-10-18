import type { ApiResponse, OperationLog, OperationLogList } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchOperationLogs(
  params: {
    operatorUserId?: number;
    module?: string;
    action?: string;
    resourceType?: string;
    result?: string;
    keyword?: string;
    occurredFrom?: string;
    occurredTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<OperationLogList>>('/api/v1/operation-logs', {
      params: {
        operator_user_id: params.operatorUserId,
        module: params.module || undefined,
        action: params.action || undefined,
        resource_type: params.resourceType || undefined,
        result: params.result || undefined,
        keyword: params.keyword || undefined,
        occurred_from: params.occurredFrom,
        occurred_to: params.occurredTo,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchOperationLog(logId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<OperationLog>>(`/api/v1/operation-logs/${logId}`, { signal }),
  );
}

import type { ApiResponse, AsyncTask, AsyncTaskList, AsyncTaskLog } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchTasks(
  params: {
    taskType?: string;
    status?: string;
    keyword?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<AsyncTaskList>>('/api/v1/tasks', {
      params: {
        task_type: params.taskType || undefined,
        status: params.status || undefined,
        keyword: params.keyword || undefined,
        created_from: params.createdFrom,
        created_to: params.createdTo,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchTask(taskId: string, signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<AsyncTask>>(`/api/v1/tasks/${taskId}`, { signal }));
}

export function fetchTaskLogs(taskId: string, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<AsyncTaskLog[]>>(`/api/v1/tasks/${taskId}/logs`, { signal }),
  );
}

export function retryTask(taskId: string) {
  return unwrapApi(apiClient.post<ApiResponse<AsyncTask>>(`/api/v1/tasks/${taskId}/retry`));
}

export function cancelTask(taskId: string) {
  return unwrapApi(apiClient.post<ApiResponse<AsyncTask>>(`/api/v1/tasks/${taskId}/cancel`));
}

export async function downloadTaskResult(taskId: string, fallbackName = 'export.csv') {
  const response = await apiClient.get<Blob>(`/api/v1/tasks/${taskId}/download`, {
    responseType: 'blob',
    timeout: 60000,
  });
  const blob = response.data;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

export function createSalesExportTask(params: {
  startDate?: string;
  endDate?: string;
  warehouseId?: number;
}) {
  return unwrapApi(
    apiClient.post<ApiResponse<AsyncTask>>('/api/v1/analytics/sales/export-tasks', null, {
      params: {
        start_date: params.startDate,
        end_date: params.endDate,
        warehouse_id: params.warehouseId,
      },
    }),
  );
}

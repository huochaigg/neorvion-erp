import type {
  ApiResponse,
  Warehouse,
  WarehouseCreatePayload,
  WarehouseList,
  WarehouseUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchWarehouses(
  params: { q?: string; type?: string; status?: string; page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<WarehouseList>>('/api/v1/warehouses', {
      params: {
        q: params.q || undefined,
        type: params.type || undefined,
        status: params.status || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchWarehouse(warehouseId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<Warehouse>>(`/api/v1/warehouses/${warehouseId}`, { signal }),
  );
}

export function createWarehouse(payload: WarehouseCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<Warehouse>>('/api/v1/warehouses', payload));
}

export function updateWarehouse(warehouseId: number, payload: WarehouseUpdatePayload) {
  return unwrapApi(
    apiClient.patch<ApiResponse<Warehouse>>(`/api/v1/warehouses/${warehouseId}`, payload),
  );
}

export function changeWarehouseStatus(warehouseId: number, status: string) {
  return unwrapApi(
    apiClient.patch<ApiResponse<Warehouse>>(`/api/v1/warehouses/${warehouseId}/status`, { status }),
  );
}

export function setDefaultWarehouse(warehouseId: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<Warehouse>>(`/api/v1/warehouses/${warehouseId}/set-default`),
  );
}

export function deleteWarehouse(warehouseId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/warehouses/${warehouseId}`));
}

import type {
  ApiResponse,
  StockTransferCreatePayload,
  StockTransferDetail,
  StockTransferList,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchStockTransfers(
  params: {
    q?: string;
    sourceWarehouseId?: number;
    targetWarehouseId?: number;
    status?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<StockTransferList>>('/api/v1/stock-transfers', {
      params: {
        q: params.q || undefined,
        source_warehouse_id: params.sourceWarehouseId,
        target_warehouse_id: params.targetWarehouseId,
        status: params.status || undefined,
        created_from: params.createdFrom || undefined,
        created_to: params.createdTo || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchStockTransfer(id: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<StockTransferDetail>>(`/api/v1/stock-transfers/${id}`, { signal }),
  );
}

export function createStockTransfer(payload: StockTransferCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<StockTransferDetail>>('/api/v1/stock-transfers', payload));
}

export function updateStockTransfer(id: number, payload: StockTransferCreatePayload) {
  return unwrapApi(
    apiClient.patch<ApiResponse<StockTransferDetail>>(`/api/v1/stock-transfers/${id}`, payload),
  );
}

export function submitStockTransfer(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<StockTransferDetail>>(`/api/v1/stock-transfers/${id}/submit`),
  );
}

export function confirmTransferOutbound(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<StockTransferDetail>>(`/api/v1/stock-transfers/${id}/confirm-outbound`),
  );
}

export function confirmTransferReceive(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<StockTransferDetail>>(`/api/v1/stock-transfers/${id}/confirm-receive`),
  );
}

export function cancelStockTransfer(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<StockTransferDetail>>(`/api/v1/stock-transfers/${id}/cancel`),
  );
}

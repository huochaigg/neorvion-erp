import type {
  ApiResponse,
  StocktakeCreatePayload,
  StocktakeDetail,
  StocktakeItemSavePayload,
  StocktakeList,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchStocktakes(
  params: {
    q?: string;
    warehouseId?: number;
    status?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<StocktakeList>>('/api/v1/stocktakes', {
      params: {
        q: params.q || undefined,
        warehouse_id: params.warehouseId,
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

export function fetchStocktake(id: number, signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<StocktakeDetail>>(`/api/v1/stocktakes/${id}`, { signal }));
}

export function createStocktake(payload: StocktakeCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<StocktakeDetail>>('/api/v1/stocktakes', payload));
}

export function saveStocktakeItems(id: number, items: StocktakeItemSavePayload[]) {
  return unwrapApi(
    apiClient.put<ApiResponse<StocktakeDetail>>(`/api/v1/stocktakes/${id}/items`, { items }),
  );
}

export function submitStocktake(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<StocktakeDetail>>(`/api/v1/stocktakes/${id}/submit`));
}

export function confirmStocktake(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<StocktakeDetail>>(`/api/v1/stocktakes/${id}/confirm`));
}

export function cancelStocktake(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<StocktakeDetail>>(`/api/v1/stocktakes/${id}/cancel`));
}

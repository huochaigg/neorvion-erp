import type {
  ApiResponse,
  InventoryAdjustPayload,
  InventoryDetail,
  InventoryInitializePayload,
  InventoryItem,
  InventoryList,
  InventoryTransactionList,
  SkuOptionList,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchInventory(
  params: {
    q?: string;
    skuCode?: string;
    warehouseId?: number;
    categoryId?: number;
    brandId?: number;
    stockStatus?: string;
    threshold?: number;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<InventoryList>>('/api/v1/inventory', {
      params: {
        q: params.q || undefined,
        sku_code: params.skuCode || undefined,
        warehouse_id: params.warehouseId,
        category_id: params.categoryId,
        brand_id: params.brandId,
        stock_status: params.stockStatus || undefined,
        threshold: params.threshold,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchInventoryDetail(inventoryId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<InventoryDetail>>(`/api/v1/inventory/${inventoryId}`, { signal }),
  );
}

export function initializeInventory(payload: InventoryInitializePayload) {
  return unwrapApi(apiClient.post<ApiResponse<InventoryItem>>('/api/v1/inventory/initialize', payload));
}

export function adjustInventory(inventoryId: number, payload: InventoryAdjustPayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<InventoryItem>>(`/api/v1/inventory/${inventoryId}/adjust`, payload),
  );
}

export function fetchInventoryTransactions(
  params: {
    warehouseId?: number;
    skuId?: number;
    inventoryId?: number;
    type?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  const path =
    params.inventoryId != null
      ? `/api/v1/inventory/${params.inventoryId}/transactions`
      : '/api/v1/inventory/transactions';
  return unwrapApi(
    apiClient.get<ApiResponse<InventoryTransactionList>>(path, {
      params: {
        warehouse_id: params.warehouseId,
        sku_id: params.skuId,
        type: params.type || undefined,
        created_from: params.createdFrom || undefined,
        created_to: params.createdTo || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchSkuOptions(
  params: { q?: string; page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<SkuOptionList>>('/api/v1/product-skus', {
      params: {
        q: params.q || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

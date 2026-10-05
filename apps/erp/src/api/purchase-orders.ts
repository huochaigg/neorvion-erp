import type {
  ApiResponse,
  PurchaseOrderCreatePayload,
  PurchaseOrderDetail,
  PurchaseOrderList,
  PurchaseOrderUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchPurchaseOrders(
  params: {
    q?: string;
    supplierId?: number;
    warehouseId?: number;
    skuId?: number;
    status?: string;
    createdFrom?: string;
    createdTo?: string;
    expectedFrom?: string;
    expectedTo?: string;
    createdBy?: number;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseOrderList>>('/api/v1/purchase-orders', {
      params: {
        q: params.q || undefined,
        supplier_id: params.supplierId,
        warehouse_id: params.warehouseId,
        sku_id: params.skuId,
        status: params.status || undefined,
        created_from: params.createdFrom || undefined,
        created_to: params.createdTo || undefined,
        expected_from: params.expectedFrom || undefined,
        expected_to: params.expectedTo || undefined,
        created_by: params.createdBy,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchPurchaseOrder(orderId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseOrderDetail>>(`/api/v1/purchase-orders/${orderId}`, {
      signal,
    }),
  );
}

export function createPurchaseOrder(payload: PurchaseOrderCreatePayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseOrderDetail>>('/api/v1/purchase-orders', payload),
  );
}

export function updatePurchaseOrder(orderId: number, payload: PurchaseOrderUpdatePayload) {
  return unwrapApi(
    apiClient.patch<ApiResponse<PurchaseOrderDetail>>(`/api/v1/purchase-orders/${orderId}`, payload),
  );
}

export function submitPurchaseOrder(orderId: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseOrderDetail>>(`/api/v1/purchase-orders/${orderId}/submit`),
  );
}

export function approvePurchaseOrder(orderId: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseOrderDetail>>(`/api/v1/purchase-orders/${orderId}/approve`),
  );
}

export function rejectPurchaseOrder(orderId: number, reason: string) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseOrderDetail>>(`/api/v1/purchase-orders/${orderId}/reject`, {
      reason,
    }),
  );
}

export function cancelPurchaseOrder(orderId: number, reason?: string | null) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseOrderDetail>>(`/api/v1/purchase-orders/${orderId}/cancel`, {
      reason: reason || null,
    }),
  );
}

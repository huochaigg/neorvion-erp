import type {
  ApiResponse,
  ReturnOrderDetail,
  ReturnOrderList,
  ReturnOrderUpdatePayload,
  ReturnReceivePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchReturnOrders(
  params: {
    q?: string;
    afterSaleId?: number;
    salesOrderId?: number;
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
    apiClient.get<ApiResponse<ReturnOrderList>>('/api/v1/return-orders', {
      params: {
        q: params.q || undefined,
        after_sale_id: params.afterSaleId,
        sales_order_id: params.salesOrderId,
        warehouse_id: params.warehouseId,
        status: params.status || undefined,
        created_from: params.createdFrom,
        created_to: params.createdTo,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchReturnOrder(id: number, signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<ReturnOrderDetail>>(`/api/v1/return-orders/${id}`, { signal }));
}

export function updateReturnOrder(id: number, payload: ReturnOrderUpdatePayload) {
  return unwrapApi(apiClient.patch<ApiResponse<ReturnOrderDetail>>(`/api/v1/return-orders/${id}`, payload));
}

export function receiveReturnOrder(id: number, payload: ReturnReceivePayload) {
  return unwrapApi(apiClient.post<ApiResponse<ReturnOrderDetail>>(`/api/v1/return-orders/${id}/receive`, payload));
}

export function confirmReturnInbound(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<ReturnOrderDetail>>(`/api/v1/return-orders/${id}/confirm-inbound`));
}

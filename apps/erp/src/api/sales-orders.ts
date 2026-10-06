import type {
  ApiResponse,
  SalesOrderCreatePayload,
  SalesOrderDetail,
  SalesOrderList,
  SalesOrderUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchSalesOrders(
  params: {
    q?: string;
    orderNo?: string;
    externalOrderNo?: string;
    customerId?: number;
    warehouseId?: number;
    skuCode?: string;
    productName?: string;
    status?: string;
    source?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<SalesOrderList>>('/api/v1/sales-orders', {
      params: {
        q: params.q || undefined,
        order_no: params.orderNo || undefined,
        external_order_no: params.externalOrderNo || undefined,
        customer_id: params.customerId,
        warehouse_id: params.warehouseId,
        sku_code: params.skuCode || undefined,
        product_name: params.productName || undefined,
        status: params.status || undefined,
        source: params.source || undefined,
        created_from: params.createdFrom || undefined,
        created_to: params.createdTo || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchSalesOrder(orderId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<SalesOrderDetail>>(`/api/v1/sales-orders/${orderId}`, { signal }),
  );
}

export function createSalesOrder(payload: SalesOrderCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<SalesOrderDetail>>('/api/v1/sales-orders', payload));
}

export function updateSalesOrder(orderId: number, payload: SalesOrderUpdatePayload) {
  return unwrapApi(
    apiClient.patch<ApiResponse<SalesOrderDetail>>(`/api/v1/sales-orders/${orderId}`, payload),
  );
}

export function submitSalesOrder(orderId: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<SalesOrderDetail>>(`/api/v1/sales-orders/${orderId}/submit`),
  );
}

export function confirmSalesOrder(orderId: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<SalesOrderDetail>>(`/api/v1/sales-orders/${orderId}/confirm`),
  );
}

export function cancelSalesOrder(orderId: number, reason: string | null) {
  return unwrapApi(
    apiClient.post<ApiResponse<SalesOrderDetail>>(`/api/v1/sales-orders/${orderId}/cancel`, { reason }),
  );
}

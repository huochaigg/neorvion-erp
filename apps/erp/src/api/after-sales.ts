import type {
  AfterSaleApprovePayload,
  AfterSaleCreatePayload,
  AfterSaleDetail,
  AfterSaleList,
  AfterSalePreview,
  AfterSaleRejectPayload,
  ApiResponse,
  RefundCreatePayload,
  RefundRecord,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchAfterSales(
  params: {
    q?: string;
    salesOrderId?: number;
    customerId?: number;
    skuCode?: string;
    type?: string;
    status?: string;
    refundStatus?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<AfterSaleList>>('/api/v1/after-sales', {
      params: {
        q: params.q || undefined,
        sales_order_id: params.salesOrderId,
        customer_id: params.customerId,
        sku_code: params.skuCode || undefined,
        type: params.type || undefined,
        status: params.status || undefined,
        refund_status: params.refundStatus || undefined,
        created_from: params.createdFrom,
        created_to: params.createdTo,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchAfterSalePreview(salesOrderId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<AfterSalePreview>>('/api/v1/after-sales/preview', {
      params: { sales_order_id: salesOrderId },
      signal,
    }),
  );
}

export function fetchAfterSale(id: number, signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<AfterSaleDetail>>(`/api/v1/after-sales/${id}`, { signal }));
}

export function createAfterSale(payload: AfterSaleCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<AfterSaleDetail>>('/api/v1/after-sales', payload));
}

export function approveAfterSale(id: number, payload: AfterSaleApprovePayload) {
  return unwrapApi(apiClient.post<ApiResponse<AfterSaleDetail>>(`/api/v1/after-sales/${id}/approve`, payload));
}

export function rejectAfterSale(id: number, payload: AfterSaleRejectPayload) {
  return unwrapApi(apiClient.post<ApiResponse<AfterSaleDetail>>(`/api/v1/after-sales/${id}/reject`, payload));
}

export function cancelAfterSale(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<AfterSaleDetail>>(`/api/v1/after-sales/${id}/cancel`));
}

export function createAfterSaleRefund(id: number, payload: RefundCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<RefundRecord>>(`/api/v1/after-sales/${id}/refunds`, payload));
}

import type {
  ApiResponse,
  RefundConfirmPayload,
  RefundFailPayload,
  RefundList,
  RefundRecord,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchRefunds(
  params: {
    q?: string;
    afterSaleId?: number;
    status?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<RefundList>>('/api/v1/refunds', {
      params: {
        q: params.q || undefined,
        after_sale_id: params.afterSaleId,
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

export function confirmRefund(id: number, payload: RefundConfirmPayload) {
  return unwrapApi(apiClient.post<ApiResponse<RefundRecord>>(`/api/v1/refunds/${id}/confirm`, payload));
}

export function failRefund(id: number, payload: RefundFailPayload) {
  return unwrapApi(apiClient.post<ApiResponse<RefundRecord>>(`/api/v1/refunds/${id}/fail`, payload));
}

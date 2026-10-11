import type {
  ApiResponse,
  SupplierRefundConfirmPayload,
  SupplierRefundFailPayload,
  SupplierRefundList,
  SupplierRefundRecord,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchSupplierRefunds(
  params: {
    q?: string;
    purchaseReturnId?: number;
    status?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<SupplierRefundList>>('/api/v1/supplier-refunds', {
      params: {
        q: params.q || undefined,
        purchase_return_id: params.purchaseReturnId,
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

export function confirmSupplierRefund(id: number, payload: SupplierRefundConfirmPayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<SupplierRefundRecord>>(`/api/v1/supplier-refunds/${id}/confirm`, payload),
  );
}

export function failSupplierRefund(id: number, payload: SupplierRefundFailPayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<SupplierRefundRecord>>(`/api/v1/supplier-refunds/${id}/fail`, payload),
  );
}

import type { ApiResponse, PurchaseReturnOutboundDetail, PurchaseReturnOutboundList } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchPurchaseReturnOutbounds(
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
    apiClient.get<ApiResponse<PurchaseReturnOutboundList>>('/api/v1/purchase-return-outbounds', {
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

export function fetchPurchaseReturnOutbound(id: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseReturnOutboundDetail>>(`/api/v1/purchase-return-outbounds/${id}`, {
      signal,
    }),
  );
}

export function confirmPurchaseReturnOutbound(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseReturnOutboundDetail>>(
      `/api/v1/purchase-return-outbounds/${id}/confirm`,
    ),
  );
}

export function cancelPurchaseReturnOutbound(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseReturnOutboundDetail>>(
      `/api/v1/purchase-return-outbounds/${id}/cancel`,
    ),
  );
}

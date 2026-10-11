import type {
  ApiResponse,
  PurchaseReturnApprovePayload,
  PurchaseReturnCreatePayload,
  PurchaseReturnDetail,
  PurchaseReturnList,
  PurchaseReturnOutboundCreatePayload,
  PurchaseReturnOutboundDetail,
  PurchaseReturnPreview,
  PurchaseReturnRejectPayload,
  SupplierRefundCreatePayload,
  SupplierRefundRecord,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchPurchaseReturns(
  params: {
    q?: string;
    purchaseOrderId?: number;
    supplierId?: number;
    warehouseId?: number;
    skuId?: number;
    status?: string;
    settlementType?: string;
    refundStatus?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseReturnList>>('/api/v1/purchase-returns', {
      params: {
        q: params.q || undefined,
        purchase_order_id: params.purchaseOrderId,
        supplier_id: params.supplierId,
        warehouse_id: params.warehouseId,
        sku_id: params.skuId,
        status: params.status || undefined,
        settlement_type: params.settlementType || undefined,
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

export function fetchPurchaseReturnPreview(
  purchaseOrderId: number,
  warehouseId?: number,
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseReturnPreview>>('/api/v1/purchase-returns/preview', {
      params: {
        purchase_order_id: purchaseOrderId,
        warehouse_id: warehouseId,
      },
      signal,
    }),
  );
}

export function fetchPurchaseReturn(id: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseReturnDetail>>(`/api/v1/purchase-returns/${id}`, { signal }),
  );
}

export function createPurchaseReturn(payload: PurchaseReturnCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<PurchaseReturnDetail>>('/api/v1/purchase-returns', payload));
}

export function submitPurchaseReturn(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<PurchaseReturnDetail>>(`/api/v1/purchase-returns/${id}/submit`));
}

export function approvePurchaseReturn(id: number, payload: PurchaseReturnApprovePayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseReturnDetail>>(`/api/v1/purchase-returns/${id}/approve`, payload),
  );
}

export function rejectPurchaseReturn(id: number, payload: PurchaseReturnRejectPayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseReturnDetail>>(`/api/v1/purchase-returns/${id}/reject`, payload),
  );
}

export function cancelPurchaseReturn(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<PurchaseReturnDetail>>(`/api/v1/purchase-returns/${id}/cancel`));
}

export function createPurchaseReturnOutbound(id: number, payload: PurchaseReturnOutboundCreatePayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseReturnOutboundDetail>>(
      `/api/v1/purchase-returns/${id}/outbounds`,
      payload,
    ),
  );
}

export function createPurchaseReturnRefund(id: number, payload: SupplierRefundCreatePayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<SupplierRefundRecord>>(`/api/v1/purchase-returns/${id}/refunds`, payload),
  );
}

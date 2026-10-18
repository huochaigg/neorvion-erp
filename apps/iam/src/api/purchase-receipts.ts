import type { ApiResponse } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export interface PurchaseReceiptItem {
  id: number;
  purchase_order_item_id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  order_quantity: number;
  received_before: number;
  expected_quantity: number;
  received_quantity: number;
}

export interface PurchaseReceiptDetail {
  id: number;
  receipt_no: string;
  purchase_order_id: number;
  purchase_order_no: string;
  supplier_name: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  remark: string | null;
  received_by_name: string | null;
  received_at: string | null;
  created_at: string;
  sku_count: number;
  total_received: number;
  items: PurchaseReceiptItem[];
}

export interface PurchaseReceiptList {
  items: Array<{
    id: number;
    receipt_no: string;
    purchase_order_id: number;
    purchase_order_no: string;
    supplier_name: string;
    warehouse_name: string;
    status: string;
    sku_count: number;
    total_received: number;
    received_by_name: string | null;
    received_at: string | null;
    created_at: string;
  }>;
  total: number;
  page: number;
  page_size: number;
}

export function fetchPurchaseReceipts(
  params: {
    q?: string;
    purchaseOrderId?: number;
    status?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseReceiptList>>('/api/v1/purchase-receipts', {
      params: {
        q: params.q || undefined,
        purchase_order_id: params.purchaseOrderId,
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

export function fetchPurchaseReceipt(id: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseReceiptDetail>>(`/api/v1/purchase-receipts/${id}`, { signal }),
  );
}

export function createPurchaseReceipt(payload: {
  purchase_order_id: number;
  remark?: string | null;
  items: Array<{ purchase_order_item_id: number; received_quantity: number }>;
}) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseReceiptDetail>>('/api/v1/purchase-receipts', payload),
  );
}

export function confirmPurchaseReceipt(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseReceiptDetail>>(`/api/v1/purchase-receipts/${id}/confirm`),
  );
}

export function cancelPurchaseReceipt(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<PurchaseReceiptDetail>>(`/api/v1/purchase-receipts/${id}/cancel`),
  );
}

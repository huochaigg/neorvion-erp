import type { ApiResponse } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export interface OutboundItem {
  id: number;
  sales_order_item_id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  planned_quantity: number;
  picked_quantity: number;
  outbound_quantity: number;
}

export interface OutboundDetail {
  id: number;
  outbound_no: string;
  sales_order_id: number;
  sales_order_no: string;
  customer_name: string;
  warehouse_name: string;
  status: string;
  remark: string | null;
  recipient_name: string | null;
  address: string | null;
  picked_at: string | null;
  confirmed_at: string | null;
  created_at: string;
  items: OutboundItem[];
  picks: OutboundPick[];
}

export interface OutboundPickLine {
  id: number;
  sku_code: string;
  product_name: string;
  quantity: number;
  picked_before: number;
  picked_after: number;
}

export interface OutboundPick {
  id: number;
  outbound_no: string;
  picked_at: string;
  picked_by_name: string | null;
  lines: OutboundPickLine[];
}

export interface OutboundList {
  items: Array<{
    id: number;
    outbound_no: string;
    sales_order_id: number;
    sales_order_no: string;
    customer_name: string;
    warehouse_name: string;
    status: string;
    sku_count: number;
    planned_quantity: number;
    picked_quantity: number;
    outbound_quantity: number;
    created_at: string;
  }>;
  total: number;
  page: number;
  page_size: number;
}

export function fetchOutboundOrders(
  params: {
    q?: string;
    salesOrderId?: number;
    status?: string;
    createdFrom?: string;
    createdTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<OutboundList>>('/api/v1/outbound-orders', {
      params: {
        q: params.q || undefined,
        sales_order_id: params.salesOrderId,
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

export function fetchOutboundOrder(id: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<OutboundDetail>>(`/api/v1/outbound-orders/${id}`, { signal }),
  );
}

export function createOutboundOrder(salesOrderId: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<OutboundDetail>>('/api/v1/outbound-orders', {
      sales_order_id: salesOrderId,
    }),
  );
}

export function pickOutboundOrder(
  id: number,
  items: Array<{ id: number; picked_quantity: number }>,
  finish = true,
) {
  return unwrapApi(
    apiClient.post<ApiResponse<OutboundDetail>>(`/api/v1/outbound-orders/${id}/pick`, {
      items,
      finish,
    }),
  );
}

export function confirmOutboundOrder(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<OutboundDetail>>(`/api/v1/outbound-orders/${id}/confirm`),
  );
}

export function cancelOutboundOrder(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<OutboundDetail>>(`/api/v1/outbound-orders/${id}/cancel`),
  );
}

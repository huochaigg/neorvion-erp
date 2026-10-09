import type {
  ApiResponse,
  ShipmentCreatePayload,
  ShipmentDeliverPayload,
  ShipmentDetail,
  ShipmentList,
  ShipmentUpdatePayload,
  TrackingEventCreatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchShipments(
  params: {
    q?: string;
    salesOrderId?: number;
    outboundOrderId?: number;
    carrierId?: number;
    customerId?: number;
    status?: string;
    shippedFrom?: string;
    shippedTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<ShipmentList>>('/api/v1/shipments', {
      params: {
        q: params.q || undefined,
        sales_order_id: params.salesOrderId,
        outbound_order_id: params.outboundOrderId,
        carrier_id: params.carrierId,
        customer_id: params.customerId,
        status: params.status || undefined,
        shipped_from: params.shippedFrom || undefined,
        shipped_to: params.shippedTo || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchShipment(id: number, signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<ShipmentDetail>>(`/api/v1/shipments/${id}`, { signal }));
}

export function createShipment(payload: ShipmentCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<ShipmentDetail>>('/api/v1/shipments', payload));
}

export function updateShipment(id: number, payload: ShipmentUpdatePayload) {
  return unwrapApi(apiClient.patch<ApiResponse<ShipmentDetail>>(`/api/v1/shipments/${id}`, payload));
}

export function confirmShipment(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<ShipmentDetail>>(`/api/v1/shipments/${id}/confirm`));
}

export function cancelShipment(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<ShipmentDetail>>(`/api/v1/shipments/${id}/cancel`));
}

export function addShipmentTrackingEvent(id: number, payload: TrackingEventCreatePayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<ShipmentDetail>>(`/api/v1/shipments/${id}/tracking-events`, payload),
  );
}

export function deliverShipment(id: number, payload: ShipmentDeliverPayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<ShipmentDetail>>(`/api/v1/shipments/${id}/deliver`, payload),
  );
}

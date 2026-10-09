import type {
  ApiResponse,
  Carrier,
  CarrierCreatePayload,
  CarrierList,
  CarrierUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchCarriers(
  params: {
    q?: string;
    status?: string;
    carrierType?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<CarrierList>>('/api/v1/carriers', {
      params: {
        q: params.q || undefined,
        status: params.status || undefined,
        carrier_type: params.carrierType || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchCarrier(carrierId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<Carrier>>(`/api/v1/carriers/${carrierId}`, { signal }),
  );
}

export function createCarrier(payload: CarrierCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<Carrier>>('/api/v1/carriers', payload));
}

export function updateCarrier(carrierId: number, payload: CarrierUpdatePayload) {
  return unwrapApi(apiClient.patch<ApiResponse<Carrier>>(`/api/v1/carriers/${carrierId}`, payload));
}

export function changeCarrierStatus(carrierId: number, status: string) {
  return unwrapApi(
    apiClient.patch<ApiResponse<Carrier>>(`/api/v1/carriers/${carrierId}/status`, { status }),
  );
}

export function deleteCarrier(carrierId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/carriers/${carrierId}`));
}

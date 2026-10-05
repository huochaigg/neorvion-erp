import type {
  ApiResponse,
  Supplier,
  SupplierCreatePayload,
  SupplierList,
  SupplierUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchSuppliers(
  params: {
    q?: string;
    status?: string;
    countryCode?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<SupplierList>>('/api/v1/suppliers', {
      params: {
        q: params.q || undefined,
        status: params.status || undefined,
        country_code: params.countryCode || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchSupplier(supplierId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<Supplier>>(`/api/v1/suppliers/${supplierId}`, { signal }),
  );
}

export function createSupplier(payload: SupplierCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<Supplier>>('/api/v1/suppliers', payload));
}

export function updateSupplier(supplierId: number, payload: SupplierUpdatePayload) {
  return unwrapApi(
    apiClient.patch<ApiResponse<Supplier>>(`/api/v1/suppliers/${supplierId}`, payload),
  );
}

export function changeSupplierStatus(supplierId: number, status: string) {
  return unwrapApi(
    apiClient.patch<ApiResponse<Supplier>>(`/api/v1/suppliers/${supplierId}/status`, { status }),
  );
}

export function deleteSupplier(supplierId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/suppliers/${supplierId}`));
}

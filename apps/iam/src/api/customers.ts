import type {
  ApiResponse,
  Customer,
  CustomerCreatePayload,
  CustomerList,
  CustomerUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchCustomers(
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
    apiClient.get<ApiResponse<CustomerList>>('/api/v1/customers', {
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

export function createCustomer(payload: CustomerCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<Customer>>('/api/v1/customers', payload));
}

export function updateCustomer(customerId: number, payload: CustomerUpdatePayload) {
  return unwrapApi(apiClient.patch<ApiResponse<Customer>>(`/api/v1/customers/${customerId}`, payload));
}

export function changeCustomerStatus(customerId: number, status: string) {
  return unwrapApi(
    apiClient.patch<ApiResponse<Customer>>(`/api/v1/customers/${customerId}/status`, { status }),
  );
}

export function deleteCustomer(customerId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/customers/${customerId}`));
}

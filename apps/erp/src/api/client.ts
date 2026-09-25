import axios from 'axios';
import type { ApiResponse } from '@neorvion/shared';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 8000,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    console.error('[erp-api]', error instanceof Error ? error.message : 'request failed');
    return Promise.reject(error);
  },
);

export async function unwrapApi<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const { data } = await promise;
  if (data.code !== 0) {
    throw new Error(data.message);
  }
  return data.data;
}

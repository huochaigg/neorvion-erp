import axios from 'axios';
import type { ApiResponse } from '@neorvion/shared';
import { getShellProps } from '@/lib/runtime';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 8000,
  withCredentials: true,
});

apiClient.interceptors.request.use((config) => {
  const token = getShellProps().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const message = error instanceof Error ? error.message : 'request failed';
    console.error('[erp-api]', message);
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

import axios, { isCancel } from 'axios';
import { ApiError, TENANT_HEADER, type ApiResponse } from '@neorvion/shared';
import { shellProps } from '@/runtime';
import { useCopilotStore } from '@/store';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8013',
  timeout: Number(import.meta.env.VITE_API_TIMEOUT_MS || 8000),
});

api.interceptors.request.use((config) => {
  const token = shellProps().token;
  const tenant = useCopilotStore.getState().tenantId;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (tenant) config.headers[TENANT_HEADER] = String(tenant);
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (isCancel(error)) return Promise.reject(error);
    if (error?.code === 'ECONNABORTED') {
      return Promise.reject(
        new ApiError('请求超时，请检查会话数据库或身份服务', {
          status: 0,
          code: 0,
        }),
      );
    }
    return Promise.reject(
      new ApiError(error?.response?.data?.message || '网络异常', {
        status: error?.response?.status ?? 0,
        code: error?.response?.data?.code ?? 0,
      }),
    );
  },
);

export async function unwrap<T>(p: Promise<{ data: ApiResponse<T> }>) {
  const { data } = await p;
  if (data.code !== 0) throw new ApiError(data.message, { code: data.code });
  return data.data;
}

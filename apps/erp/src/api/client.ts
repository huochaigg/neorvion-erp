import axios, { isAxiosError, isCancel, type AxiosError } from 'axios';
import { ApiError, type ApiResponse } from '@neorvion/shared';
import { getShellProps } from '@/lib/runtime';

/** ERP 只使用 Shell 传入的 Access Token，不调用 Refresh，避免双边轮换 Cookie。 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 8000,
  withCredentials: true,
});

function toApiError(error: AxiosError<ApiResponse<unknown>>): ApiError {
  const status = error.response?.status ?? 0;
  const code = error.response?.data?.code ?? 0;
  if (!error.response) {
    return new ApiError('网络异常', { status, code });
  }
  if (status >= 500) {
    return new ApiError(error.response.data?.message || '服务暂时不可用', { status, code });
  }
  return new ApiError(error.response.data?.message || error.message, { status, code });
}

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
    if (isCancel(error)) {
      return Promise.reject(error);
    }
    const nextError = isAxiosError(error) ? toApiError(error) : error;
    if (nextError instanceof ApiError && nextError.status >= 500) {
      console.error('[erp-api]', nextError.message);
    }
    return Promise.reject(nextError);
  },
);

export async function unwrapApi<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const { data } = await promise;
  if (data.code !== 0) {
    throw new ApiError(data.message, { code: data.code });
  }
  return data.data;
}

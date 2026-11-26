import axios, { isCancel, type AxiosInstance } from 'axios';
import {
  ApiError,
  isTerminalAuthFailure,
  recoverExpiredRequest,
  TENANT_HEADER,
  type ApiResponse,
} from '@neorvion/shared';
import { shellProps } from '@/runtime';
import { useCopilotStore } from '@/store';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8013',
  timeout: Number(import.meta.env.VITE_API_TIMEOUT_MS || 8000),
});

export function copilotAuthContext() {
  const state = useCopilotStore.getState();
  return `${shellProps().sessionVersion?.() ?? 0}:${shellProps().user?.id ?? ''}:${state.epoch}:${state.tenantId ?? ''}`;
}

export function installCopilotAuth(client: AxiosInstance) {
  client.interceptors.request.use((config) => {
    const token = shellProps().token;
    const tenant = useCopilotStore.getState().tenantId;
    if (!config._retried) {
      config.authTokenSent = token;
      config.authContext = copilotAuthContext();
    }
    if (token && !config._retried) config.headers.Authorization = `Bearer ${token}`;
    if (tenant) config.headers[TENANT_HEADER] = String(tenant);
    return config;
  });
  client.interceptors.response.use(
    (response) => response,
    async (error: unknown) => {
      if (isCancel(error)) return Promise.reject(error);
      const axiosError = axios.isAxiosError(error) ? error : null;
      const original = axiosError?.config;
      const body = axiosError?.response?.data as { message?: string; code?: number } | undefined;
      const nextError = new ApiError(
        body?.message ||
          (axiosError?.code === 'ECONNABORTED' ? '请求超时，请检查会话或稍后重试' : '请求异常'),
        { status: axiosError?.response?.status ?? 0, code: body?.code ?? 0 },
      );
      if (original) {
        if (
          isTerminalAuthFailure(nextError.status, nextError.code) &&
          original.authContext === copilotAuthContext() &&
          original.authTokenSent === shellProps().token
        ) {
          shellProps().expireSession?.();
        }
        if (
          original._retried &&
          nextError.status === 401 &&
          original.authContext === copilotAuthContext() &&
          original.authTokenSent === shellProps().token
        )
          shellProps().expireSession?.();
        try {
          const result = await recoverExpiredRequest({
            status: nextError.status,
            code: nextError.code,
            retried: original._retried,
            skip: original.skipAuthRefresh,
            tokenSent: original.authTokenSent ?? null,
            contextSent: original.authContext ?? '',
            context: copilotAuthContext,
            getToken: () => shellProps().token,
            refresh: shellProps().refreshSession,
            retry: (token) => {
              original._retried = true;
              original.authTokenSent = token;
              original.headers.Authorization = `Bearer ${token}`;
              return client.request(original);
            },
          });
          if (result) return result;
        } catch (retryError) {
          return Promise.reject(retryError);
        }
      }
      return Promise.reject(nextError);
    },
  );
}

installCopilotAuth(api);

export async function unwrap<T>(p: Promise<{ data: ApiResponse<T> }>) {
  const { data } = await p;
  if (data.code !== 0) throw new ApiError(data.message, { code: data.code });
  return data.data;
}

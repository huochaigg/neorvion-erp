import axios, { isCancel, type AxiosInstance } from 'axios';
import {
  ApiError,
  createAuthRequestAdapter,
  microAuthContext,
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
  return microAuthContext(shellProps(), { epoch: state.epoch, tenantId: state.tenantId });
}

export function installCopilotAuth(client: AxiosInstance) {
  const auth = createAuthRequestAdapter({
    getToken: () => shellProps().token,
    getContext: copilotAuthContext,
    getRefresh: () => shellProps().refreshSession,
    expireSession: () => shellProps().expireSession?.(),
  });
  client.interceptors.request.use((config) => {
    auth.attach(config);
    const tenant = useCopilotStore.getState().tenantId;
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
      const result = await auth.recover(original, nextError, (config) => client.request(config));
      if (result) return result;
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

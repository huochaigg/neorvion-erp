import axios, {
  isAxiosError,
  isCancel,
  type AxiosError,
  type InternalAxiosRequestConfig,
} from 'axios';
import {
  ApiError,
  createAuthRequestAdapter,
  decideTenantHeader,
  isTenantInaccessibleError,
  microAuthContext,
  MICRO_EVENTS,
  responseApiError,
  SHELL_ROUTES,
  TENANT_HEADER,
  type ApiResponse,
} from '@neorvion/shared';
import { getShellProps } from '@/lib/runtime';
import { useKnowledgeTenantStore } from '@/stores/tenant-runtime';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 8000,
  withCredentials: true,
});

const auth = createAuthRequestAdapter({
  getToken: () => getShellProps().token,
  getContext: () => {
    const tenant = useKnowledgeTenantStore.getState();
    return microAuthContext(getShellProps(), {
      epoch: tenant.epoch,
      tenantId: tenant.currentTenantId,
    });
  },
  getRefresh: () => getShellProps().refreshSession,
  expireSession: () => getShellProps().expireSession?.(),
});

apiClient.interceptors.request.use((config) => {
  auth.attach(config);
  const tenantState = useKnowledgeTenantStore.getState();
  const decision = decideTenantHeader({
    method: config.method ?? 'get',
    url: config.url ?? '',
    baseURL: config.baseURL ?? apiClient.defaults.baseURL,
    skipTenantHeader: Boolean(config.skipTenantHeader),
    currentTenantId: tenantState.currentTenantId,
    isSwitching: false,
  });
  if (decision.action === 'attach') {
    config.headers[TENANT_HEADER] = String(decision.tenantId);
    config.tenantContextId = decision.tenantId;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (isCancel(error)) return Promise.reject(error);
    const axiosError = isAxiosError(error) ? (error as AxiosError<ApiResponse<unknown>>) : null;
    const original = axiosError?.config as InternalAxiosRequestConfig | undefined;
    const nextError = axiosError ? responseApiError(axiosError) : error;

    if (nextError instanceof ApiError && nextError.code === 40350) {
      if (auth.isCurrent(original)) window.location.assign(SHELL_ROUTES.changePassword);
      return Promise.reject(nextError);
    }
    if (nextError instanceof ApiError && isTenantInaccessibleError(nextError.code)) {
      if (auth.isCurrent(original)) window.$wujie?.bus.$emit(MICRO_EVENTS.tenantInaccessible);
      return Promise.reject(nextError);
    }
    if (nextError instanceof ApiError) {
      const result = await auth.recover(original, nextError, (config) => apiClient.request(config));
      if (result) return result;
      if (nextError.status >= 500) console.error('[knowledge-api]', nextError.message);
    }
    return Promise.reject(nextError);
  },
);

export async function unwrapApi<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const { data } = await promise;
  if (data.code !== 0) throw new ApiError(data.message, { code: data.code });
  return data.data;
}

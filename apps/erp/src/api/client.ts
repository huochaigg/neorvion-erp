import axios, { isAxiosError, isCancel, type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import {
  ApiError,
  decideTenantHeader,
  isTenantInaccessibleError,
  MICRO_EVENTS,
  SESSION_EXPIRED_MESSAGE,
  SHELL_ROUTES,
  TENANT_HEADER,
  type ApiResponse,
} from '@neorvion/shared';
import { getShellProps } from '@/lib/runtime';
import { useErpTenantStore } from '@/stores/tenant-runtime';

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
  return new ApiError(error.response.data?.message || error.message, {
    status,
    code,
    data: error.response.data?.data,
  });
}

apiClient.interceptors.request.use((config) => {
  const token = getShellProps().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  const tenantState = useErpTenantStore.getState();
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
    if (isCancel(error)) {
      return Promise.reject(error);
    }
    const axiosError = isAxiosError(error) ? error : null;
    const original = axiosError?.config as InternalAxiosRequestConfig | undefined;
    const nextError = axiosError ? toApiError(axiosError) : error;

    if (nextError instanceof ApiError && nextError.code === 40350) {
      window.location.assign(SHELL_ROUTES.changePassword);
      return Promise.reject(nextError);
    }
    if (nextError instanceof ApiError && isTenantInaccessibleError(nextError.code)) {
      window.$wujie?.bus.$emit(MICRO_EVENTS.tenantInaccessible);
      return Promise.reject(nextError);
    }

    const unauthorized = nextError instanceof ApiError && nextError.status === 401;
    if (unauthorized && original && !original._retried) {
      original._retried = true;
      const refreshSession = getShellProps().refreshSession;
      if (refreshSession) {
        try {
          const token = await refreshSession();
          original.headers.Authorization = `Bearer ${token}`;
          return apiClient.request(original);
        } catch {
          return Promise.reject(
            nextError instanceof ApiError
              ? nextError
              : new ApiError(SESSION_EXPIRED_MESSAGE, { status: 401, code: 40103 }),
          );
        }
      }
      window.$wujie?.bus.$emit(MICRO_EVENTS.unauthorized);
    }

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

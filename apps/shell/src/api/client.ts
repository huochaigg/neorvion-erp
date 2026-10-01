import axios, { isCancel, type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import {
  ApiError,
  AUTH_ERROR_CODE,
  decideTenantHeader,
  isTenantInaccessibleError,
  myTenantsQueryKey,
  SESSION_EXPIRED_MESSAGE,
  SHELL_ROUTES,
  TENANT_HEADER,
  type ApiResponse,
  type TokenPayload,
} from '@neorvion/shared';
import { getRegisteredQueryClient } from '@/lib/query-client';
import { endSessionDueToExpiry } from '@/lib/session';
import { clearTenantSelection } from '@/lib/switch-tenant';
import { useAuthStore } from '@/stores/auth-store';
import { useTenantStore } from '@/stores/tenant-store';
import { authClient } from './auth-client';
import { toApiError, unwrapApi } from './http';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 8000,
  withCredentials: true,
});

const AUTH_REFRESH_URL = '/api/v1/auth/refresh';

let refreshPromise: Promise<string> | null = null;

function handleTenantInaccessible() {
  const queryClient = getRegisteredQueryClient();
  if (queryClient) {
    clearTenantSelection(queryClient, { persist: true });
    void queryClient.invalidateQueries({ queryKey: myTenantsQueryKey() });
    return;
  }
  useTenantStore.getState().clearCurrentTenant();
}

/**
 * 全局只允许一个正在执行的 Refresh。
 * 启动恢复、业务 401、React Strict Mode 双调用共享同一 Promise，避免轮换后第二次 401 把会话清掉。
 */
function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = unwrapApi(authClient.post<ApiResponse<TokenPayload>>(AUTH_REFRESH_URL))
      .then((tokens) => {
        useAuthStore.getState().markAuthenticated(tokens.access_token);
        return tokens.access_token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

/** ERP 与 Shell 业务 401 共用。失败会清会话并提示重新登录。 */
export async function refreshSessionFromShell(): Promise<string> {
  try {
    return await refreshAccessToken();
  } catch (error) {
    endSessionDueToExpiry();
    throw error;
  }
}

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  const tenantState = useTenantStore.getState();
  const decision = decideTenantHeader({
    method: config.method ?? 'get',
    url: config.url ?? '',
    baseURL: config.baseURL ?? apiClient.defaults.baseURL,
    skipTenantHeader: Boolean(config.skipTenantHeader),
    currentTenantId: tenantState.currentTenantId,
    isSwitching: tenantState.isSwitching,
  });

  if (decision.action === 'reject') {
    return Promise.reject(new ApiError('正在切换企业，请稍候', { code: 40030 }));
  }
  if (decision.action === 'attach') {
    config.headers[TENANT_HEADER] = String(decision.tenantId);
    config.tenantContextId = decision.tenantId;
  }

  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiResponse<unknown>>) => {
    if (isCancel(error)) {
      return Promise.reject(error);
    }
    const original = error.config as InternalAxiosRequestConfig | undefined;
    const status = error.response?.status;
    const skipRefresh = Boolean(original?.skipAuthRefresh);
    const apiError = toApiError(error);

    if (apiError instanceof ApiError && apiError.code === 40350) {
      if (window.location.pathname !== SHELL_ROUTES.changePassword) {
        window.location.assign(SHELL_ROUTES.changePassword);
      }
      return Promise.reject(apiError);
    }

    if (apiError instanceof ApiError && isTenantInaccessibleError(apiError.code)) {
      handleTenantInaccessible();
      return Promise.reject(apiError);
    }

    if (status !== 401 || !original || original._retried || skipRefresh) {
      return Promise.reject(apiError);
    }

    original._retried = true;
    try {
      const token = await refreshAccessToken();
      original.headers.Authorization = `Bearer ${token}`;
      return apiClient.request(original);
    } catch {
      endSessionDueToExpiry();
      return Promise.reject(
        new ApiError(SESSION_EXPIRED_MESSAGE, { status: 401, code: AUTH_ERROR_CODE.revoked }),
      );
    }
  },
);

export { unwrapApi };

/** 仅用于应用启动恢复会话。401 表示没有有效 Refresh Cookie，属于预期结果。 */
export async function restoreSession(): Promise<string | null> {
  try {
    return await refreshAccessToken();
  } catch (error) {
    if (useAuthStore.getState().status !== 'authenticated') {
      useAuthStore.getState().markUnauthenticated();
    }
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

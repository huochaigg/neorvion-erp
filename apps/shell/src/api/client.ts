import axios, { isCancel, type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import {
  ApiError,
  createSessionRefresh,
  recoverExpiredRequest,
  decideTenantHeader,
  isTenantInaccessibleError,
  isTerminalAuthFailure,
  myTenantsQueryKey,
  SHELL_ROUTES,
  TENANT_HEADER,
  type ApiResponse,
  type TokenPayload,
} from '@neorvion/shared';
import { getRegisteredQueryClient } from '@/lib/query-client';
import { endSessionDueToExpiry } from '@/lib/session';
import { syncTokenToAliveSandboxes } from '@/micro/sandbox-health';
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

const sessionRefresh = createSessionRefresh({
  refresh: async (signal) =>
    (
      await unwrapApi(
        authClient.post<ApiResponse<TokenPayload>>(AUTH_REFRESH_URL, undefined, { signal }),
      )
    ).access_token,
  getToken: () => useAuthStore.getState().accessToken,
  updateToken: (token) => {
    useAuthStore.getState().markAuthenticated(token);
    syncTokenToAliveSandboxes(token);
  },
  onExpired: endSessionDueToExpiry,
  isInvalidRefresh: (error) => error instanceof ApiError && error.status === 401,
});
let tenantVersion = 0;
useTenantStore.subscribe((state, previous) => {
  if (state.currentTenantId !== previous.currentTenantId) tenantVersion++;
});
export function getAuthSessionVersion() {
  return sessionRefresh.version();
}

/** Explicit login/logout invalidates an in-flight refresh before it can write an old token. */
export function invalidatePendingRefresh() {
  sessionRefresh.invalidate();
}
export function expireSessionFromShell() {
  sessionRefresh.invalidate();
  endSessionDueToExpiry();
}

useAuthStore.subscribe((state, previous) => {
  if (state.accessToken && state.accessToken !== previous.accessToken) {
    syncTokenToAliveSandboxes(state.accessToken);
  }
});

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
  return sessionRefresh.refresh();
}

/** ERP 与 Shell 业务 401 共用。失败会清会话并提示重新登录。 */
export async function refreshSessionFromShell(): Promise<string> {
  try {
    return await refreshAccessToken();
  } catch (error) {
    throw error;
  }
}

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (!config._retried) {
    config.authTokenSent = token;
    config.authContext = `${sessionRefresh.version()}:${tenantVersion}:${useTenantStore.getState().currentTenantId ?? ''}`;
  }
  if (token && !config._retried) {
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

    if (
      apiError instanceof ApiError &&
      original &&
      isTerminalAuthFailure(apiError.status, apiError.code) &&
      original.authContext ===
        `${sessionRefresh.version()}:${tenantVersion}:${useTenantStore.getState().currentTenantId ?? ''}` &&
      original.authTokenSent === useAuthStore.getState().accessToken
    ) {
      expireSessionFromShell();
    }

    if (
      status !== 401 ||
      !original ||
      original._retried ||
      skipRefresh ||
      !(apiError instanceof ApiError)
    ) {
      return Promise.reject(apiError);
    }
    try {
      const result = await recoverExpiredRequest({
        status,
        code: apiError.code,
        tokenSent: original.authTokenSent ?? null,
        contextSent: original.authContext ?? '',
        context: () =>
          `${sessionRefresh.version()}:${tenantVersion}:${useTenantStore.getState().currentTenantId ?? ''}`,
        getToken: () => useAuthStore.getState().accessToken,
        refresh: refreshAccessToken,
        retry: (token) => {
          original._retried = true;
          original.authTokenSent = token;
          original.headers.Authorization = `Bearer ${token}`;
          return apiClient.request(original);
        },
      });
      if (result) return result;
    } catch (retryError) {
      if (
        retryError instanceof ApiError &&
        retryError.status === 401 &&
        original._retried &&
        original.authContext ===
          `${sessionRefresh.version()}:${tenantVersion}:${useTenantStore.getState().currentTenantId ?? ''}` &&
        original.authTokenSent === useAuthStore.getState().accessToken
      )
        expireSessionFromShell();
      return Promise.reject(retryError);
    }
    return Promise.reject(apiError);
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

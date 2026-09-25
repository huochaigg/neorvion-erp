import axios, { isAxiosError, isCancel, type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { ApiError, type ApiResponse, type TokenPayload } from '@neorvion/shared';
import { SHELL_ROUTES } from '@neorvion/shared';
import { useAuthStore } from '@/stores/auth-store';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 8000,
  withCredentials: true,
});

const AUTH_REFRESH_URL = '/api/v1/auth/refresh';
const AUTH_ANONYMOUS = new Set([
  '/api/v1/auth/login',
  '/api/v1/auth/register',
  '/api/v1/auth/public-key',
  AUTH_REFRESH_URL,
]);
const AUTH_SKIP_REFRESH = new Set([...AUTH_ANONYMOUS, '/api/v1/auth/logout']);

let refreshPromise: Promise<string | null> | null = null;

export function apiPathname(url?: string, baseURL?: string): string {
  if (!url) {
    return '';
  }
  try {
    const origin = baseURL && /^https?:\/\//i.test(baseURL) ? baseURL : 'http://local.invalid';
    const parsed = new URL(url, origin);
    return parsed.pathname.replace(/\/$/, '') || '/';
  } catch {
    return (url.split('?')[0] ?? '').replace(/\/$/, '');
  }
}

function shouldSkipAuthRefresh(config?: InternalAxiosRequestConfig): boolean {
  if (!config) {
    return false;
  }
  if (config.skipAuthRefresh) {
    return true;
  }
  return AUTH_SKIP_REFRESH.has(apiPathname(config.url, config.baseURL));
}

function redirectToLogin() {
  const from = `${window.location.pathname}${window.location.search}`;
  if (window.location.pathname === SHELL_ROUTES.login) {
    return;
  }
  const target = `${SHELL_ROUTES.login}?from=${encodeURIComponent(from)}`;
  window.location.assign(target);
}

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

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = apiClient
      .post<ApiResponse<TokenPayload>>(AUTH_REFRESH_URL, undefined, { skipAuthRefresh: true })
      .then((response) => {
        const token = response.data.data.access_token;
        useAuthStore.getState().setAccessToken(token);
        return token;
      })
      .catch((error: unknown) => {
        useAuthStore.getState().reset();
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

apiClient.interceptors.request.use((config) => {
  const path = apiPathname(config.url, config.baseURL);
  if (AUTH_ANONYMOUS.has(path)) {
    delete config.headers.Authorization;
    return config;
  }
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiResponse<unknown>>) => {
    if (isCancel(error)) {
      return Promise.reject(error);
    }
    const status = error.response?.status;
    const original = error.config;
    const skipRefresh = shouldSkipAuthRefresh(original);

    if (status !== 401 || !original || original._retried || skipRefresh) {
      return Promise.reject(isAxiosError(error) ? toApiError(error) : error);
    }

    original._retried = true;
    try {
      const token = await refreshAccessToken();
      if (!token) {
        redirectToLogin();
        return Promise.reject(new ApiError('登录已过期，请重新登录', { status: 401, code: 40100 }));
      }
      original.headers.Authorization = `Bearer ${token}`;
      return apiClient.request(original);
    } catch {
      redirectToLogin();
      return Promise.reject(new ApiError('登录已过期，请重新登录', { status: 401, code: 40104 }));
    }
  },
);

export async function unwrapApi<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const { data } = await promise;
  if (data.code !== 0) {
    throw new ApiError(data.message, { code: data.code });
  }
  return data.data;
}

export async function refreshSession(): Promise<TokenPayload | null> {
  try {
    return await unwrapApi(
      apiClient.post<ApiResponse<TokenPayload>>(AUTH_REFRESH_URL, undefined, { skipAuthRefresh: true }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

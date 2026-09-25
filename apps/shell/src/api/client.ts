import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type { ApiResponse, TokenPayload } from '@neorvion/shared';
import { SHELL_ROUTES } from '@neorvion/shared';
import { useAuthStore } from '@/stores/auth-store';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 8000,
  withCredentials: true,
});

const AUTH_REFRESH_URL = '/api/v1/auth/refresh';
const AUTH_SKIP_REFRESH = new Set([
  '/api/v1/auth/login',
  '/api/v1/auth/register',
  AUTH_REFRESH_URL,
]);

let refreshPromise: Promise<string | null> | null = null;

function redirectToLogin() {
  const from = `${window.location.pathname}${window.location.search}`;
  if (window.location.pathname === SHELL_ROUTES.login) {
    return;
  }
  const target = `${SHELL_ROUTES.login}?from=${encodeURIComponent(from)}`;
  window.location.assign(target);
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
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiResponse<unknown>>) => {
    const status = error.response?.status;
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const requestUrl = original?.url ?? '';
    const skipRefresh = original?.skipAuthRefresh || AUTH_SKIP_REFRESH.has(requestUrl);

    if (status !== 401 || !original || original._retried || skipRefresh) {
      const message = error.response?.data?.message ?? error.message;
      return Promise.reject(new Error(message));
    }

    original._retried = true;
    try {
      const token = await refreshAccessToken();
      if (!token) {
        redirectToLogin();
        return Promise.reject(error);
      }
      original.headers.Authorization = `Bearer ${token}`;
      return apiClient.request(original);
    } catch {
      redirectToLogin();
      return Promise.reject(new Error('登录已过期，请重新登录'));
    }
  },
);

export async function unwrapApi<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const { data } = await promise;
  if (data.code !== 0) {
    throw new Error(data.message);
  }
  return data.data;
}

export function refreshSession() {
  return unwrapApi(apiClient.post<ApiResponse<TokenPayload>>(AUTH_REFRESH_URL, undefined, { skipAuthRefresh: true }));
}

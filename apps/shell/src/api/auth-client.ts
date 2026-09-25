import axios, { isCancel } from 'axios';
import { toApiError } from './http';

/** 登录、注册、公钥、Refresh、Logout。永不自动 Refresh，也不附加 Access Token。 */
export const authClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 8000,
  withCredentials: true,
});

authClient.interceptors.request.use((config) => {
  config.skipAuthRefresh = true;
  delete config.headers.Authorization;
  return config;
});

authClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (isCancel(error)) {
      return Promise.reject(error);
    }
    return Promise.reject(toApiError(error));
  },
);

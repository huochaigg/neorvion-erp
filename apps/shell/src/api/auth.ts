import type { ApiResponse, TokenPayload, UserProfile } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function registerAccount(payload: {
  email: string;
  password: string;
  display_name: string;
}) {
  return unwrapApi(apiClient.post<ApiResponse<UserProfile>>('/api/v1/auth/register', payload));
}

export function loginAccount(payload: { email: string; password: string }) {
  return unwrapApi(apiClient.post<ApiResponse<TokenPayload>>('/api/v1/auth/login', payload));
}

export function logoutAccount() {
  return unwrapApi(apiClient.post<ApiResponse<null>>('/api/v1/auth/logout'));
}

export function fetchCurrentUser() {
  return unwrapApi(apiClient.get<ApiResponse<UserProfile>>('/api/v1/auth/me'));
}

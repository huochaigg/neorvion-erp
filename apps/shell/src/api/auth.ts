import type { ApiResponse, TokenPayload, UserProfile } from '@neorvion/shared';
import { encryptAuthPassword } from '@/lib/password';
import { authClient } from './auth-client';
import { apiClient, unwrapApi } from './client';

export async function registerAccount(payload: {
  email: string;
  password: string;
  display_name: string;
}) {
  const encrypted = await encryptAuthPassword(payload.password);
  return unwrapApi(
    authClient.post<ApiResponse<UserProfile>>('/api/v1/auth/register', {
      email: payload.email,
      display_name: payload.display_name,
      ...encrypted,
    }),
  );
}

export async function loginAccount(payload: { email: string; password: string }) {
  const encrypted = await encryptAuthPassword(payload.password);
  return unwrapApi(
    authClient.post<ApiResponse<TokenPayload>>('/api/v1/auth/login', {
      email: payload.email,
      ...encrypted,
    }),
  );
}

export function logoutAccount() {
  return unwrapApi(authClient.post<ApiResponse<null>>('/api/v1/auth/logout'));
}

export function fetchCurrentUser() {
  return unwrapApi(apiClient.get<ApiResponse<UserProfile>>('/api/v1/auth/me'));
}

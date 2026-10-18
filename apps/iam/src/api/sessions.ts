import type { ApiResponse } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export interface AuthSessionInfo {
  id: string;
  user_agent: string;
  ip_address: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at: string | null;
  revoke_reason: string | null;
  current: boolean;
}

export function fetchSessions(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<AuthSessionInfo[]>>('/api/v1/sessions', { signal }));
}

export function revokeSession(sessionId: string) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/sessions/${sessionId}`));
}

export function revokeAllSessions() {
  return unwrapApi(apiClient.post<ApiResponse<{ revoked: number }>>('/api/v1/sessions/revoke-all'));
}

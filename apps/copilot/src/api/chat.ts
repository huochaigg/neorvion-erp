import {
  ApiError,
  fetchWithAuthRecovery,
  TENANT_HEADER,
} from '@neorvion/shared';
import { shellProps } from '@/runtime';
import { useCopilotStore } from '@/store';
import { consumeSse } from '@/lib/sse';
import type { StreamEvent } from '@/types';
import { copilotAuthContext } from './client';

export async function streamChat(input: {
  conversationId: number;
  message: string;
  clientRequestId: string;
  signal: AbortSignal;
  onEvent: (e: StreamEvent) => void;
  skillMode: 'AUTO' | 'MANUAL' | 'NONE';
  skillKey?: string;
}) {
  const token = shellProps().token;
  const tenant = useCopilotStore.getState().tenantId;
  const contextSent = copilotAuthContext();
  const url = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8013'}/api/v1/conversations/${input.conversationId}/messages`;
  const body = JSON.stringify({
    client_request_id: input.clientRequestId,
    message: input.message,
    skill_mode: input.skillMode,
    skill_key: input.skillMode === 'MANUAL' ? input.skillKey : undefined,
  });
  const response = await fetchWithAuthRecovery({
    tokenSent: token,
    contextSent,
    getToken: () => shellProps().token,
    getContext: copilotAuthContext,
    getRefresh: () => shellProps().refreshSession,
    expireSession: () => shellProps().expireSession?.(),
    signal: input.signal,
    send: (accessToken) => fetch(url, {
      method: 'POST',
      signal: input.signal,
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
        [TENANT_HEADER]: String(tenant ?? ''),
      },
      body,
    }),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    throw new ApiError(failure?.message || '请求失败', {
      status: response.status,
      code: failure?.code ?? 0,
    });
  }
  await consumeSse(response, input.onEvent, input.signal);
}

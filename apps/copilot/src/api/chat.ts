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
import { api, unwrap } from './client';
import type { ApiResponse } from '@neorvion/shared';

function apiBase() {
  return import.meta.env.VITE_API_BASE_URL || 'http://localhost:8013';
}

async function openSse(
  url: string,
  init: { method: string; body?: string; lastEventId?: number; signal: AbortSignal },
  onEvent: (e: StreamEvent) => void,
) {
  const token = shellProps().token;
  const tenant = useCopilotStore.getState().tenantId;
  const contextSent = copilotAuthContext();
  const response = await fetchWithAuthRecovery({
    tokenSent: token,
    contextSent,
    getToken: () => shellProps().token,
    getContext: copilotAuthContext,
    getRefresh: () => shellProps().refreshSession,
    expireSession: () => shellProps().expireSession?.(),
    signal: init.signal,
    send: (accessToken) =>
      fetch(url, {
        method: init.method,
        signal: init.signal,
        headers: {
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
          [TENANT_HEADER]: String(tenant ?? ''),
          ...(init.lastEventId ? { 'Last-Event-ID': String(init.lastEventId) } : {}),
        },
        body: init.body,
      }),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    throw new ApiError(failure?.message || '请求失败', {
      status: response.status,
      code: failure?.code ?? 0,
    });
  }
  await consumeSse(response, onEvent, init.signal);
}

export async function streamChat(input: {
  conversationId: number;
  message: string;
  clientRequestId: string;
  signal: AbortSignal;
  onEvent: (e: StreamEvent) => void;
  skillMode: 'AUTO' | 'MANUAL' | 'NONE';
  skillKey?: string;
  retryOfMessageId?: number;
}) {
  await openSse(
    `${apiBase()}/api/v1/conversations/${input.conversationId}/messages`,
    {
      method: 'POST',
      signal: input.signal,
      body: JSON.stringify({
        client_request_id: input.clientRequestId,
        message: input.message,
        skill_mode: input.skillMode,
        skill_key: input.skillMode === 'MANUAL' ? input.skillKey : undefined,
        retry_of_message_id: input.retryOfMessageId,
      }),
    },
    input.onEvent,
  );
}

export async function subscribeChatRun(input: {
  conversationId: number;
  messageId: number;
  after?: number;
  signal: AbortSignal;
  onEvent: (e: StreamEvent) => void;
}) {
  const after = input.after ?? 0;
  const query = after > 0 ? `?after=${after}` : '';
  await openSse(
    `${apiBase()}/api/v1/conversations/${input.conversationId}/messages/${input.messageId}/events${query}`,
    {
      method: 'GET',
      signal: input.signal,
      lastEventId: after,
    },
    input.onEvent,
  );
}

export function cancelChatRun(conversationId: number, messageId: number) {
  return unwrap(
    api.post<ApiResponse<{ status: string; cancel_requested: boolean; message_id: number }>>(
      `/api/v1/conversations/${conversationId}/messages/${messageId}/cancel`,
    ),
  );
}

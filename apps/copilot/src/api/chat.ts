import {
  ApiError,
  isTerminalAuthFailure,
  prepareStreamResubmission,
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
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8013'}/api/v1/conversations/${input.conversationId}/messages`,
    {
      method: 'POST',
      signal: input.signal,
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token ?? ''}`,
        [TENANT_HEADER]: String(tenant ?? ''),
      },
      body: JSON.stringify({
        client_request_id: input.clientRequestId,
        message: input.message,
        skill_mode: input.skillMode,
        skill_key: input.skillMode === 'MANUAL' ? input.skillKey : undefined,
      }),
    },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (
      isTerminalAuthFailure(response.status, body?.code ?? 0) &&
      contextSent === copilotAuthContext() &&
      token === shellProps().token
    ) {
      shellProps().expireSession?.();
    }
    if (
      await prepareStreamResubmission({
        status: response.status,
        code: body?.code ?? 0,
        tokenSent: token,
        getToken: () => shellProps().token,
        contextSent,
        context: copilotAuthContext,
        refresh: shellProps().refreshSession,
      })
    ) {
      throw new ApiError('登录已恢复。请手动重新发送消息，避免重复执行任务。', {
        status: 401,
        code: body?.code ?? 0,
      });
    }
    throw new ApiError(body?.message || '请求失败', {
      status: response.status,
      code: body?.code ?? 0,
    });
  }
  await consumeSse(response, input.onEvent, input.signal);
}

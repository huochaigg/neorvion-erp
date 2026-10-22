import { TENANT_HEADER } from '@neorvion/shared';
import { shellProps } from '@/runtime';
import { useCopilotStore } from '@/store';
import { consumeSse } from '@/lib/sse';
import type { StreamEvent } from '@/types';

export async function streamChat(input: {
  conversationId: number;
  message: string;
  clientRequestId: string;
  signal: AbortSignal;
  onEvent: (e: StreamEvent) => void;
}) {
  const token = shellProps().token;
  const tenant = useCopilotStore.getState().tenantId;
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
      }),
    },
  );
  if (!response.ok) {
    throw new Error((await response.json().catch(() => null))?.message || '请求失败');
  }
  await consumeSse(response, input.onEvent);
}

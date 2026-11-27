import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AxiosError } from 'axios';
import { apiClient } from './client';
import { streamConversationMessage } from './rag';

const { state } = vi.hoisted(() => ({
  state: {
    token: 'old',
    tenantId: 1,
    epoch: 0,
    refreshSession: vi.fn(async () => 'new'),
    expireSession: vi.fn(),
  },
}));

vi.mock('@/lib/runtime', () => ({
  getShellProps: () => ({
    token: state.token,
    user: { id: 1 },
    refreshSession: state.refreshSession,
    expireSession: state.expireSession,
    sessionVersion: () => 0,
  }),
}));
vi.mock('@/stores/tenant-runtime', () => ({
  useKnowledgeTenantStore: {
    getState: () => ({ currentTenantId: state.tenantId, epoch: state.epoch }),
  },
}));
vi.mock('@/lib/knowledge-stream', () => ({ beginKnowledgeStream: () => new AbortController() }));
vi.mock('@/lib/sse', () => ({ consumeSse: vi.fn() }));

describe('Knowledge IAM recovery', () => {
  beforeEach(() => {
    state.token = 'old';
    state.tenantId = 1;
    state.epoch = 0;
    state.refreshSession = vi.fn(async () => {
      state.token = 'new';
      return 'new';
    });
    state.expireSession.mockClear();
  });

  it('retries an ordinary API only once after expiration', async () => {
    const previous = apiClient.defaults.adapter;
    const attempts: string[] = [];
    apiClient.defaults.adapter = async (config) => {
      attempts.push(String(config.headers.Authorization));
      const status = attempts.length === 1 ? 401 : 200;
      const response = {
        config,
        status,
        statusText: '',
        headers: {},
        data: { code: status === 401 ? 40103 : 0 },
      };
      if (status === 401)
        throw new (await import('axios')).AxiosError(
          'expired',
          'ERR_BAD_RESPONSE',
          config,
          undefined,
          response,
        );
      return response;
    };
    try {
      await apiClient.get('/api/v1/knowledge-bases');
      expect(attempts).toEqual(['Bearer old', 'Bearer new']);
      expect(state.refreshSession).toHaveBeenCalledTimes(1);
    } finally {
      apiClient.defaults.adapter = previous;
    }
  });

  it('silently refreshes and retries the same RAG Chat POST before SSE starts', async () => {
    const send = vi.fn(async (_url: string, init: RequestInit) =>
      (init.headers as Record<string, string>).Authorization === 'Bearer old'
        ? Response.json({ code: 40103 }, { status: 401 })
        : new Response('event: done\ndata: {"answer":"ok"}\n\n', { status: 200 }));
    vi.stubGlobal('fetch', send);
    try {
      const onEvent = vi.fn();
      await streamConversationMessage(
        1, { content: 'hello', strategy: 'HYBRID', rerank: true }, onEvent,
      );
      expect(send).toHaveBeenCalledTimes(2);
      expect(send.mock.calls[0][1].body).toBe(send.mock.calls[1][1].body);
      expect(send.mock.calls[0][1].signal).toBe(send.mock.calls[1][1].signal);
      expect((send.mock.calls[1][1].headers as Record<string, string>).Authorization).toBe('Bearer new');
      expect(state.refreshSession).toHaveBeenCalledTimes(1);
    } finally { vi.unstubAllGlobals(); }
  });

  it('ignores a late tenant-inaccessible response from the previous tenant', async () => {
    const previous = apiClient.defaults.adapter;
    apiClient.defaults.adapter = async (config) => {
      state.tenantId = 2;
      state.epoch++;
      throw new AxiosError('old tenant', 'ERR_BAD_RESPONSE', config, undefined, {
        config,
        status: 403,
        statusText: '',
        headers: {},
        data: { code: 40310 },
      });
    };
    try {
      await expect(apiClient.get('/api/v1/knowledge-bases')).rejects.toMatchObject({
        status: 403,
        code: 40310,
      });
      expect(state.tenantId).toBe(2);
      expect(state.refreshSession).not.toHaveBeenCalled();
    } finally {
      apiClient.defaults.adapter = previous;
    }
  });
});

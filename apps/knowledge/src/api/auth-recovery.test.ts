import { beforeEach, describe, expect, it, vi } from 'vitest';
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

  it('refreshes a stream session and asks for an explicit resend', async () => {
    const send = vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ code: 40103, message: 'expired' }),
    }));
    vi.stubGlobal('fetch', send);
    try {
      await expect(
        streamConversationMessage(
          1,
          { content: 'hello', strategy: 'HYBRID', rerank: true },
          vi.fn(),
        ),
      ).rejects.toThrow('请手动重新发送');
      expect(send).toHaveBeenCalledTimes(1);
      expect(state.refreshSession).toHaveBeenCalledTimes(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

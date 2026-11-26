import axios, { AxiosError, type AxiosAdapter, type AxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { installCopilotAuth } from './client';
import { streamChat } from './chat';

const { state } = vi.hoisted(() => ({
  state: {
    token: 'old' as string | null,
    tenantId: 1,
    epoch: 0,
    refreshSession: vi.fn(async () => 'new'),
    expireSession: vi.fn(),
  },
}));

vi.mock('@/runtime', () => ({
  shellProps: () => ({
    token: state.token,
    tenantId: state.tenantId,
    user: { id: 1 },
    refreshSession: state.refreshSession,
    expireSession: state.expireSession,
    sessionVersion: () => 0,
  }),
}));
vi.mock('@/store', () => ({ useCopilotStore: { getState: () => state } }));

function mockClient(reply: (config: AxiosRequestConfig) => number): AxiosAdapter {
  return async (config) => {
    const status = reply(config);
    const response = {
      config,
      data: { code: status === 401 ? 40103 : status === 403 ? 40310 : 0 },
      status,
      statusText: '',
      headers: {},
    };
    if (status !== 200)
      throw new AxiosError('failure', 'ERR_BAD_RESPONSE', config, undefined, response);
    return response;
  };
}

describe('Copilot axios IAM adapter', () => {
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

  it('retries an expired ordinary API and ERP options request with a new token', async () => {
    for (const path of ['/api/v1/conversations', '/api/v1/warehouses']) {
      const attempts: string[] = [];
      const client = axios.create({
        adapter: mockClient((config) => {
          attempts.push(String(config.headers?.Authorization));
          return attempts.length === 1 ? 401 : 200;
        }),
      });
      installCopilotAuth(client);
      await client.get(path);
      expect(attempts).toEqual(['Bearer old', 'Bearer new']);
      state.token = 'old';
    }
  });

  it('does not refresh on permission denial or replay after a second 401', async () => {
    const forbidden = axios.create({ adapter: mockClient(() => 403) });
    installCopilotAuth(forbidden);
    await expect(forbidden.get('/restricted')).rejects.toMatchObject({ status: 403 });
    expect(state.refreshSession).not.toHaveBeenCalled();

    const calls: string[] = [];
    const rejected = axios.create({
      adapter: mockClient((config) => {
        calls.push(String(config.headers?.Authorization));
        return 401;
      }),
    });
    installCopilotAuth(rejected);
    await expect(rejected.get('/expired')).rejects.toMatchObject({ status: 401 });
    expect(calls).toEqual(['Bearer old', 'Bearer new']);
    expect(state.expireSession).toHaveBeenCalledTimes(1);
  });

  it('does not replay after tenant switch during refresh', async () => {
    state.refreshSession = vi.fn(async () => {
      state.tenantId = 2;
      state.epoch++;
      state.token = 'new';
      return 'new';
    });
    const calls = vi.fn(() => 401);
    const client = axios.create({ adapter: mockClient(calls) });
    installCopilotAuth(client);
    await expect(client.get('/expired')).rejects.toThrow('租户已变化');
    expect(calls).toHaveBeenCalledTimes(1);
  });

  it('ends a revoked current session without refreshing, but ignores a late old-token refusal', async () => {
    const client = axios.create({ adapter: mockClient(() => 401) });
    installCopilotAuth(client);
    client.defaults.adapter = async (config) => {
      throw new AxiosError('revoked', 'ERR_BAD_RESPONSE', config, undefined, {
        config,
        status: 401,
        statusText: '',
        headers: {},
        data: { code: 40104 },
      });
    };
    await expect(client.get('/revoked')).rejects.toMatchObject({ status: 401, code: 40104 });
    expect(state.expireSession).toHaveBeenCalledTimes(1);
    expect(state.refreshSession).not.toHaveBeenCalled();
    state.expireSession.mockClear();
    client.defaults.adapter = async (config) => {
      state.token = 'new';
      throw new AxiosError('late', 'ERR_BAD_RESPONSE', config, undefined, {
        config,
        status: 401,
        statusText: '',
        headers: {},
        data: { code: 40104 },
      });
    };
    await expect(client.get('/late')).rejects.toMatchObject({ status: 401 });
    expect(state.expireSession).not.toHaveBeenCalled();
  });

  it('refreshes on a pre-stream 401 but never resends the chat POST automatically', async () => {
    const send = vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ code: 40103 }),
    }));
    vi.stubGlobal('fetch', send);
    try {
      await expect(
        streamChat({
          conversationId: 1,
          message: 'hello',
          clientRequestId: 'one',
          signal: new AbortController().signal,
          onEvent: vi.fn(),
          skillMode: 'NONE',
        }),
      ).rejects.toThrow('请手动重新发送');
      expect(send).toHaveBeenCalledTimes(1);
      expect(state.refreshSession).toHaveBeenCalledTimes(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

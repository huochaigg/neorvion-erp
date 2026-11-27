import axios, { AxiosError, type AxiosAdapter, type AxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { installCopilotAuth } from './client';
import { streamChat } from './chat';
import { createSessionRefresh } from '@neorvion/shared';

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

  it('silently retries Chat with the same message, request ID, tenant and AbortSignal', async () => {
    const signal = new AbortController().signal;
    const send = vi.fn(async (_url: string, init: RequestInit) =>
      init.headers && (init.headers as Record<string, string>).Authorization === 'Bearer old'
        ? Response.json({ code: 40103 }, { status: 401 })
        : new Response('event: done\ndata: {"answer":"ok"}\n\n', {
            status: 200, headers: { 'Content-Type': 'text/event-stream' },
          }));
    vi.stubGlobal('fetch', send);
    try {
      const onEvent = vi.fn();
      await streamChat({
        conversationId: 1, message: 'hello', clientRequestId: 'same-id',
        signal, onEvent, skillMode: 'NONE',
      });
      expect(send).toHaveBeenCalledTimes(2);
      const [first, second] = send.mock.calls;
      expect(first[0]).toBe(second[0]);
      expect(first[1].body).toBe(second[1].body);
      expect(first[1].body).toContain('same-id');
      expect(first[1].signal).toBe(signal);
      expect(second[1].signal).toBe(signal);
      expect((first[1].headers as Record<string, string>)['X-Tenant-ID'])
        .toBe((second[1].headers as Record<string, string>)['X-Tenant-ID']);
      expect((second[1].headers as Record<string, string>).Authorization).toBe('Bearer new');
      expect(state.refreshSession).toHaveBeenCalledTimes(1);
      expect(onEvent).toHaveBeenCalledTimes(1);
    } finally { vi.unstubAllGlobals(); }
  });

  it('shares one Shell refresh between an ordinary API and an expired Chat stream', async () => {
    let finishRefresh!: (token: string) => void;
    const refresh = vi.fn(() => new Promise<string>((resolve) => { finishRefresh = resolve; }));
    const coordinator = createSessionRefresh({
      refresh,
      getToken: () => state.token,
      updateToken: (token) => { state.token = token; },
      onExpired: state.expireSession,
      isInvalidRefresh: () => true,
    });
    state.refreshSession = vi.fn(() => coordinator.refresh());
    const client = axios.create({ adapter: mockClient((config) =>
      config.headers?.Authorization === 'Bearer old' ? 401 : 200) });
    installCopilotAuth(client);
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) =>
      (init.headers as Record<string, string>).Authorization === 'Bearer old'
        ? Response.json({ code: 40103 }, { status: 401 })
        : new Response('event: done\ndata: {"answer":"ok"}\n\n', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    try {
      const onEvent = vi.fn();
      const api = client.post('/api/v1/conversations', { title: 'one' });
      const chat = streamChat({
        conversationId: 1, message: 'hello', clientRequestId: 'same-id',
        skillMode: 'NONE', signal: new AbortController().signal, onEvent,
      });
      await vi.waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
      finishRefresh('new');
      await Promise.all([api, chat]);
      expect(refresh).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(onEvent).toHaveBeenCalledTimes(1);
    } finally { vi.unstubAllGlobals(); }
  });
});

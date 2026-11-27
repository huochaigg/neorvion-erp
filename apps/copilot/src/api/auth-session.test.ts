import { describe, expect, it, vi } from 'vitest';
import {
  createSessionRefresh,
  fetchWithAuthRecovery,
  recoverExpiredRequest,
} from '@neorvion/shared';

describe('shared IAM session recovery', () => {
  it('refreshes once for concurrent expired requests and retries each with the new token', async () => {
    let token: string | null = 'old';
    let complete!: (token: string) => void;
    const refresh = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          complete = resolve;
        }),
    );
    const session = createSessionRefresh({
      refresh,
      getToken: () => token,
      updateToken: (next) => {
        token = next;
      },
      onExpired: vi.fn(),
      isInvalidRefresh: () => true,
    });
    const retries = [vi.fn(async (next: string) => next), vi.fn(async (next: string) => next)];
    const recover = (retry: (token: string) => Promise<string>) =>
      recoverExpiredRequest({
        status: 401,
        code: 40103,
        tokenSent: 'old',
        getToken: () => token,
        contextSent: 'tenant-1',
        context: () => 'tenant-1',
        refresh: session.refresh,
        retry,
      });
    const pending = retries.map(recover);
    expect(refresh).toHaveBeenCalledTimes(1);
    complete('new');
    expect(await Promise.all(pending)).toEqual(['new', 'new']);
    expect(retries.every((retry) => retry.mock.calls.length === 1)).toBe(true);
  });

  it('invalidates an in-flight refresh on logout or login', async () => {
    let complete!: (token: string) => void;
    const update = vi.fn();
    const session = createSessionRefresh({
      refresh: () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
      getToken: () => 'old',
      updateToken: update,
      onExpired: vi.fn(),
      isInvalidRefresh: () => true,
    });
    const pending = session.refresh();
    session.invalidate();
    complete('stale');
    await expect(pending).rejects.toThrow('登录状态已变化');
    expect(update).not.toHaveBeenCalled();
  });

  it('invalid refresh notifies once, while a transient failure preserves the session', async () => {
    const expired = vi.fn();
    const failure = { status: 401 };
    const session = createSessionRefresh({
      refresh: async () => {
        throw failure;
      },
      getToken: () => 'old',
      updateToken: vi.fn(),
      onExpired: expired,
      isInvalidRefresh: (error) => error === failure,
    });
    const requests = [session.refresh(), session.refresh()];
    await Promise.all(requests.map((request) => expect(request).rejects.toBe(failure)));
    expect(expired).toHaveBeenCalledTimes(1);
    const network = createSessionRefresh({
      refresh: async () => {
        throw new Error('offline');
      },
      getToken: () => 'old',
      updateToken: vi.fn(),
      onExpired: expired,
      isInvalidRefresh: () => false,
    });
    await expect(network.refresh()).rejects.toThrow('offline');
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('never refreshes refresh itself, a permission refusal, or a second 401', async () => {
    const refresh = vi.fn(async () => 'new');
    for (const [status, code, retried, skip] of [
      [401, 40103, false, true],
      [403, 40310, false, false],
      [401, 40103, true, false],
      [401, 40104, false, false],
    ] as const) {
      expect(
        await recoverExpiredRequest({
          status,
          code,
          retried,
          skip,
          tokenSent: 'old',
          getToken: () => 'old',
          contextSent: 'a',
          context: () => 'a',
          refresh,
          retry: async () => 'new',
        }),
      ).toBeUndefined();
    }
    expect(refresh).not.toHaveBeenCalled();
  });

  it('does not replay an old tenant request after a switch', async () => {
    let context = 'tenant-1';
    let complete!: (token: string) => void;
    const retry = vi.fn(async () => 'result');
    const pending = recoverExpiredRequest({
      status: 401,
      code: 40103,
      tokenSent: 'old',
      getToken: () => 'old',
      contextSent: context,
      context: () => context,
      refresh: () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
      retry,
    });
    context = 'tenant-2';
    complete('new');
    await expect(pending).rejects.toThrow('租户已变化');
    expect(retry).not.toHaveBeenCalled();
  });

  it('does not start another refresh after the session has been cleared', async () => {
    const refresh = vi.fn(async () => 'new');
    const retry = vi.fn(async () => 'result');
    const result = await recoverExpiredRequest({
      status: 401,
      code: 40103,
      tokenSent: 'old',
      getToken: () => null,
      contextSent: 'a',
      context: () => 'a',
      refresh,
      retry,
    });
    expect(result).toBeUndefined();
    expect(refresh).not.toHaveBeenCalled();
    expect(retry).not.toHaveBeenCalled();
  });

  it('retries only a pre-stream HTTP 40103, preserving the same request payload', async () => {
    let token = 'old';
    const body = JSON.stringify({ client_request_id: 'same-id', message: 'hello' });
    const refresh = vi.fn(async () => { token = 'new'; return token; });
    const send = vi.fn(async (accessToken: string) => accessToken === 'old'
      ? Response.json({ code: 40103 }, { status: 401 })
      : new Response('event: done\ndata: {"answer":"ok"}\n\n', { status: 200 }));
    const result = await fetchWithAuthRecovery({
      tokenSent: token, contextSent: 'a', getToken: () => token, getContext: () => 'a',
      getRefresh: () => refresh, expireSession: vi.fn(),
      send: (accessToken) => { expect(body).toContain('same-id'); return send(accessToken); },
    });
    expect(result.status).toBe(200);
    expect(await result.text()).toContain('answer');
    expect(send.mock.calls.map(([accessToken]) => accessToken)).toEqual(['old', 'new']);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('never replays an established SSE response or a forbidden request', async () => {
    const refresh = vi.fn(async () => 'new');
    for (const initial of [
      new Response('event: error\ndata: {"code":40103}\n\n', { status: 200 }),
      new Response('event: tool_call\ndata: {"name":"write"}\n\nevent: error\ndata: {"code":40103}\n\n', { status: 200 }),
      Response.json({ code: 40310 }, { status: 403 })]) {
      const send = vi.fn(async () => initial);
      const result = await fetchWithAuthRecovery({
        tokenSent: 'old', contextSent: 'a', getToken: () => 'old', getContext: () => 'a',
        getRefresh: () => refresh, expireSession: vi.fn(), send,
      });
      expect(result).toBe(initial);
      expect(send).toHaveBeenCalledTimes(1);
    }
    expect(refresh).not.toHaveBeenCalled();
  });

  it('ends a revoked session without refreshing or resending the stream', async () => {
    const refresh = vi.fn(async () => 'new');
    const expireSession = vi.fn();
    const send = vi.fn(async () => Response.json({ code: 40104 }, { status: 401 }));
    const response = await fetchWithAuthRecovery({
      tokenSent: 'old', contextSent: 'a', getToken: () => 'old', getContext: () => 'a',
      getRefresh: () => refresh, expireSession, send,
    });
    expect(response.status).toBe(401);
    expect(send).toHaveBeenCalledTimes(1);
    expect(refresh).not.toHaveBeenCalled();
    expect(expireSession).toHaveBeenCalledTimes(1);
  });

  it('uses an already refreshed token without rotating the cookie again', async () => {
    const refresh = vi.fn(async () => 'new');
    const send = vi.fn(async (token: string) => token === 'old'
      ? Response.json({ code: 40103 }, { status: 401 }) : new Response('ok'));
    const response = await fetchWithAuthRecovery({
      tokenSent: 'old', contextSent: 'a', getToken: () => 'new', getContext: () => 'a',
      getRefresh: () => refresh, expireSession: vi.fn(), send,
    });
    expect(response.status).toBe(200);
    expect(send.mock.calls.map(([token]) => token)).toEqual(['old', 'new']);
    expect(refresh).not.toHaveBeenCalled();
  });

  it('stops after one retry when the new token is also rejected', async () => {
    let token = 'old';
    const expireSession = vi.fn();
    const refresh = vi.fn(async () => { token = 'new'; return token; });
    const send = vi.fn(async () => Response.json({ code: 40103 }, { status: 401 }));
    const response = await fetchWithAuthRecovery({
      tokenSent: token, contextSent: 'a', getToken: () => token, getContext: () => 'a',
      getRefresh: () => refresh, expireSession, send,
    });
    expect(response.status).toBe(401);
    expect(send).toHaveBeenCalledTimes(2);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(expireSession).toHaveBeenCalledTimes(1);
  });

  it('does not resend when cancelled or switched to another tenant during refresh', async () => {
    for (const change of ['abort', 'tenant']) {
      const controller = new AbortController();
      let context = 'tenant-1';
      let token = 'old';
      let complete!: (token: string) => void;
      const refresh = vi.fn(() => new Promise<string>((resolve) => { complete = resolve; }));
      const send = vi.fn(async () => Response.json({ code: 40103 }, { status: 401 }));
      const pending = fetchWithAuthRecovery({
        tokenSent: token, contextSent: context, getToken: () => token, getContext: () => context,
        getRefresh: () => refresh, expireSession: vi.fn(), signal: controller.signal, send,
      });
      await vi.waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
      if (change === 'abort') controller.abort(); else context = 'tenant-2';
      token = 'new';
      complete(token);
      await expect(pending).rejects.toThrow();
      expect(send).toHaveBeenCalledTimes(1);
    }
  });
});

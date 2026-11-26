import { describe, expect, it, vi } from 'vitest';
import {
  createSessionRefresh,
  prepareStreamResubmission,
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

  it('refreshes a stream session without automatically replaying the POST', async () => {
    const refresh = vi.fn(async () => 'new');
    expect(
      await prepareStreamResubmission({
        status: 401,
        code: 40103,
        tokenSent: 'old',
        getToken: () => 'old',
        contextSent: 'a',
        context: () => 'a',
        refresh,
      }),
    ).toBe(true);
    expect(
      await prepareStreamResubmission({
        status: 403,
        code: 40310,
        tokenSent: 'old',
        getToken: () => 'old',
        contextSent: 'a',
        context: () => 'a',
        refresh,
      }),
    ).toBe(false);
    expect(
      await prepareStreamResubmission({
        status: 401,
        code: 40103,
        tokenSent: 'old',
        getToken: () => 'old',
        contextSent: 'a',
        context: () => 'b',
        refresh,
      }),
    ).toBe(false);
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});

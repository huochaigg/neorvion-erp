import { createAuthRequestAdapter } from './request';

/** A pre-stream HTTP 40103 is emitted by the authentication dependency before the handler runs.
 * A 200 SSE response is returned unchanged: errors inside its body must never replay the request.
 */
export async function fetchWithAuthRecovery(options: {
  send: (token: string) => Promise<Response>;
  tokenSent: string | null;
  contextSent: string;
  getToken: () => string | null;
  getContext: () => string;
  getRefresh: () => (() => Promise<string>) | undefined;
  expireSession: () => void;
  signal?: AbortSignal;
}): Promise<Response> {
  const request = {
    headers: {} as { Authorization?: string },
    authTokenSent: options.tokenSent,
    authContext: options.contextSent,
    _retried: false,
  };
  const auth = createAuthRequestAdapter({
    getToken: options.getToken,
    getContext: options.getContext,
    getRefresh: () => {
      const refresh = options.getRefresh();
      if (!refresh) return undefined;
      return async () => {
        options.signal?.throwIfAborted();
        return refresh();
      };
    },
    expireSession: options.expireSession,
  });
  const readCode = async (response: Response) => {
    const body = await response.clone().json().catch(() => null) as { code?: number } | null;
    return typeof body?.code === 'number' ? body.code : 0;
  };

  options.signal?.throwIfAborted();
  const first = await options.send(options.tokenSent ?? '');
  if (first.status !== 401) return first;
  options.signal?.throwIfAborted();
  const code = await readCode(first);
  const retried = await auth.recover(request, { status: first.status, code }, async (config) => {
    options.signal?.throwIfAborted();
    const second = await options.send(config.authTokenSent ?? '');
    if (second.status === 401) {
      // Apply the same terminal-session rule, without allowing a third send.
      await auth.recover(config, { status: 401, code: await readCode(second) }, async () => second);
    }
    return second;
  });
  return retried ?? first;
}

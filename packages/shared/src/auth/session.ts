import { AUTH_ERROR_CODE } from '../types/auth';

/** The host owns the refresh cookie. Children receive only this delegated operation. */
export function createSessionRefresh(options: {
  refresh: (signal: AbortSignal) => Promise<string>;
  getToken: () => string | null;
  updateToken: (token: string) => void;
  onExpired: () => void;
  isInvalidRefresh: (error: unknown) => boolean;
}) {
  let generation = 0;
  let pending: Promise<string> | null = null;
  let controller: AbortController | null = null;
  return {
    version: () => generation,
    invalidate() {
      generation++;
      controller?.abort();
      controller = null;
      pending = null;
    },
    refresh(): Promise<string> {
      if (pending) return pending;
      const started = generation;
      const activeController = new AbortController();
      controller = activeController;
      const operation = options.refresh(activeController.signal).then(
        (token) => {
          if (started !== generation) {
            throw new Error('登录状态已变化，请重新发起请求');
          }
          options.updateToken(token);
          return token;
        },
        (error: unknown) => {
          if (started === generation && options.getToken() && options.isInvalidRefresh(error))
            options.onExpired();
          throw error;
        },
      );
      pending = operation;
      void operation
        .finally(() => {
          if (pending === operation) pending = null;
          if (controller === activeController) controller = null;
        })
        .catch(() => undefined);
      return operation;
    },
  };
}

export function isRecoverableExpiry(status: number, code: number, retried = false): boolean {
  return !retried && status === 401 && code === AUTH_ERROR_CODE.expired;
}

export function isTerminalAuthFailure(status: number, code: number): boolean {
  return (
    status === 401 && (code === AUTH_ERROR_CODE.revoked || code === AUTH_ERROR_CODE.invalidToken)
  );
}

/** A late response may belong to an old tenant or a login that has since been replaced. */
export async function recoverExpiredRequest<T>(options: {
  status: number;
  code: number;
  retried?: boolean;
  skip?: boolean;
  tokenSent: string | null;
  getToken: () => string | null;
  context: () => string;
  contextSent: string;
  refresh?: () => Promise<string>;
  retry: (token: string) => Promise<T>;
}): Promise<T | undefined> {
  if (
    options.skip ||
    !options.tokenSent ||
    !isRecoverableExpiry(options.status, options.code, options.retried)
  )
    return undefined;
  if (options.context() !== options.contextSent || !options.refresh) return undefined;
  const current = options.getToken();
  if (!current) return undefined;
  const token = current && current !== options.tokenSent ? current : await options.refresh();
  if (options.context() !== options.contextSent || !options.getToken()) {
    throw new Error('登录或租户已变化，请重新发起请求');
  }
  return options.retry(token);
}

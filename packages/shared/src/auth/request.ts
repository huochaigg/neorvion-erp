import { ApiError } from '../errors/api-error';
import type { ShellToErpProps } from '../types/bridge';
import { isTerminalAuthFailure, recoverExpiredRequest } from './session';

export interface AuthRequestConfig {
  headers: { Authorization?: unknown };
  _retried?: boolean;
  skipAuthRefresh?: boolean;
  authTokenSent?: string | null;
  authContext?: string;
}

export function microAuthContext(
  session: Pick<ShellToErpProps, 'sessionVersion' | 'user'>,
  tenant: { epoch: number; tenantId: number | null },
): string {
  return `${session.sessionVersion?.() ?? 0}:${session.user?.id ?? ''}:${tenant.epoch}:${tenant.tenantId ?? ''}`;
}

/** The caller supplies its own transport, tenant header, errors and navigation. */
export function createAuthRequestAdapter(options: {
  getToken: () => string | null;
  getContext: () => string;
  getRefresh: () => (() => Promise<string>) | undefined;
  expireSession: () => void;
}) {
  return {
    attach<C extends AuthRequestConfig>(config: C): C {
      const token = options.getToken();
      if (!config._retried) {
        config.authTokenSent = token;
        config.authContext = options.getContext();
      }
      if (token && !config._retried) config.headers.Authorization = `Bearer ${token}`;
      return config;
    },
    isCurrent(config: AuthRequestConfig | undefined): boolean {
      return Boolean(
        config &&
        config.authContext === options.getContext() &&
        config.authTokenSent &&
        config.authTokenSent === options.getToken(),
      );
    },
    async recover<C extends AuthRequestConfig, T>(
      config: C | undefined,
      error: Pick<ApiError, 'status' | 'code'>,
      retry: (config: C) => Promise<T>,
    ): Promise<T | undefined> {
      if (!config) return undefined;
      const sameRequestContext = config.authContext === options.getContext();
      const sameToken =
        Boolean(config.authTokenSent) && config.authTokenSent === options.getToken();
      if (
        sameRequestContext &&
        sameToken &&
        (isTerminalAuthFailure(error.status, error.code) ||
          (config._retried && error.status === 401))
      )
        options.expireSession();

      return recoverExpiredRequest({
        status: error.status,
        code: error.code,
        retried: config._retried,
        skip: config.skipAuthRefresh,
        tokenSent: config.authTokenSent ?? null,
        contextSent: config.authContext ?? '',
        context: options.getContext,
        getToken: options.getToken,
        refresh: options.getRefresh(),
        retry: (token) => {
          config._retried = true;
          config.authTokenSent = token;
          config.headers.Authorization = `Bearer ${token}`;
          return retry(config);
        },
      });
    },
  };
}

export function responseApiError(error: {
  message: string;
  response?: {
    status: number;
    data?: { code?: number; message?: string; data?: unknown };
  };
}): ApiError {
  const status = error.response?.status ?? 0;
  const code = error.response?.data?.code ?? 0;
  if (!error.response) return new ApiError('网络异常', { status, code });
  if (status >= 500) {
    return new ApiError(error.response.data?.message || '服务暂时不可用', { status, code });
  }
  return new ApiError(error.response.data?.message || error.message, {
    status,
    code,
    data: error.response.data?.data,
  });
}

/**
 * 哪些请求不应自动带 X-Tenant-ID。
 * 用 method + 规范化 pathname 精确匹配，不用字符串包含。
 */
const SKIP_TENANT_HEADER: ReadonlyArray<{ method: string; path: string }> = [
  { method: 'GET', path: '/api/crypto/public-key' },
  { method: 'POST', path: '/api/v1/auth/register' },
  { method: 'POST', path: '/api/v1/auth/login' },
  { method: 'POST', path: '/api/v1/auth/refresh' },
  { method: 'POST', path: '/api/v1/auth/logout' },
  { method: 'GET', path: '/api/v1/auth/me' },
  { method: 'POST', path: '/api/v1/tenants' },
  { method: 'GET', path: '/api/v1/tenants' },
  { method: 'GET', path: '/api/v1/health' },
];

export function normalizeRequestPath(url: string, baseURL?: string): string {
  try {
    const resolved = new URL(url, baseURL || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost'));
    return resolved.pathname.replace(/\/+$/, '') || '/';
  } catch {
    const path = url.split('?')[0]?.split('#')[0] ?? url;
    return path.replace(/\/+$/, '') || '/';
  }
}

export function shouldAttachTenantHeader(method: string, pathname: string): boolean {
  const normalizedMethod = method.toUpperCase();
  const normalizedPath = pathname.replace(/\/+$/, '') || '/';
  return !SKIP_TENANT_HEADER.some(
    (item) => item.method === normalizedMethod && item.path === normalizedPath,
  );
}

/** GET /api/v1/tenants/{id} 与 members 走路径参数，后端不强制请求头，但带上无害。 */
export function isTenantInaccessibleError(code: number): boolean {
  return code === 40310 || code === 40410;
}

export type TenantHeaderDecision =
  | { action: 'skip' }
  | { action: 'attach'; tenantId: number }
  | { action: 'reject'; reason: 'switching' };

/** 在请求发起时绑定租户上下文，不在响应返回时再取一次 currentTenantId。 */
export function decideTenantHeader(options: {
  method: string;
  url: string;
  baseURL?: string;
  skipTenantHeader?: boolean;
  currentTenantId: number | null;
  isSwitching: boolean;
}): TenantHeaderDecision {
  if (options.skipTenantHeader) {
    return { action: 'skip' };
  }
  const pathname = normalizeRequestPath(options.url, options.baseURL);
  if (!shouldAttachTenantHeader(options.method, pathname)) {
    return { action: 'skip' };
  }
  if (options.isSwitching) {
    return { action: 'reject', reason: 'switching' };
  }
  if (options.currentTenantId == null) {
    return { action: 'skip' };
  }
  return { action: 'attach', tenantId: options.currentTenantId };
}

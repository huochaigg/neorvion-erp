import 'axios';

declare module 'axios' {
  interface AxiosRequestConfig {
    skipAuthRefresh?: boolean;
    skipTenantHeader?: boolean;
    tenantContextId?: number | null;
    _retried?: boolean;
  }
}

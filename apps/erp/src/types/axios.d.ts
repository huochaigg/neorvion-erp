import 'axios';

declare module 'axios' {
  interface AxiosRequestConfig {
    skipTenantHeader?: boolean;
    tenantContextId?: number | null;
    _retried?: boolean;
    skipAuthRefresh?: boolean;
    authTokenSent?: string | null;
    authContext?: string;
  }
}

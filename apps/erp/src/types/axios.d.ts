import 'axios';

declare module 'axios' {
  interface AxiosRequestConfig {
    skipTenantHeader?: boolean;
    tenantContextId?: number | null;
  }
}

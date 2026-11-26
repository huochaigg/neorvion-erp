import 'axios';

declare module 'axios' {
  interface AxiosRequestConfig {
    _retried?: boolean;
    skipAuthRefresh?: boolean;
    authTokenSent?: string | null;
    authContext?: string;
  }
}

/** 后端统一响应结构。 */
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface HealthCheckData {
  app: 'ok';
  mysql: 'ok' | 'unavailable';
  redis: 'ok' | 'unavailable';
  milestone: string;
}

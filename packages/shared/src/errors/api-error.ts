/** 接口业务错误。不要把密码、Token、密文放进 message。 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: number;

  constructor(message: string, options?: { status?: number; code?: number }) {
    super(message);
    this.name = 'ApiError';
    this.status = options?.status ?? 0;
    this.code = options?.code ?? 0;
  }
}

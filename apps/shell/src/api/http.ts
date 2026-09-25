import { isAxiosError, type AxiosError } from 'axios';
import { ApiError, type ApiResponse } from '@neorvion/shared';

export function toApiError(error: unknown): unknown {
  if (!isAxiosError(error)) {
    return error;
  }
  const axiosError = error as AxiosError<ApiResponse<unknown>>;
  const status = axiosError.response?.status ?? 0;
  const code = axiosError.response?.data?.code ?? 0;
  if (!axiosError.response) {
    return new ApiError('网络异常', { status, code });
  }
  if (status >= 500) {
    return new ApiError(axiosError.response.data?.message || '服务暂时不可用', { status, code });
  }
  return new ApiError(axiosError.response.data?.message || axiosError.message, { status, code });
}

export async function unwrapApi<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const { data } = await promise;
  if (data.code !== 0) {
    throw new ApiError(data.message, { code: data.code });
  }
  return data.data;
}

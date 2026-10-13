import type {
  ApiResponse,
  KnowledgeBase,
  KnowledgeBaseCreatePayload,
  KnowledgeBaseList,
  KnowledgeBaseUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchKnowledgeBases(
  params: {
    q?: string;
    status?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeBaseList>>('/api/v1/knowledge-bases', {
      params: {
        q: params.q || undefined,
        status: params.status || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchKnowledgeBase(id: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeBase>>(`/api/v1/knowledge-bases/${id}`, { signal }),
  );
}

export function createKnowledgeBase(payload: KnowledgeBaseCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeBase>>('/api/v1/knowledge-bases', payload));
}

export function updateKnowledgeBase(id: number, payload: KnowledgeBaseUpdatePayload) {
  return unwrapApi(
    apiClient.patch<ApiResponse<KnowledgeBase>>(`/api/v1/knowledge-bases/${id}`, payload),
  );
}

export function deleteKnowledgeBase(id: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/knowledge-bases/${id}`));
}

import type {
  ApiResponse,
  KnowledgeChunk,
  KnowledgeChunkList,
  KnowledgeChunkParams,
  KnowledgeChunkUpdatePayload,
  KnowledgeDocumentDetail,
  KnowledgeDocumentList,
  KnowledgeOverview,
  KnowledgeTask,
  KnowledgeTaskList,
  KnowledgeUploadBatch,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchKnowledgeOverview(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<KnowledgeOverview>>('/api/v1/overview', { signal }));
}

export function fetchDocuments(
  params: {
    knowledgeBaseId?: number;
    q?: string;
    status?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeDocumentList>>('/api/v1/documents', {
      params: {
        knowledge_base_id: params.knowledgeBaseId,
        q: params.q || undefined,
        status: params.status || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchDocument(id: number, signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<KnowledgeDocumentDetail>>(`/api/v1/documents/${id}`, { signal }));
}

export function uploadDocuments(knowledgeBaseId: number, files: File[]) {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeUploadBatch>>(
      `/api/v1/knowledge-bases/${knowledgeBaseId}/documents`,
      form,
      { timeout: 120000 },
    ),
  );
}

export async function downloadDocument(id: number, filename: string) {
  const response = await apiClient.get(`/api/v1/documents/${id}/file`, {
    responseType: 'blob',
    timeout: 60000,
  });
  const url = URL.createObjectURL(response.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function deleteDocument(id: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/documents/${id}`));
}

export function requestParse(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeTask>>(`/api/v1/documents/${id}/parse`));
}

export function requestChunk(id: number, payload: KnowledgeChunkParams) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeTask>>(`/api/v1/documents/${id}/chunk`, payload));
}

export function fetchChunks(
  params: {
    knowledgeBaseId?: number;
    documentId?: number;
    enabled?: boolean;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeChunkList>>('/api/v1/chunks', {
      params: {
        knowledge_base_id: params.knowledgeBaseId,
        document_id: params.documentId,
        enabled: params.enabled,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function updateChunk(id: number, payload: KnowledgeChunkUpdatePayload) {
  return unwrapApi(apiClient.patch<ApiResponse<KnowledgeChunk>>(`/api/v1/chunks/${id}`, payload));
}

export function fetchProcessingTasks(
  params: {
    knowledgeBaseId?: number;
    documentId?: number;
    status?: string;
    taskType?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeTaskList>>('/api/v1/tasks', {
      params: {
        knowledge_base_id: params.knowledgeBaseId,
        document_id: params.documentId,
        status: params.status || undefined,
        task_type: params.taskType || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function retryProcessingTask(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeTask>>(`/api/v1/tasks/${id}/retry`));
}

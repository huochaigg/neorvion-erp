import {
  ApiError,
  TENANT_HEADER,
  type ApiResponse,
  type KnowledgeChatAskPayload,
  type KnowledgeConversation,
  type KnowledgeConversationDetail,
  type KnowledgeConversationList,
  type KnowledgeIndexStatus,
  type KnowledgeModelProfile,
  type KnowledgeSearchPayload,
  type KnowledgeRetrievalDefaults,
  type KnowledgeSearchResult,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';
import { beginKnowledgeStream } from '@/lib/knowledge-stream';
import { getShellProps } from '@/lib/runtime';
import { consumeSse } from '@/lib/sse';
import { useKnowledgeTenantStore } from '@/stores/tenant-runtime';

export function searchKnowledge(payload: KnowledgeSearchPayload, signal?: AbortSignal) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeSearchResult>>('/api/v1/search', payload, { signal }));
}

export function fetchRetrievalDefaults(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<KnowledgeRetrievalDefaults>>('/api/v1/retrieval/defaults', { signal }));
}

export function testRetrieval(payload: KnowledgeSearchPayload, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeSearchResult>>('/api/v1/retrieval/test', payload, { signal }),
  );
}

export function fetchIndexStatus(knowledgeBaseId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeIndexStatus>>(
      `/api/v1/knowledge-bases/${knowledgeBaseId}/index-status`,
      { signal },
    ),
  );
}

export function reindexKnowledgeBase(knowledgeBaseId: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<{ queued: number }>>(`/api/v1/knowledge-bases/${knowledgeBaseId}/reindex`),
  );
}

export function fetchConversations(params: { page: number; pageSize: number }, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeConversationList>>('/api/v1/conversations', {
      params: { page: params.page, page_size: params.pageSize },
      signal,
    }),
  );
}

export function fetchConversation(id: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeConversationDetail>>(`/api/v1/conversations/${id}`, { signal }),
  );
}

export function createConversation(payload: { title?: string; knowledge_base_ids?: number[] }) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeConversation>>('/api/v1/conversations', payload));
}

export function updateConversation(
  id: number,
  payload: { title?: string; knowledge_base_ids?: number[] },
) {
  return unwrapApi(apiClient.patch<ApiResponse<KnowledgeConversation>>(`/api/v1/conversations/${id}`, payload));
}

export function deleteConversation(id: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/conversations/${id}`));
}

export function fetchModels(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<KnowledgeModelProfile[]>>('/api/v1/models', { signal }));
}

export function testModel(kind: string) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeModelProfile>>('/api/v1/models/test', { kind }));
}

export async function streamConversationMessage(
  conversationId: number,
  payload: KnowledgeChatAskPayload,
  onEvent: (event: string, data: unknown) => void,
  externalSignal?: AbortSignal,
): Promise<void> {
  const controller = beginKnowledgeStream();
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
    }
  }
  const token = getShellProps().token;
  const tenantId = useKnowledgeTenantStore.getState().currentTenantId;
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
    'Content-Type': 'application/json',
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (tenantId != null) {
    headers[TENANT_HEADER] = String(tenantId);
  }
  const baseURL = apiClient.defaults.baseURL ?? '';
  const response = await fetch(`${baseURL}/api/v1/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    credentials: 'include',
    signal: controller.signal,
  });
  if (!response.ok) {
    let message = '问答请求失败';
    try {
      const body = (await response.json()) as ApiResponse<unknown>;
      message = body.message || message;
      throw new ApiError(message, { status: response.status, code: body.code });
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      throw new ApiError(message, { status: response.status });
    }
  }
  await consumeSse(response, { onEvent });
}

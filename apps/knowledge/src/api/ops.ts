import type {
  ApiResponse,
  KnowledgeApiKey,
  KnowledgeApiKeyList,
  KnowledgeAuditLogList,
  KnowledgeGrant,
  KnowledgeGrantList,
  KnowledgeRecycleBatch,
  KnowledgeRecycleList,
  KnowledgeRevision,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchRecycle(params: { page: number; pageSize: number }, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeRecycleList>>('/api/v1/recycle', {
      params: { page: params.page, page_size: params.pageSize },
      signal,
    }),
  );
}

export function restoreRecycleBatch(items: { resource_type: string; id: number }[]) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeRecycleBatch>>('/api/v1/recycle/restore-batch', { items }));
}

export function purgeRecycleBatch(items: { resource_type: string; id: number }[]) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeRecycleBatch>>('/api/v1/recycle/purge-batch', { items }));
}

export function emptyRecycle(payload: { confirm: boolean; expected_count: number }) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeRecycleBatch>>('/api/v1/recycle/empty', payload));
}

export function restoreKnowledgeBase(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<unknown>>(`/api/v1/knowledge-bases/${id}/restore`));
}

export function purgeKnowledgeBase(id: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/knowledge-bases/${id}/purge`));
}

export function restoreDocument(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<unknown>>(`/api/v1/documents/${id}/restore`));
}

export function purgeDocument(id: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/documents/${id}/purge`));
}

export function fetchGrants(knowledgeBaseId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeGrantList>>(`/api/v1/knowledge-bases/${knowledgeBaseId}/grants`, { signal }),
  );
}

export function upsertGrant(knowledgeBaseId: number, payload: { user_id: number; permission: string }) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeGrant>>(`/api/v1/knowledge-bases/${knowledgeBaseId}/grants`, payload),
  );
}

export function deleteGrant(knowledgeBaseId: number, grantId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/knowledge-bases/${knowledgeBaseId}/grants/${grantId}`));
}

export function fetchRevisions(documentId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<{ items: KnowledgeRevision[] }>>(`/api/v1/documents/${documentId}/revisions`, { signal }),
  );
}

export function replaceDocument(documentId: number, file: Blob, note?: string) {
  const form = new FormData();
  form.append('file', file);
  if (note) form.append('note', note);
  return unwrapApi(apiClient.post<ApiResponse<unknown>>(`/api/v1/documents/${documentId}/replace`, form, { timeout: 120000 }));
}

export function restoreRevision(documentId: number, revisionId: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<unknown>>(`/api/v1/documents/${documentId}/revisions/${revisionId}/restore`),
  );
}

export function fetchApiKeys(params: { page: number; pageSize: number }, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeApiKeyList>>('/api/v1/api-keys', {
      params: { page: params.page, page_size: params.pageSize },
      signal,
    }),
  );
}

export function createApiKey(payload: {
  name: string;
  scopes: string[];
  knowledge_base_ids?: number[];
}) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeApiKey>>('/api/v1/api-keys', payload));
}

export function revokeApiKey(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeApiKey>>(`/api/v1/api-keys/${id}/revoke`));
}

export function fetchAuditLogs(
  params: { action?: string; resourceType?: string; page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeAuditLogList>>('/api/v1/audit-logs', {
      params: {
        action: params.action || undefined,
        resource_type: params.resourceType || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

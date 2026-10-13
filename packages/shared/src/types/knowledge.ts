/** 与 Knowledge 后端 `KnowledgeBaseOut` / `KnowledgeBaseListOut` 对齐。 */

export const KNOWLEDGE_BASE_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const KNOWLEDGE_DOCUMENT_STATUS = {
  pending: 'PENDING',
  processing: 'PROCESSING',
  completed: 'COMPLETED',
  failed: 'FAILED',
} as const;

export const KNOWLEDGE_BASE_STATUS_LABEL: Record<string, string> = {
  ACTIVE: '启用',
  DISABLED: '禁用',
};

export interface KnowledgeBase {
  id: number;
  tenant_id: number;
  name: string;
  description: string | null;
  status: string;
  document_count: number;
  created_by: number;
  updated_by: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBaseList {
  items: KnowledgeBase[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeBaseCreatePayload {
  name: string;
  description?: string | null;
}

export interface KnowledgeBaseUpdatePayload {
  name?: string;
  description?: string | null;
  status?: string;
}

export function knowledgeBaseStatusLabel(status: string): string {
  return KNOWLEDGE_BASE_STATUS_LABEL[status] ?? status;
}

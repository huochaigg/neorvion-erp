/** 与 Knowledge 后端 schema 对齐。 */

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

export const KNOWLEDGE_TASK_STATUS = {
  queued: 'QUEUED',
  running: 'RUNNING',
  success: 'SUCCESS',
  failed: 'FAILED',
} as const;

export const KNOWLEDGE_TASK_TYPE = {
  parse: 'PARSE',
  chunk: 'CHUNK',
} as const;

export const KNOWLEDGE_CHUNK_STRATEGY = {
  fixed: 'FIXED',
  recursive: 'RECURSIVE',
} as const;

export const KNOWLEDGE_BASE_STATUS_LABEL: Record<string, string> = {
  ACTIVE: '启用',
  DISABLED: '禁用',
};

export const KNOWLEDGE_DOCUMENT_STATUS_LABEL: Record<string, string> = {
  PENDING: '待处理',
  PROCESSING: '处理中',
  COMPLETED: '已完成',
  FAILED: '失败',
};

export const KNOWLEDGE_TASK_STATUS_LABEL: Record<string, string> = {
  QUEUED: '排队中',
  RUNNING: '运行中',
  SUCCESS: '成功',
  FAILED: '失败',
};

export const KNOWLEDGE_TASK_TYPE_LABEL: Record<string, string> = {
  PARSE: '解析',
  CHUNK: '切片',
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

export interface KnowledgeDocument {
  id: number;
  tenant_id: number;
  knowledge_base_id: number;
  filename: string;
  file_size: number;
  mime_type: string;
  extension: string;
  sha256: string;
  status: string;
  error_message: string | null;
  warning_message: string | null;
  extracted_char_count: number;
  chunk_strategy: string | null;
  chunk_size: number | null;
  chunk_overlap: number | null;
  chunk_unit: string;
  active_chunk_version: number;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  extracted_preview: string | null;
  extract_meta: Record<string, unknown> | null;
}

export interface KnowledgeDocumentList {
  items: KnowledgeDocument[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeUploadItem {
  filename: string;
  ok: boolean;
  message: string;
  document: KnowledgeDocument | null;
}

export interface KnowledgeUploadBatch {
  items: KnowledgeUploadItem[];
  succeeded: number;
  failed: number;
}

export interface KnowledgeChunk {
  id: number;
  tenant_id: number;
  knowledge_base_id: number;
  document_id: number;
  version: number;
  chunk_index: number;
  content: string;
  char_count: number;
  page_no: number | null;
  heading: string | null;
  source_start: number | null;
  source_end: number | null;
  status: string;
  enabled: boolean;
  updated_at: string;
}

export interface KnowledgeChunkList {
  items: KnowledgeChunk[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeChunkUpdatePayload {
  content?: string;
  enabled?: boolean;
}

export interface KnowledgeChunkParams {
  strategy: string;
  chunk_size: number;
  chunk_overlap: number;
}

export interface KnowledgeTask {
  id: number;
  tenant_id: number;
  knowledge_base_id: number;
  document_id: number;
  task_type: string;
  status: string;
  progress: number;
  attempt: number;
  error_message: string | null;
  payload: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface KnowledgeTaskList {
  items: KnowledgeTask[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeOverview {
  knowledge_base_count: number;
  document_count: number;
  chunk_count: number;
  document_completed: number;
  document_failed: number;
  pending_task_count: number;
  failed_task_count: number;
  recent_documents: KnowledgeDocument[];
  pending_tasks: KnowledgeTask[];
}

export function knowledgeBaseStatusLabel(status: string): string {
  return KNOWLEDGE_BASE_STATUS_LABEL[status] ?? status;
}

export function knowledgeDocumentStatusLabel(status: string): string {
  return KNOWLEDGE_DOCUMENT_STATUS_LABEL[status] ?? status;
}

export function knowledgeTaskStatusLabel(status: string): string {
  return KNOWLEDGE_TASK_STATUS_LABEL[status] ?? status;
}

export function knowledgeTaskTypeLabel(type: string): string {
  return KNOWLEDGE_TASK_TYPE_LABEL[type] ?? type;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

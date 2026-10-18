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
  embed: 'EMBED',
} as const;

export const KNOWLEDGE_RETRIEVAL_STRATEGY = {
  vector: 'VECTOR',
  keyword: 'KEYWORD',
  hybrid: 'HYBRID',
} as const;

export const KNOWLEDGE_MESSAGE_ROLE = {
  user: 'USER',
  assistant: 'ASSISTANT',
} as const;

export const KNOWLEDGE_MESSAGE_STATUS = {
  streaming: 'STREAMING',
  completed: 'COMPLETED',
  failed: 'FAILED',
  cancelled: 'CANCELLED',
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
  EMBED: '向量化',
};

export const KNOWLEDGE_RETRIEVAL_STRATEGY_LABEL: Record<string, string> = {
  VECTOR: '向量检索',
  KEYWORD: '关键词检索',
  HYBRID: '混合检索',
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
  document_available?: boolean;
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

export interface KnowledgeSearchHit {
  chunk_id: number;
  document_id: number;
  knowledge_base_id: number;
  filename: string;
  content: string;
  page_no: number | null;
  heading: string | null;
  chunk_index: number;
  version: number;
  final_rank: number;
  vector_score: number | null;
  keyword_score: number | null;
  rrf_score: number | null;
  rerank_score: number | null;
}

export interface KnowledgeSearchResult {
  items: KnowledgeSearchHit[];
  strategy: string;
  rerank_applied: boolean;
  rerank_degraded: boolean;
  stages: Record<string, unknown>;
  latency_ms: number;
  knowledge_base_ids: number[];
}

export interface KnowledgeSearchPayload {
  query: string;
  knowledge_base_ids?: number[];
  strategy?: string;
  top_k?: number;
  candidate_k?: number;
  similarity_threshold?: number | null;
  vector_k?: number | null;
  keyword_k?: number | null;
  rrf_k?: number | null;
  rerank?: boolean;
}

export interface KnowledgeRetrievalDefaults {
  default_top_k: number;
  default_candidate_k: number;
  rrf_k: number;
  default_chunk_size: number;
  default_chunk_overlap: number;
  embedding_model: string;
  embedding_dimensions: number;
  worker_concurrency: number;
  similarity_threshold: number | null;
  rerank_model: string;
}

export interface KnowledgeIndexStatus {
  knowledge_base_id: number;
  model_name: string;
  dimensions: number;
  total_active_chunks: number;
  ready: number;
  pending: number;
  stale: number;
  failed: number;
  incompatible?: number;
  needs_reindex?: boolean;
}

export interface KnowledgeConversation {
  id: number;
  tenant_id: number;
  title: string;
  knowledge_base_ids: number[];
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeConversationList {
  items: KnowledgeConversation[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeCitation {
  chunk_id: number;
  document_id: number;
  knowledge_base_id: number;
  filename: string;
  page_no: number | null;
  heading: string | null;
  snippet: string;
  rank: number;
  vector_score: number | null;
  keyword_score: number | null;
  rrf_score: number | null;
  rerank_score: number | null;
}

export interface KnowledgeMessage {
  id: number;
  conversation_id: number;
  role: string;
  content: string;
  status: string;
  retrieval_strategy: string | null;
  usage: Record<string, unknown> | null;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
  citations: KnowledgeCitation[];
}

export interface KnowledgeConversationDetail extends KnowledgeConversation {
  messages: KnowledgeMessage[];
}

export interface KnowledgeChatAskPayload {
  content: string;
  strategy?: string;
  top_k?: number;
  rerank?: boolean;
  regenerate_of?: number | null;
}

export interface KnowledgeModelProfile {
  id: number | null;
  kind: string;
  name: string;
  provider: string;
  base_url: string;
  model_name: string;
  dimensions: number | null;
  api_key_env: string;
  has_api_key: boolean;
  is_default: boolean;
  enabled: boolean;
  is_system: boolean;
  last_tested_at: string | null;
  last_test_ok: boolean | null;
  last_test_message: string | null;
}

export function knowledgeRetrievalStrategyLabel(strategy: string): string {
  return KNOWLEDGE_RETRIEVAL_STRATEGY_LABEL[strategy] ?? strategy;
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

export const KNOWLEDGE_QUESTION_TYPE = {
  factual: 'FACTUAL',
  multiCondition: 'MULTI_CONDITION',
  multiDoc: 'MULTI_DOC',
  paraphrase: 'PARAPHRASE',
  mixedLang: 'MIXED_LANG',
  long: 'LONG',
  unanswerable: 'UNANSWERABLE',
  hallucination: 'HALLUCINATION',
} as const;

export const KNOWLEDGE_QUESTION_TYPE_LABEL: Record<string, string> = {
  FACTUAL: '事实型',
  MULTI_CONDITION: '多条件',
  MULTI_DOC: '多文档综合',
  PARAPHRASE: '同义/口语',
  MIXED_LANG: '中英混合',
  LONG: '长问题',
  UNANSWERABLE: '无答案',
  HALLUCINATION: '易幻觉',
};

export const KNOWLEDGE_ANNOTATION_STATUS_LABEL: Record<string, string> = {
  PENDING: '待标注',
  LABELED: '已标注',
  READY: '可评测',
};

export const KNOWLEDGE_RUN_STATUS_LABEL: Record<string, string> = {
  QUEUED: '排队中',
  RUNNING: '运行中',
  SUCCESS: '成功',
  FAILED: '失败',
  CANCELLED: '已取消',
};

export function knowledgeQuestionTypeLabel(value: string): string {
  return KNOWLEDGE_QUESTION_TYPE_LABEL[value] ?? value;
}

export function knowledgeAnnotationStatusLabel(value: string): string {
  return KNOWLEDGE_ANNOTATION_STATUS_LABEL[value] ?? value;
}

export function knowledgeRunStatusLabel(value: string): string {
  return KNOWLEDGE_RUN_STATUS_LABEL[value] ?? value;
}

export interface KnowledgeEvalDataset {
  id: number;
  tenant_id: number;
  name: string;
  description: string | null;
  knowledge_base_ids: number[];
  current_version: number;
  pending_count: number;
  labeled_count: number;
  ready_count: number;
  total_cases: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeEvalDatasetList {
  items: KnowledgeEvalDataset[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeEvalJudgment {
  id: number;
  chunk_id: number;
  document_id: number;
  relevance: number;
  source_key: string;
  chunk_version: number;
  filename: string;
  snippet: string;
  stale: boolean;
}

export interface KnowledgeEvalCase {
  id: number;
  dataset_id: number;
  question: string;
  expected_answer: string | null;
  question_type: string;
  difficulty: number;
  tags: string[];
  is_unanswerable: boolean;
  annotation_status: string;
  source: string;
  external_key?: string | null;
  needs_human_review?: boolean;
  judgments: KnowledgeEvalJudgment[];
  created_at: string;
  updated_at: string;
}

export interface KnowledgeEvalProbe {
  case_id: number;
  question: string;
  expected_answer?: string | null;
  is_unanswerable: boolean;
  strategy: string;
  rerank_applied: boolean;
  rerank_degraded: boolean;
  latency_ms: number;
  stages: Record<string, unknown>;
  retrieved: Record<string, unknown>[];
  retrieval_metrics: Record<string, unknown> | null;
  answer: string | null;
  citations: Record<string, unknown>[];
  usage: Record<string, unknown> | null;
  needs_human_review: boolean;
}

export interface KnowledgeGrant {
  id: number;
  knowledge_base_id: number;
  user_id: number;
  permission: string;
  created_by: number;
  created_at: string;
}

export interface KnowledgeGrantList {
  items: KnowledgeGrant[];
  restricted: boolean;
}

export interface KnowledgeRevision {
  id: number;
  document_id: number;
  revision: number;
  filename: string;
  sha256: string;
  file_size: number;
  mime_type: string;
  chunk_version: number;
  note: string | null;
  created_by: number;
  created_at: string;
}

export interface KnowledgeRecycleItem {
  resource_type: string;
  id: number;
  knowledge_base_id: number | null;
  name: string;
  deleted_at: string;
  deleted_by: number | null;
}

export interface KnowledgeRecycleList {
  items: KnowledgeRecycleItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeRecycleBatch {
  succeeded: number;
  skipped: number;
  failed: number;
  remaining: number;
  errors: { resource_type?: string; id?: number; message?: string }[];
}

export interface KnowledgeApiKey {
  id: number;
  tenant_id: number;
  name: string;
  prefix: string;
  scopes: string[];
  knowledge_base_ids: number[];
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_by: number;
  created_at: string;
  api_key?: string;
}

export interface KnowledgeApiKeyList {
  items: KnowledgeApiKey[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeAuditLog {
  id: number;
  actor_user_id: number | null;
  actor_key_id: number | null;
  action: string;
  resource_type: string;
  resource_id: number | null;
  detail: Record<string, unknown> | null;
  ip_address: string | null;
  request_id: string | null;
  created_at: string;
}

export interface KnowledgeAuditLogList {
  items: KnowledgeAuditLog[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeEvalCaseList {
  items: KnowledgeEvalCase[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeEvalExperimentConfig {
  strategy?: string;
  top_k?: number;
  candidate_k?: number;
  vector_k?: number | null;
  keyword_k?: number | null;
  rrf_k?: number;
  similarity_threshold?: number | null;
  rerank?: boolean;
  evaluate_generation?: boolean;
  knowledge_base_ids?: number[] | null;
}

export interface KnowledgeEvalExperiment {
  id: number;
  dataset_id: number;
  name: string;
  description: string | null;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeEvalExperimentList {
  items: KnowledgeEvalExperiment[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeEvalRun {
  id: number;
  experiment_id: number;
  dataset_id: number;
  dataset_version: number;
  status: string;
  progress: number;
  attempt: number;
  error_message: string | null;
  config_snapshot: Record<string, unknown>;
  dataset_snapshot_meta: Record<string, unknown>;
  metrics: Record<string, unknown> | null;
  usage: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface KnowledgeEvalRunList {
  items: KnowledgeEvalRun[];
  total: number;
  page: number;
  page_size: number;
}

export interface KnowledgeEvalResult {
  id: number;
  run_id: number;
  case_id: number;
  question: string;
  expected_answer?: string | null;
  is_unanswerable: boolean;
  retrieved: Record<string, unknown>[];
  retrieval_metrics: Record<string, unknown> | null;
  answer: string | null;
  generation_metrics: Record<string, unknown> | null;
  judge_error: string | null;
  human_override: Record<string, unknown> | null;
  latency_ms: number;
  usage?: Record<string, unknown> | null;
  error_message: string | null;
}

export interface KnowledgeEvalCompare {
  runs: KnowledgeEvalRun[];
  comparable: boolean;
  incomparable_reason: string | null;
  metric_deltas: Record<string, Record<string, { base: number; value: number; delta: number; delta_pct: number | null } | null>>;
}

export interface KnowledgeUsageStats {
  query_count: number;
  search_success: number;
  search_empty: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number | null;
  strategy_counts: Record<string, number>;
  note: string;
}

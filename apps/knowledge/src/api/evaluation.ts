import type {
  ApiResponse,
  KnowledgeEvalCase,
  KnowledgeEvalCaseList,
  KnowledgeEvalProbe,
  KnowledgeEvalCompare,
  KnowledgeEvalDataset,
  KnowledgeEvalDatasetList,
  KnowledgeEvalLabelEstimate,
  KnowledgeEvalLabelSuggestion,
  KnowledgeEvalDatasetVersionDetail,
  KnowledgeEvalDatasetVersionDiff,
  KnowledgeEvalDatasetVersionList,
  KnowledgeEvalFreezeResult,
  KnowledgeEvalExperiment,
  KnowledgeEvalExperimentConfig,
  KnowledgeEvalExperimentList,
  KnowledgeEvalResult,
  KnowledgeEvalRun,
  KnowledgeEvalRunList,
  KnowledgeUsageStats,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchEvalDatasets(
  params: { q?: string; page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalDatasetList>>('/api/v1/evaluation/datasets', {
      params: { q: params.q || undefined, page: params.page, page_size: params.pageSize },
      signal,
    }),
  );
}

export function fetchEvalDataset(id: number, signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<KnowledgeEvalDataset>>(`/api/v1/evaluation/datasets/${id}`, { signal }));
}

export function createEvalDataset(payload: { name: string; description?: string; knowledge_base_ids?: number[] }) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalDataset>>('/api/v1/evaluation/datasets', payload));
}

export function updateEvalDataset(
  id: number,
  payload: { name?: string; description?: string | null; knowledge_base_ids?: number[] },
) {
  return unwrapApi(apiClient.patch<ApiResponse<KnowledgeEvalDataset>>(`/api/v1/evaluation/datasets/${id}`, payload));
}

export function deleteEvalDataset(id: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/evaluation/datasets/${id}`));
}

export function copyEvalDataset(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalDataset>>(`/api/v1/evaluation/datasets/${id}/copy`));
}

export function freezeEvalDataset(id: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeEvalFreezeResult>>(`/api/v1/evaluation/datasets/${id}/freeze`),
  );
}

export function fetchEvalVersions(
  datasetId: number,
  params: { page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalDatasetVersionList>>(`/api/v1/evaluation/datasets/${datasetId}/versions`, {
      params: { page: params.page, page_size: params.pageSize },
      signal,
    }),
  );
}

export function fetchEvalVersion(
  datasetId: number,
  version: number,
  params: { q?: string; page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalDatasetVersionDetail>>(
      `/api/v1/evaluation/datasets/${datasetId}/versions/${version}`,
      {
        params: { q: params.q || undefined, page: params.page, page_size: params.pageSize },
        signal,
      },
    ),
  );
}

export function compareEvalVersions(
  datasetId: number,
  params: { left: number; right: number; page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalDatasetVersionDiff>>(
      `/api/v1/evaluation/datasets/${datasetId}/versions/compare`,
      {
        params: {
          left: params.left,
          right: params.right,
          page: params.page,
          page_size: params.pageSize,
        },
        signal,
      },
    ),
  );
}

export function deleteEvalVersion(datasetId: number, version: number) {
  return unwrapApi(
    apiClient.delete<ApiResponse<null>>(`/api/v1/evaluation/datasets/${datasetId}/versions/${version}`),
  );
}

export function refreshEvalStale(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalDataset>>(`/api/v1/evaluation/datasets/${id}/refresh-stale`));
}

export function fetchEvalCases(
  datasetId: number,
  params: { status?: string; q?: string; page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalCaseList>>(`/api/v1/evaluation/datasets/${datasetId}/cases`, {
      params: {
        status: params.status || undefined,
        q: params.q || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function createEvalCase(
  datasetId: number,
  payload: {
    question: string;
    expected_answer?: string;
    question_type?: string;
    difficulty?: number;
    tags?: string[];
    is_unanswerable?: boolean;
  },
) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeEvalCase>>(`/api/v1/evaluation/datasets/${datasetId}/cases`, payload),
  );
}

export function updateEvalCase(
  caseId: number,
  payload: {
    question?: string;
    expected_answer?: string | null;
    question_type?: string;
    difficulty?: number;
    tags?: string[];
    is_unanswerable?: boolean;
    needs_human_review?: boolean;
  },
) {
  return unwrapApi(apiClient.patch<ApiResponse<KnowledgeEvalCase>>(`/api/v1/evaluation/cases/${caseId}`, payload));
}

export function deleteEvalCase(caseId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/evaluation/cases/${caseId}`));
}

export function replaceEvalJudgments(caseId: number, items: { chunk_id: number; relevance: number }[]) {
  return unwrapApi(apiClient.put<ApiResponse<KnowledgeEvalCase>>(`/api/v1/evaluation/cases/${caseId}/judgments`, items));
}

export function probeEvalCase(
  caseId: number,
  payload: { strategy: string; top_k: number; rerank: boolean; generate: boolean },
) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalProbe>>(`/api/v1/evaluation/cases/${caseId}/probe`, payload));
}

export function importEvalCases(datasetId: number, file: File) {
  const form = new FormData();
  form.append('file', file);
  return unwrapApi(
    apiClient.post<ApiResponse<{ succeeded: number; failed: number; errors: { row: number; message: string }[] }>>(
      `/api/v1/evaluation/datasets/${datasetId}/import`,
      form,
      { timeout: 60000 },
    ),
  );
}

export async function exportEvalCases(datasetId: number, filename: string) {
  const response = await apiClient.get(`/api/v1/evaluation/datasets/${datasetId}/export`, {
    responseType: 'blob',
    timeout: 30000,
  });
  const url = URL.createObjectURL(response.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function importEvalFromChat(datasetId: number, payload: { conversation_id: number; confirm: boolean }) {
  return unwrapApi(
    apiClient.post<ApiResponse<{ candidates: { question: string }[]; confirmed: boolean }>>(
      `/api/v1/evaluation/datasets/${datasetId}/from-chat`,
      payload,
    ),
  );
}

export function fetchEvalExperiments(
  params: {
    datasetId?: number;
    strategy?: string;
    sortBy?: string;
    sortOrder?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalExperimentList>>('/api/v1/evaluation/experiments', {
      params: {
        dataset_id: params.datasetId,
        strategy: params.strategy || undefined,
        sort_by: params.sortBy,
        sort_order: params.sortOrder,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function createEvalExperiment(payload: {
  dataset_id: number;
  name: string;
  description?: string;
  config?: KnowledgeEvalExperimentConfig;
}) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalExperiment>>('/api/v1/evaluation/experiments', payload));
}

export function copyEvalExperiment(id: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalExperiment>>(`/api/v1/evaluation/experiments/${id}/copy`));
}

export function deleteEvalExperiment(id: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/evaluation/experiments/${id}`));
}

export function startEvalRun(experimentId: number) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeEvalRun>>(`/api/v1/evaluation/experiments/${experimentId}/run`),
  );
}

export function fetchEvalRuns(
  params: {
    experimentId?: number;
    status?: string;
    strategy?: string;
    sortBy?: string;
    sortOrder?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalRunList>>('/api/v1/evaluation/runs', {
      params: {
        experiment_id: params.experimentId,
        status: params.status || undefined,
        strategy: params.strategy || undefined,
        sort_by: params.sortBy,
        sort_order: params.sortOrder,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchEvalRun(runId: number, signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<KnowledgeEvalRun>>(`/api/v1/evaluation/runs/${runId}`, { signal }));
}

export function fetchEvalResults(runId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalResult[]>>(`/api/v1/evaluation/runs/${runId}/results`, { signal }),
  );
}

export function cancelEvalRun(runId: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalRun>>(`/api/v1/evaluation/runs/${runId}/cancel`));
}

export function pauseEvalRun(runId: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalRun>>(`/api/v1/evaluation/runs/${runId}/pause`));
}

export function resumeEvalRun(
  runId: number,
  payload?: { token_budget?: number | null; cost_budget_usd?: number | null },
) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeEvalRun>>(`/api/v1/evaluation/runs/${runId}/resume`, payload ?? {}),
  );
}

export function retryEvalRun(runId: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalRun>>(`/api/v1/evaluation/runs/${runId}/retry`));
}

export function retryFailedEvalRun(runId: number) {
  return unwrapApi(apiClient.post<ApiResponse<KnowledgeEvalRun>>(`/api/v1/evaluation/runs/${runId}/retry-failed`));
}

export function overrideEvalResult(
  resultId: number,
  payload: { faithfulness?: number; answer_relevancy?: number; answer_correctness?: number; note?: string },
) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeEvalResult>>(`/api/v1/evaluation/results/${resultId}/human`, payload),
  );
}

export interface KnowledgeEvalCaseDiagnosis {
  comparable: boolean;
  incomparable_reason: string | null;
  baseline_usage: Record<string, unknown>;
  candidate_usage: Record<string, unknown>;
  summary: Record<string, number>;
  groups: Record<string, unknown>;
  recall_bootstrap: Record<string, unknown>;
  cases: Array<Record<string, unknown>>;
  note: string;
}

export function diagnoseEvalRuns(baselineId: number, candidateId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalCaseDiagnosis>>('/api/v1/evaluation/compare/cases', {
      params: { baseline_id: baselineId, candidate_id: candidateId },
      signal,
    }),
  );
}

export function compareEvalRuns(runIds: number[], signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalCompare>>('/api/v1/evaluation/compare', {
      params: { run_ids: runIds.join(',') },
      signal,
    }),
  );
}

export interface KnowledgeEvalLabelJob {
  id: number;
  task_id?: number;
  dataset_id: number;
  job_type?: 'SUGGEST' | 'CONFIRM' | string;
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | string;
  accepted: boolean;
  already_running: boolean;
  executed: boolean;
  total: number;
  processed?: number;
  succeeded?: number;
  drafted: number;
  failed: number;
  skipped: number;
  pending_cases: number;
  details?: { skips?: { suggestion_id: number; reason: string }[]; failures?: { suggestion_id: number; reason: string }[] };
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  confirmed?: number;
  errors?: { suggestion_id: number; message: string }[];
  pending_drafts?: number;
  high_drafts?: number;
}

export function isLiveEvalLabelJob(status?: string | null) {
  return status === 'QUEUED' || status === 'RUNNING';
}

export function fetchEvalLabelJob(datasetId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalLabelJob | null>>(
      `/api/v1/evaluation/datasets/${datasetId}/label-jobs/current`,
      { signal },
    ),
  );
}

export function estimateEvalLabels(datasetId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalLabelEstimate>>(
      `/api/v1/evaluation/datasets/${datasetId}/label-suggestions/estimate`,
      { signal },
    ),
  );
}

export function fetchEvalLabelSuggestions(
  datasetId: number,
  params: { confidence?: string; status?: string },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalLabelSuggestion[]>>(
      `/api/v1/evaluation/datasets/${datasetId}/label-suggestions`,
      { params: { confidence: params.confidence || undefined, status: params.status || undefined }, signal },
    ),
  );
}

export function runEvalLabelSuggestions(
  datasetId: number,
  payload: { execute: boolean; rerun?: boolean; only_failed?: boolean; only_rejected?: boolean; only_empty?: boolean },
) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeEvalLabelEstimate & Partial<KnowledgeEvalLabelJob>>>(
      `/api/v1/evaluation/datasets/${datasetId}/label-suggestions`,
      payload,
    ),
  );
}

export function confirmEvalLabelSuggestions(datasetId: number, payload: { suggestion_ids?: number[]; only_high?: boolean }) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeEvalLabelJob & { confirmed?: number; errors?: { suggestion_id: number; message: string }[] }>>(
      `/api/v1/evaluation/datasets/${datasetId}/label-suggestions/confirm`,
      payload,
    ),
  );
}

export function updateEvalLabelSuggestion(
  suggestionId: number,
  payload: {
    confidence?: string;
    verdict?: string;
    rationale?: string;
    risk?: string;
    items?: { chunk_id: number; relevance: number; reason?: string; excerpt?: string }[];
  },
) {
  return unwrapApi(
    apiClient.patch<ApiResponse<KnowledgeEvalLabelSuggestion>>(
      `/api/v1/evaluation/label-suggestions/${suggestionId}`,
      payload,
    ),
  );
}

export function rejectEvalLabelSuggestion(suggestionId: number, note: string) {
  return unwrapApi(
    apiClient.post<ApiResponse<KnowledgeEvalLabelSuggestion>>(
      `/api/v1/evaluation/label-suggestions/${suggestionId}/reject`,
      { note },
    ),
  );
}

export function deleteEvalLabelSuggestion(suggestionId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/evaluation/label-suggestions/${suggestionId}`));
}

export function fetchUsageStats(days: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeUsageStats>>('/api/v1/stats/usage', { params: { days }, signal }),
  );
}
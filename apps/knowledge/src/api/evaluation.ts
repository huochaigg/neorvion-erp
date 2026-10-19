import type {
  ApiResponse,
  KnowledgeEvalCase,
  KnowledgeEvalCaseList,
  KnowledgeEvalProbe,
  KnowledgeEvalCompare,
  KnowledgeEvalDataset,
  KnowledgeEvalDatasetList,
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
  return unwrapApi(apiClient.post<ApiResponse<{ version: number; ready_count: number; stale_judgment_count: number }>>(
    `/api/v1/evaluation/datasets/${id}/freeze`,
  ));
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
    apiClient.get<ApiResponse<KnowledgeEvalExperimentList>>('/api/v1/evaluation/experiments', {
      params: {
        dataset_id: params.datasetId,
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

export function compareEvalRuns(runIds: number[], signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeEvalCompare>>('/api/v1/evaluation/compare', {
      params: { run_ids: runIds.join(',') },
      signal,
    }),
  );
}

export function fetchUsageStats(days: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<KnowledgeUsageStats>>('/api/v1/stats/usage', { params: { days }, signal }),
  );
}
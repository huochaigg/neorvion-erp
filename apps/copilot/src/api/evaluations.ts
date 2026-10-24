import { api, unwrap } from '@/api/client';

export interface EvaluationDataset {
  id: number;
  name: string;
  description?: string;
  status: string;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface EvaluationCase {
  id: number;
  dataset_id: number;
  external_key: string;
  case_type: string;
  difficulty: number;
  user_input: string;
  status: string;
}

export interface EvaluationDatasetDetail extends EvaluationDataset {
  cases: EvaluationCase[];
}

export interface EvaluationRun {
  id: number;
  dataset_version_id: number;
  mode: 'SINGLE' | 'MULTI' | 'AUTO';
  execution_kind: 'REPLAY' | 'LIVE';
  model_provider: string;
  model_name: string;
  environment_fingerprint: string;
  status: string;
  total_cases: number;
  completed_cases: number;
  failed_cases: number;
  metrics?: Record<string, unknown>;
  created_at: string;
}

export interface EvaluationCaseRun {
  id: number;
  case_key: string;
  status: string;
  task_outcome: string;
  actual_answer?: string;
  metrics: Record<string, unknown>;
  assertion_results: Array<Record<string, unknown>>;
  error_code?: number;
}

export interface EvaluationRunDetail extends EvaluationRun {
  cases: EvaluationCaseRun[];
}

export interface EvaluationDatasetVersion {
  id: number;
  dataset_id: number;
  version: number;
  case_count: number;
  ready_count: number;
  review_count: number;
}

export interface Page<T> {
  items: T[];
  total: number;
}

export const listEvaluationDatasets = (signal?: AbortSignal) =>
  unwrap(api.get('/api/v1/evaluations/datasets', { signal })).then(
    (value) => value as Page<EvaluationDataset>,
  );

export const getEvaluationDataset = (id: number, signal?: AbortSignal) =>
  unwrap(api.get(`/api/v1/evaluations/datasets/${id}`, { signal })).then(
    (value) => value as EvaluationDatasetDetail,
  );

export const createEvaluationDataset = (payload: { name: string; description?: string }) =>
  unwrap(api.post('/api/v1/evaluations/datasets', payload)).then(
    (value) => value as EvaluationDataset,
  );

export const createEvaluationCase = (
  datasetId: number,
  payload: {
    external_key: string;
    case_type: string;
    user_input: string;
    status: 'READY' | 'NEEDS_REVIEW' | 'DISABLED';
  },
) =>
  unwrap(
    api.post(`/api/v1/evaluations/datasets/${datasetId}/cases`, {
      ...payload,
      difficulty: 2,
      expected_behavior: {},
      expected_tools: { required: [], optional: [], forbidden: ['execute_action'] },
      expected_arguments: [],
      expected_evidence: {},
      expected_answer_assertions: [],
      forbidden_actions: ['ERP_WRITE'],
      required_permissions: ['copilot:use'],
      scenario_config: {},
    }),
  );

export const importV8EvaluationCases = (datasetId: number) =>
  unwrap(api.post(`/api/v1/evaluations/datasets/${datasetId}/cases/import-v8`));

export const importV9EvaluationCases = (datasetId: number) =>
  unwrap(api.post(`/api/v1/evaluations/datasets/${datasetId}/cases/import-v9`));

export const freezeEvaluationDataset = (id: number) =>
  unwrap(api.post(`/api/v1/evaluations/datasets/${id}/freeze`));

export const listEvaluationVersions = (id: number, signal?: AbortSignal) =>
  unwrap(api.get(`/api/v1/evaluations/datasets/${id}/versions`, { signal })).then(
    (value) => value as EvaluationDatasetVersion[],
  );

export const listEvaluationRuns = (signal?: AbortSignal) =>
  unwrap(api.get('/api/v1/evaluations/runs', { signal })).then(
    (value) => value as Page<EvaluationRun>,
  );

export const createEvaluationRun = (payload: {
  dataset_version_id: number;
  mode: 'SINGLE' | 'MULTI' | 'AUTO';
  execution_kind: 'REPLAY' | 'LIVE';
  idempotency_key: string;
}) =>
  unwrap(api.post('/api/v1/evaluations/runs', payload)).then(
    (value) => value as EvaluationRun,
  );

export const getEvaluationRun = (id: number, signal?: AbortSignal) =>
  unwrap(api.get(`/api/v1/evaluations/runs/${id}`, { signal })).then(
    (value) => value as EvaluationRunDetail,
  );

export const pauseEvaluationRun = (id: number) =>
  unwrap(api.post(`/api/v1/evaluations/runs/${id}/pause`));
export const resumeEvaluationRun = (id: number) =>
  unwrap(api.post(`/api/v1/evaluations/runs/${id}/resume`));
export const cancelEvaluationRun = (id: number) =>
  unwrap(api.post(`/api/v1/evaluations/runs/${id}/cancel`));

export const createEvaluationComparison = (baselineRunId: number, candidateRunId: number) =>
  unwrap(
    api.post('/api/v1/evaluations/comparisons', {
      baseline_run_id: baselineRunId,
      candidate_run_id: candidateRunId,
    }),
  );

export interface EvaluationComparison {
  id: number;
  comparable: boolean;
  incomparable_reason?: string;
  report: Record<string, unknown>;
}

export const getAgentTrace = (id: number, signal?: AbortSignal) =>
  unwrap(api.get(`/api/v1/agent-runs/${id}/trace`, { signal }));

import { describe, expect, it } from 'vitest';
import {
  comparabilityWarning,
  evalRunMetrics,
  evalRunProgressText,
  formatEvalCount,
  formatEvalMetric,
  formatLatencyMs,
  formatRunDuration,
  latestRunStatus,
  metricMissingReason,
  parseCompareRunIds,
} from './evalMetrics';
import type { KnowledgeEvalExperiment, KnowledgeEvalRun } from '@neorvion/shared';

describe('formatEvalMetric', () => {
  it('keeps missing values as dash instead of zero', () => {
    expect(formatEvalMetric(null)).toBe('-');
    expect(formatEvalMetric(undefined)).toBe('-');
    expect(formatEvalMetric(Number.NaN)).toBe('-');
  });

  it('renders a real zero', () => {
    expect(formatEvalMetric(0)).toBe('0.000');
  });
});

describe('formatLatencyMs', () => {
  it('does not invent a p95', () => {
    expect(formatLatencyMs(null)).toBe('-');
    expect(formatLatencyMs(12.6)).toBe('13ms');
  });
});

describe('formatRunDuration', () => {
  it('uses started/finished timestamps', () => {
    expect(
      formatRunDuration({
        started_at: '2026-10-19T04:00:00.000Z',
        finished_at: '2026-10-19T04:00:12.400Z',
        created_at: '2026-10-19T04:00:00.000Z',
      }),
    ).toBe('12.4s');
  });

  it('is dash when the run never finished', () => {
    expect(
      formatRunDuration({
        started_at: '2026-10-19T04:00:00.000Z',
        finished_at: null,
        created_at: '2026-10-19T04:00:00.000Z',
      }),
    ).toBe('-');
  });
});

describe('comparabilityWarning', () => {
  const run = {
    id: 1,
    status: 'SUCCESS',
    progress: 100,
    dataset_id: 8,
    dataset_version: 1,
    error_message: null,
    recall: 0.5,
    mrr: 0.5,
    ndcg: 0.5,
    hit_rate: 1,
    precision: 0.2,
    k: 5,
    latency_p95_ms: 40,
    supervised_count: 2,
    unanswerable_count: 0,
    case_count: 2,
    comparable: true,
    embedding_model: 'mock',
    embedding_dimensions: 8,
    started_at: null,
    finished_at: null,
    created_at: '2026-10-19T04:00:00.000Z',
  };

  function experiment(id: number, latest: typeof run | null): KnowledgeEvalExperiment {
    return {
      id,
      dataset_id: latest?.dataset_id ?? 8,
      name: `e${id}`,
      description: null,
      config: {},
      created_at: '2026-10-19T04:00:00.000Z',
      updated_at: '2026-10-19T04:00:00.000Z',
      latest_run: latest,
    };
  }

  it('is silent for matching successful runs', () => {
    expect(comparabilityWarning([experiment(1, run), experiment(2, { ...run, id: 2 })])).toBeNull();
  });

  it('warns when dataset versions differ', () => {
    const message = comparabilityWarning([
      experiment(1, run),
      experiment(2, { ...run, id: 2, dataset_version: 2 }),
    ]);
    expect(message).toContain('数据集冻结版本不同');
  });

  it('ignores experiments that have not succeeded', () => {
    expect(latestRunStatus(null)).toBe('NEVER_RUN');
    expect(comparabilityWarning([experiment(1, null), experiment(2, run)])).toBeNull();
  });
});

describe('metricMissingReason', () => {
  it('does not treat a missing run as a zero score', () => {
    expect(metricMissingReason(null)).toContain('尚未运行');
    expect(formatEvalCount(null)).toBe('-');
    expect(formatEvalCount(0)).toBe('0');
  });
});

describe('parseCompareRunIds', () => {
  it('keeps 2-3 unique positive ids', () => {
    expect(parseCompareRunIds('12,12,9,abc,3,8')).toEqual([12, 9, 3]);
    expect(parseCompareRunIds(null)).toEqual([]);
  });
});

describe('evalRunMetrics', () => {
  const base: KnowledgeEvalRun = {
    id: 9,
    experiment_id: 1,
    dataset_id: 8,
    dataset_version: 2,
    status: 'SUCCESS',
    progress: 100,
    attempt: 1,
    error_message: null,
    interrupt_reason: null,
    current_case_id: null,
    current_stage: null,
    token_budget: 200000,
    cost_budget_usd: null,
    config_snapshot: { strategy: 'HYBRID', top_k: 5, rerank: false },
    dataset_snapshot_meta: {},
    metrics: { recall: 0, mrr: 0.5, ndcg: 0.4, hit_rate: 1, k: 5, supervised_count: 3 },
    usage: { latency_p95_ms: 41.2, case_count: 4, completed_count: 3, failed_count: 1, pending_count: 0 },
    started_at: '2026-10-19T04:00:00.000Z',
    finished_at: '2026-10-19T04:00:12.400Z',
    created_at: '2026-10-19T04:00:00.000Z',
  };

  it('keeps a real zero and hides metrics until success', () => {
    expect(evalRunMetrics(base).recall).toBe(0);
    expect(evalRunMetrics({ ...base, status: 'RUNNING', progress: 40, metrics: { recall: 0 } }).recall).toBeNull();
    expect(evalRunMetrics({ ...base, status: 'FAILED', metrics: null, usage: null }).latency_p95_ms).toBeNull();
  });

  it('summarizes completed failed and pending counts', () => {
    expect(evalRunProgressText(base)).toBe('已完成 3 / 4，失败 1，待执行 0');
  });
});

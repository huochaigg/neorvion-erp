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
import type { KnowledgeEvalRun } from '@neorvion/shared';

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
  const run: KnowledgeEvalRun = {
    id: 1,
    experiment_id: 4,
    dataset_id: 8,
    dataset_version: 1,
    status: 'SUCCESS',
    progress: 100,
    attempt: 1,
    error_message: null,
    config_snapshot: { embedding_model: 'mock', embedding_dimensions: 8, strategy: 'HYBRID', top_k: 5 },
    dataset_snapshot_meta: { comparable: true },
    metrics: { recall: 0.5 },
    usage: { latency_p95_ms: 40 },
    started_at: null,
    finished_at: null,
    created_at: '2026-10-19T04:00:00.000Z',
  };

  it('is silent for matching successful runs', () => {
    expect(comparabilityWarning([run, { ...run, id: 2 }])).toBeNull();
  });

  it('warns when dataset versions differ', () => {
    const message = comparabilityWarning([run, { ...run, id: 2, dataset_version: 2 }]);
    expect(message).toContain('数据集冻结版本不同');
  });

  it('ignores runs that have not succeeded', () => {
    expect(latestRunStatus(null)).toBe('NEVER_RUN');
    expect(comparabilityWarning([{ ...run, status: 'FAILED' }, run])).toBeNull();
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
    expect(evalRunMetrics(base).evidence_coverage).toBeNull();
    expect(evalRunMetrics({ ...base, status: 'RUNNING', progress: 40, metrics: { recall: 0 } }).recall).toBeNull();
    expect(evalRunMetrics({ ...base, status: 'FAILED', metrics: null, usage: null }).latency_p95_ms).toBeNull();
  });

  it('reads coverage only after success and does not invent zero for old runs', () => {
    expect(evalRunMetrics({ ...base, metrics: { ...base.metrics, evidence_coverage: 0, complete_evidence_rate: 0 } }).evidence_coverage).toBe(0);
    expect(evalRunMetrics({ ...base, metrics: { ...base.metrics, evidence_coverage: 0.5, complete_evidence_rate: 0.4 } }).complete_evidence_rate).toBe(0.4);
  });

  it('reads nested generation metrics and keeps missing citation as dash-ready null', () => {
    const withGen = {
      ...base,
      metrics: {
        ...base.metrics,
        generation: { faithfulness: 0.8, answer_correctness: 0, citation_correctness: null, refusal_accuracy: 1 },
      },
    };
    expect(evalRunMetrics(withGen).faithfulness).toBe(0.8);
    expect(evalRunMetrics(withGen).answer_correctness).toBe(0);
    expect(evalRunMetrics(withGen).citation_correctness).toBeNull();
    expect(evalRunMetrics(withGen).citation_validity).toBeNull();
    expect(evalRunMetrics(withGen).gold_citation_match).toBeNull();
    expect(evalRunMetrics(withGen).prompt_evidence_coverage).toBeNull();
    expect(evalRunMetrics(withGen).refusal_accuracy).toBe(1);
    expect(evalRunMetrics(base).faithfulness).toBeNull();
  });

  it('summarizes completed failed and pending counts', () => {
    expect(evalRunProgressText(base)).toBe('已完成 3 / 4，失败 1，待执行 0');
  });
});

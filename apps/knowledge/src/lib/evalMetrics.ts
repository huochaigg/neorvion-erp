import type { KnowledgeEvalRun } from '@neorvion/shared';

export type EvalMetricContext = {
  status: string;
  error_message?: string | null;
  k?: number | null;
  supervised_count?: number | null;
} | null | undefined;

function optionalNumber(payload: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = payload?.[key];
  return typeof value === 'number' && !Number.isNaN(value) ? value : null;
}

/** 缺失或非数字显示为「-」，真实 0 仍显示 0.000。 */
export function formatEvalMetric(value: number | null | undefined, digits = 3): string {
  if (value == null || Number.isNaN(value)) {
    return '-';
  }
  return value.toFixed(digits);
}

export function formatLatencyMs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return '-';
  }
  return `${Math.round(value)}ms`;
}

export function formatRunDuration(
  run: Pick<KnowledgeEvalRun, 'started_at' | 'finished_at' | 'created_at'> | null | undefined,
): string {
  if (!run) {
    return '-';
  }
  if (run.started_at && run.finished_at) {
    const started = Date.parse(run.started_at);
    const finished = Date.parse(run.finished_at);
    if (!Number.isNaN(started) && !Number.isNaN(finished) && finished >= started) {
      const seconds = (finished - started) / 1000;
      if (seconds < 60) {
        return `${seconds.toFixed(1)}s`;
      }
      const minutes = Math.floor(seconds / 60);
      const rest = Math.round(seconds % 60);
      return `${minutes}m ${rest}s`;
    }
  }
  return '-';
}

export function latestRunStatus(run: { status: string } | null | undefined): string {
  return run?.status ?? 'NEVER_RUN';
}

export function formatEvalCount(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return '-';
  }
  return String(value);
}

export function usageNumber(usage: Record<string, unknown> | null | undefined, key: string): number | null {
  return optionalNumber(usage, key);
}

export function evalRunCounts(run: Pick<KnowledgeEvalRun, 'usage'> | null | undefined): {
  completed: number | null;
  failed: number | null;
  pending: number | null;
  total: number | null;
} {
  const usage = run?.usage ?? null;
  return {
    completed: usageNumber(usage, 'completed_count'),
    failed: usageNumber(usage, 'failed_count'),
    pending: usageNumber(usage, 'pending_count'),
    total: usageNumber(usage, 'case_count'),
  };
}

export function evalRunProgressText(run: Pick<KnowledgeEvalRun, 'usage'> | null | undefined): string | null {
  const counts = evalRunCounts(run);
  if (counts.total == null || counts.completed == null) {
    return null;
  }
  return `已完成 ${counts.completed} / ${counts.total}，失败 ${counts.failed ?? 0}，待执行 ${counts.pending ?? 0}`;
}

export function metricMissingReason(run: EvalMetricContext): string {
  if (!run) {
    return '尚未运行，没有评测结果。';
  }
  if (run.status === 'QUEUED' || run.status === 'RUNNING') {
    return '评测尚未完成，暂不展示指标。';
  }
  if (run.status === 'FAILED') {
    return run.error_message ? `评测失败：${run.error_message}` : '评测失败，没有有效指标。';
  }
  if (run.status === 'CANCELLED') {
    return '评测已取消，没有完整指标。';
  }
  if (run.supervised_count === 0) {
    return '没有有效监督题参与统计。';
  }
  return '本次运行未写入该指标。';
}

export function parseCompareRunIds(raw: string | null | undefined): number[] {
  if (!raw) {
    return [];
  }
  const seen = new Set<number>();
  const ids: number[] = [];
  for (const part of raw.split(',')) {
    const value = Number(part.trim());
    if (!Number.isInteger(value) || value <= 0 || seen.has(value)) {
      continue;
    }
    seen.add(value);
    ids.push(value);
    if (ids.length >= 3) {
      break;
    }
  }
  return ids;
}

function snapshotValue(run: KnowledgeEvalRun, key: string): unknown {
  return run.config_snapshot?.[key];
}

export function comparabilityWarning(runs: KnowledgeEvalRun[]): string | null {
  const ready = runs.filter((run) => run.status === 'SUCCESS');
  if (ready.length < 2) {
    return null;
  }
  const baseline = ready[0];
  const reasons: string[] = [];
  if (ready.some((run) => run.dataset_id !== baseline.dataset_id)) {
    reasons.push('所选运行使用了不同数据集');
  }
  if (ready.some((run) => run.dataset_version !== baseline.dataset_version)) {
    reasons.push('数据集冻结版本不同');
  }
  if (
    ready.some(
      (run) =>
        snapshotValue(run, 'embedding_model') !== snapshotValue(baseline, 'embedding_model') ||
        snapshotValue(run, 'embedding_dimensions') !== snapshotValue(baseline, 'embedding_dimensions'),
    )
  ) {
    reasons.push('Embedding / 索引版本不同');
  }
  if (ready.some((run) => run.dataset_snapshot_meta?.comparable === false)) {
    reasons.push('部分运行含失效标注');
  }
  if (reasons.length === 0) {
    return null;
  }
  return `${reasons.join('；')}，指标不能直接解读为检索提升。`;
}

/** 只从本次 Run 的 snapshot / metrics / usage 取值，不用实验当前配置。 */
export function evalRunMetrics(run: KnowledgeEvalRun) {
  const success = run.status === 'SUCCESS';
  const snapshot = run.config_snapshot ?? {};
  const metrics = run.metrics;
  const usage = run.usage;
  return {
    status: run.status,
    progress: run.progress,
    error_message: run.error_message,
    recall: success ? optionalNumber(metrics, 'recall') : null,
    mrr: success ? optionalNumber(metrics, 'mrr') : null,
    ndcg: success ? optionalNumber(metrics, 'ndcg') : null,
    hit_rate: success ? optionalNumber(metrics, 'hit_rate') : null,
    k: success ? optionalNumber(metrics, 'k') ?? optionalNumber(snapshot, 'top_k') : null,
    latency_p95_ms: success ? optionalNumber(usage, 'latency_p95_ms') : null,
    supervised_count: success ? optionalNumber(metrics, 'supervised_count') : null,
    unanswerable_count: success ? optionalNumber(metrics, 'unanswerable_count') : null,
    case_count: success ? optionalNumber(usage, 'case_count') : null,
  };
}

export const EVAL_METRIC_HELP = {
  recall: 'Recall@K：相关切片被召回到最终 Top-K 的比例。K 为该次运行快照里的最终 Top-K。无有效监督题时显示为「-」。',
  mrr: 'MRR：第一个相关结果排名的倒数，未命中为 0。只对有相关标注的题目宏平均。',
  ndcg: 'nDCG@K：考虑相关性等级（0–3）与排名折损。K 为该次运行快照里的最终 Top-K。',
  hit_rate: 'Hit@K：Top-K 是否至少命中一个相关切片。宏平均后介于 0–1。',
  p95: 'P95 延迟：本次运行全部题目耗时的 95 分位，含检索；未成功完成时为「-」。',
  supervised: '有效题目数：参与 Recall/MRR/nDCG/Hit 宏平均的监督题。无答案题不计入。',
};

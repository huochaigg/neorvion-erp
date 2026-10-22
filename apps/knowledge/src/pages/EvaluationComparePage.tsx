import {
  knowledgeEvalCompareQueryKey,
  knowledgeEvalRunsQueryKey,
  knowledgeRetrievalStrategyLabel,
  knowledgeRunStatusColor,
  knowledgeRunStatusLabel,
  type KnowledgeEvalRun,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Select, Space, Table, Tag } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { parseCompareRunIds } from '@/lib/evalMetrics';
import { compareEvalRuns, diagnoseEvalRuns, fetchEvalResults, fetchEvalRuns } from '@/api/evaluation';
import { GroupedMetricBars } from '@/components/MetricBars';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';

const METRIC_KEYS = ['hit_rate', 'recall', 'precision', 'mrr', 'ndcg'] as const;
const METRIC_LABEL: Record<string, string> = {
  hit_rate: 'Hit Rate',
  recall: 'Recall',
  precision: 'Precision',
  mrr: 'MRR',
  ndcg: 'nDCG',
};
const COLORS = ['#0ea5e9', '#8b5cf6', '#f59e0b', '#10b981'];

function scoreText(value: unknown): string {
  return typeof value === 'number' ? value.toFixed(3) : '无';
}

function rankText(value: unknown, hasGold: boolean): string {
  if (!hasGold) return '无相关标注';
  return typeof value === 'number' ? String(value) : '未进 Top-K';
}

function metricOf(run: KnowledgeEvalRun, key: string): number | null {
  const value = run.metrics?.[key];
  return typeof value === 'number' ? value : null;
}

export function EvaluationComparePage() {
  const navigate = useNavigate();
  const { tenantId } = usePermissions();
  const [searchParams, setSearchParams] = useSearchParams();
  const selected = parseCompareRunIds(searchParams.get('run_ids'));
  const [lowRunId, setLowRunId] = useState<number | null>(null);

  const setSelected = (ids: number[]) => {
    const next = parseCompareRunIds(ids.join(','));
    if (next.length) {
      setSearchParams({ run_ids: next.join(',') }, { replace: true });
      return;
    }
    const params = new URLSearchParams(searchParams);
    params.delete('run_ids');
    setSearchParams(params, { replace: true });
  };

  useEffect(() => {
    setLowRunId(null);
  }, [tenantId]);

  const runsQuery = useQuery({
    queryKey: knowledgeEvalRunsQueryKey(tenantId, { page: 1, pageSize: 50 }),
    queryFn: ({ signal }) => fetchEvalRuns({ page: 1, pageSize: 50 }, signal),
    enabled: tenantId != null,
  });

  const runIds = selected.join(',');
  const compareQuery = useQuery({
    queryKey: knowledgeEvalCompareQueryKey(tenantId, runIds),
    queryFn: ({ signal }) => compareEvalRuns(selected, signal),
    enabled: tenantId != null && selected.length >= 2,
  });

  const lowQuery = useQuery({
    queryKey: ['tenant', tenantId, 'knowledge-eval-results', lowRunId, 'lows'],
    queryFn: ({ signal }) => fetchEvalResults(lowRunId!, signal),
    enabled: tenantId != null && lowRunId != null,
  });

  const diagnosisQuery = useQuery({
    queryKey: ['tenant', tenantId, 'knowledge-eval-diagnosis', selected[0] ?? null, selected[1] ?? null],
    queryFn: ({ signal }) => diagnoseEvalRuns(selected[0], selected[1], signal),
    enabled: tenantId != null && selected.length >= 2,
  });

  const runs = compareQuery.data?.runs ?? [];
  const series = useMemo(
    () =>
      runs.map((run, index) => ({
        name: `#${run.id}`,
        color: COLORS[index % COLORS.length],
        values: METRIC_KEYS.map((key) => ({ label: METRIC_LABEL[key], value: metricOf(run, key) })),
      })),
    [runs],
  );

  const lowCases = (lowQuery.data ?? [])
    .filter((item) => !item.is_unanswerable)
    .map((item) => ({
      ...item,
      recall: typeof item.retrieval_metrics?.recall === 'number' ? item.retrieval_metrics.recall : 1,
    }))
    .sort((a, b) => a.recall - b.recall)
    .slice(0, 8);

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <PageHeader
        title="实验对比"
        description="对比多次运行的检索指标与参数快照。数据集版本或 Embedding/索引不同时标记为非严格可比，不会给出误导性提升结论。"
        extra={<Button onClick={() => navigate('/experiments')}>返回评测</Button>}
      />
      <Space wrap className="mb-4">
        <Select
          mode="multiple"
          maxCount={3}
          placeholder="选择至少两次成功运行"
          style={{ minWidth: 360 }}
          value={selected}
          onChange={setSelected}
          options={(() => {
            const byId = new Map<number, KnowledgeEvalRun>();
            for (const item of runsQuery.data?.items ?? []) {
              if (item.status === 'SUCCESS') {
                byId.set(item.id, item);
              }
            }
            for (const item of runs) {
              byId.set(item.id, item);
            }
            return [...byId.values()].map((item) => ({
              value: item.id,
              label: `#${item.id} ${knowledgeRetrievalStrategyLabel(String(item.config_snapshot.strategy ?? ''))} v${item.dataset_version}`,
            }));
          })()}
        />
      </Space>
      {compareQuery.data && !compareQuery.data.comparable ? (
        <Alert className="mb-3" type="warning" showIcon message={compareQuery.data.incomparable_reason || '指标非严格可比'} />
      ) : null}
      {runs.length >= 2 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card size="small" title="指标对比">
            <GroupedMetricBars series={series} />
          </Card>
          <Card size="small" title="相对变化（相对第一列）">
            <Table
              size="small"
              pagination={false}
              rowKey="key"
              dataSource={METRIC_KEYS.map((key) => {
                const row: Record<string, string> = { key, metric: METRIC_LABEL[key] };
                const deltas = compareQuery.data?.metric_deltas ?? {};
                for (const run of runs.slice(1)) {
                  const item = deltas[String(run.id)]?.[key];
                  row[`run_${run.id}`] =
                    item == null
                      ? '-'
                      : `${item.value.toFixed(3)} (${item.delta >= 0 ? '+' : ''}${item.delta.toFixed(3)} / ${item.delta_pct == null ? '-' : `${item.delta_pct.toFixed(1)}%`})`;
                }
                return row;
              })}
              columns={[
                { title: '指标', dataIndex: 'metric', width: 100 },
                ...runs.slice(1).map((run) => ({ title: `#${run.id}`, dataIndex: `run_${run.id}` })),
              ]}
            />
          </Card>
          <Card size="small" title="同题诊断" className="lg:col-span-2">
            {diagnosisQuery.data ? (
              <div className="space-y-2 text-sm">
                {!diagnosisQuery.data.comparable ? (
                  <Alert type="warning" showIcon message={diagnosisQuery.data.incomparable_reason || '不能直接比较'} />
                ) : null}
                <div>
                  对齐 {diagnosisQuery.data.summary.matched ?? 0} 题，缺失 {diagnosisQuery.data.summary.missing ?? 0}。
                  Recall 改善 {diagnosisQuery.data.summary.recall_improved ?? 0}，退化 {diagnosisQuery.data.summary.recall_regressed ?? 0}，不变 {diagnosisQuery.data.summary.recall_unchanged ?? 0}。
                  排序改善 {diagnosisQuery.data.summary.rank_improved ?? 0}，退化 {diagnosisQuery.data.summary.rank_regressed ?? 0}。
                </div>
                <div className="text-xs text-slate-500">{diagnosisQuery.data.note}</div>
                <div className="text-xs text-slate-500">
                  下表只对比所选的前两次运行。有相关标注但显示「未进 Top-K」时，该相关 Chunk 没有出现在本次结果里。
                </div>
                <Table
                  size="small"
                  pagination={false}
                  rowKey="case_id"
                  scroll={{ x: 1100 }}
                  dataSource={diagnosisQuery.data.cases ?? []}
                  columns={[
                    { title: '问题', dataIndex: 'question', ellipsis: true, width: 220 },
                    {
                      title: 'Ground Truth',
                      width: 140,
                      render: (_, record) => ((record.gold_chunk_ids as number[] | undefined) ?? []).map((id) => `#${id}`).join('、') || '无相关标注',
                    },
                    {
                      title: `#${selected[0]} Top-K`,
                      width: 140,
                      render: (_, record) => ((record.baseline_chunk_ids as number[] | undefined) ?? []).map((id) => `#${id}`).join('、') || '无',
                    },
                    {
                      title: `#${selected[1]} Top-K`,
                      width: 140,
                      render: (_, record) => ((record.candidate_chunk_ids as number[] | undefined) ?? []).map((id) => `#${id}`).join('、') || '无',
                    },
                    {
                      title: '相关名次',
                      width: 110,
                      render: (_, record) => {
                        const hasGold = ((record.gold_chunk_ids as number[] | undefined) ?? []).length > 0;
                        return `${rankText(record.baseline_best_rank, hasGold)} → ${rankText(record.candidate_best_rank, hasGold)}`;
                      },
                    },
                    {
                      title: 'Hit',
                      width: 110,
                      render: (_, record) => `${scoreText(record.hit_before)} → ${scoreText(record.hit_after)}`,
                    },
                    {
                      title: 'Recall',
                      width: 110,
                      render: (_, record) => `${scoreText(record.recall_before)} → ${scoreText(record.recall_after)}`,
                    },
                    {
                      title: 'MRR',
                      width: 110,
                      render: (_, record) => `${scoreText(record.mrr_before)} → ${scoreText(record.mrr_after)}`,
                    },
                    {
                      title: 'nDCG',
                      width: 110,
                      render: (_, record) => `${scoreText(record.ndcg_before)} → ${scoreText(record.ndcg_after)}`,
                    },
                    {
                      title: 'Rerank',
                      width: 140,
                      render: (_, record) => `${record.baseline_rerank || '无'} → ${record.candidate_rerank || '无'}`,
                    },
                    {
                      title: '检索耗时',
                      width: 120,
                      render: (_, record) => `${record.baseline_latency_ms ?? '无'} → ${record.candidate_latency_ms ?? '无'} ms`,
                    },
                  ]}
                />
                <div className="text-xs text-slate-500">
                  {diagnosisQuery.data.recall_bootstrap.available
                    ? `Recall 差值均值 ${Number(diagnosisQuery.data.recall_bootstrap.mean).toFixed(3)}，重抽样区间 ${Number(diagnosisQuery.data.recall_bootstrap.low).toFixed(3)} ~ ${Number(diagnosisQuery.data.recall_bootstrap.high).toFixed(3)}。${String(diagnosisQuery.data.recall_bootstrap.note ?? '')}`
                    : String(diagnosisQuery.data.recall_bootstrap.reason ?? '样本不足，不估计置信区间')}
                </div>
              </div>
            ) : (
              <div className="text-sm text-slate-500">选择两次运行后按题目对齐。不会重新调用模型。</div>
            )}
          </Card>
          <Card size="small" title="参数差异" className="lg:col-span-2">
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              dataSource={runs}
              columns={[
                { title: 'Run', dataIndex: 'id', width: 70 },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 90,
                  render: (value: string) => (
                    <Tag color={knowledgeRunStatusColor(value)}>{knowledgeRunStatusLabel(value)}</Tag>
                  ),
                },
                { title: '数据集版本', dataIndex: 'dataset_version', width: 100 },
                {
                  title: '策略',
                  render: (_, record) => knowledgeRetrievalStrategyLabel(String(record.config_snapshot.strategy ?? '')),
                },
                { title: 'Top-K', render: (_, record) => String(record.config_snapshot.top_k ?? '-') },
                { title: 'Rerank', render: (_, record) => (record.config_snapshot.rerank ? '开' : '关') },
                { title: 'Embedding', render: (_, record) => String(record.config_snapshot.embedding_model ?? '-') },
                { title: 'Chat', render: (_, record) => String(record.config_snapshot.chat_model ?? '-') },
                {
                  title: '生成评测',
                  render: (_, record) => (record.config_snapshot.evaluate_generation ? '是' : '否'),
                },
              ]}
            />
          </Card>
          <Card
            size="small"
            title="低分问题"
            extra={
              <Select
                placeholder="选择运行"
                style={{ width: 160 }}
                value={lowRunId}
                onChange={setLowRunId}
                options={runs.map((item) => ({ value: item.id, label: `#${item.id}` }))}
              />
            }
            className="lg:col-span-2"
          >
            {(lowCases.length === 0 && lowRunId) || !lowRunId ? (
              <div className="text-sm text-slate-500">{lowRunId ? '暂无低分问题' : '选择一次运行查看失败案例'}</div>
            ) : (
              <Table
                size="small"
                pagination={false}
                rowKey="id"
                dataSource={lowCases}
                columns={[
                  { title: '问题', dataIndex: 'question', ellipsis: true },
                  { title: 'Recall', dataIndex: 'recall', width: 90, render: (value: number) => value.toFixed(3) },
                  { title: '错误', dataIndex: 'error_message', ellipsis: true, render: (value: string | null, record) => value || record.judge_error || '-' },
                  {
                    title: '召回',
                    render: (_, record) => `${record.retrieved.length} 条`,
                    width: 80,
                  },
                ]}
              />
            )}
          </Card>
        </div>
      ) : (
        <Card size="small">选择至少两个成功的实验运行后显示对比。</Card>
      )}
    </div>
  );
}

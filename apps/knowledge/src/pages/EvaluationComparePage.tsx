import {
  knowledgeEvalCompareQueryKey,
  knowledgeEvalRunsQueryKey,
  knowledgeRetrievalStrategyLabel,
  knowledgeRunStatusLabel,
  type KnowledgeEvalRun,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Select, Space, Table } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { compareEvalRuns, fetchEvalResults, fetchEvalRuns } from '@/api/evaluation';
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

function metricOf(run: KnowledgeEvalRun, key: string): number | null {
  const value = run.metrics?.[key];
  return typeof value === 'number' ? value : null;
}

export function EvaluationComparePage() {
  const navigate = useNavigate();
  const { tenantId } = usePermissions();
  const [selected, setSelected] = useState<number[]>([]);
  const [lowRunId, setLowRunId] = useState<number | null>(null);

  useEffect(() => {
    setSelected([]);
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
          placeholder="选择至少两次成功运行"
          style={{ minWidth: 360 }}
          value={selected}
          onChange={setSelected}
          options={(runsQuery.data?.items ?? [])
            .filter((item) => item.status === 'SUCCESS')
            .map((item) => ({
              value: item.id,
              label: `#${item.id} ${knowledgeRetrievalStrategyLabel(String(item.config_snapshot.strategy ?? ''))} v${item.dataset_version}`,
            }))}
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
          <Card size="small" title="参数差异" className="lg:col-span-2">
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              dataSource={runs}
              columns={[
                { title: 'Run', dataIndex: 'id', width: 70 },
                { title: '状态', dataIndex: 'status', width: 90, render: (value: string) => knowledgeRunStatusLabel(value) },
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

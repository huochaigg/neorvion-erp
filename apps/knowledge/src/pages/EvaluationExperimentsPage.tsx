import {
  DEFAULT_PAGE_SIZE,
  knowledgeEvalDatasetsQueryKey,
  knowledgeEvalExperimentsQueryKey,
  knowledgeEvalResultsQueryKey,
  knowledgeEvalRunsQueryKey,
  knowledgeRetrievalStrategyLabel,
  knowledgeRunStatusLabel,
  KNOWLEDGE_RETRIEVAL_STRATEGY,
  PERMISSION_CODE,
  type KnowledgeEvalExperiment,
  type KnowledgeEvalResult,
  type KnowledgeEvalRun,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Form, Input, InputNumber, Select, Space, Switch, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  cancelEvalRun,
  copyEvalExperiment,
  createEvalExperiment,
  fetchEvalDatasets,
  fetchEvalExperiments,
  fetchEvalResults,
  fetchEvalRuns,
  retryEvalRun,
  startEvalRun,
} from '@/api/evaluation';
import { ActionCell, AppTable, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { MetricBars } from '@/components/MetricBars';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

function metricNumber(metrics: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = metrics?.[key];
  return typeof value === 'number' ? value : null;
}

export function EvaluationExperimentsPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [datasetId, setDatasetId] = useState<number | undefined>();
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [activeRun, setActiveRun] = useState<KnowledgeEvalRun | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    setDatasetId(undefined);
    setPage(1);
    setActiveRun(null);
  }, [tenantId]);

  const datasetsQuery = useQuery({
    queryKey: knowledgeEvalDatasetsQueryKey(tenantId, { page: 1, pageSize: 100 }),
    queryFn: ({ signal }) => fetchEvalDatasets({ page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });

  const listQuery = useQuery({
    queryKey: knowledgeEvalExperimentsQueryKey(tenantId, { datasetId, page, pageSize: DEFAULT_PAGE_SIZE }),
    queryFn: ({ signal }) => fetchEvalExperiments({ datasetId, page, pageSize: DEFAULT_PAGE_SIZE }, signal),
    enabled: tenantId != null,
  });

  const runsQuery = useQuery({
    queryKey: knowledgeEvalRunsQueryKey(tenantId, { page: 1, pageSize: 20 }),
    queryFn: ({ signal }) => fetchEvalRuns({ page: 1, pageSize: 20 }, signal),
    enabled: tenantId != null,
    refetchInterval: (current) => {
      const items = current.state.data?.items ?? [];
      return items.some((item) => item.status === 'QUEUED' || item.status === 'RUNNING') ? 2000 : false;
    },
  });

  const resultsQuery = useQuery({
    queryKey: knowledgeEvalResultsQueryKey(tenantId, activeRun?.id ?? null),
    queryFn: ({ signal }) => fetchEvalResults(activeRun!.id, signal),
    enabled: tenantId != null && activeRun != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-experiments'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-runs'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-results'] });
  };

  const createMutation = useMutation({
    mutationFn: createEvalExperiment,
    onSuccess: () => {
      message.success('已创建实验');
      setCreating(false);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const experimentColumns: ColumnsType<KnowledgeEvalExperiment> = [
    { title: '实验', dataIndex: 'name', ellipsis: true },
    {
      title: '策略',
      width: 110,
      render: (_, record) => knowledgeRetrievalStrategyLabel(String(record.config.strategy ?? 'HYBRID')),
    },
    { title: 'Top-K', width: 80, render: (_, record) => String(record.config.top_k ?? '-') },
    { title: 'Rerank', width: 80, render: (_, record) => (record.config.rerank ? '开' : '关') },
    { title: '生成评测', width: 90, render: (_, record) => (record.config.evaluate_generation ? '是' : '否') },
    {
      title: '操作',
      width: 220,
      render: (_, record) => (
        <ActionCell>
          <Can permission={PERMISSION_CODE.knowledgeCreate}>
            <Button
              type="link"
              size="small"
              onClick={() => {
                // 立刻刷新，便于轮询到 QUEUED/RUNNING；不要等长时间 inline 响应结束
                invalidate();
                void startEvalRun(record.id)
                  .then((run) => {
                    message.success(run.status === 'SUCCESS' ? '评测完成' : '已开始评测');
                    setActiveRun(run);
                    invalidate();
                  })
                  .catch((error: Error) => {
                    invalidate();
                    message.error(error.message);
                  });
              }}
            >
              运行
            </Button>
            <Button type="link" size="small" onClick={() => copyEvalExperiment(record.id).then(() => { message.success('已复制'); invalidate(); }).catch((error: Error) => message.error(error.message))}>
              复制
            </Button>
          </Can>
        </ActionCell>
      ),
    },
  ];

  const runColumns: ColumnsType<KnowledgeEvalRun> = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag>{knowledgeRunStatusLabel(value)}</Tag>,
    },
    { title: '进度', dataIndex: 'progress', width: 80, render: (value: number) => `${value}%` },
    { title: '版本', dataIndex: 'dataset_version', width: 70 },
    {
      title: 'Recall',
      width: 90,
      render: (_, record) => metricNumber(record.metrics, 'recall')?.toFixed(3) ?? '-',
    },
    {
      title: 'nDCG',
      width: 90,
      render: (_, record) => metricNumber(record.metrics, 'ndcg')?.toFixed(3) ?? '-',
    },
    { title: '时间', dataIndex: 'created_at', width: 170, render: (value: string) => formatDateTime(value) },
    {
      title: '操作',
      width: 200,
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => setActiveRun(record)}>
            明细
          </Button>
          {record.status === 'QUEUED' || record.status === 'RUNNING' ? (
            <Button type="link" size="small" onClick={() => cancelEvalRun(record.id).then(() => { message.success('已请求取消'); invalidate(); }).catch((error: Error) => message.error(error.message))}>
              取消
            </Button>
          ) : null}
          {record.status === 'FAILED' || record.status === 'CANCELLED' ? (
            <Button type="link" size="small" onClick={() => retryEvalRun(record.id).then((run) => { message.success('已重试'); setActiveRun(run); invalidate(); }).catch((error: Error) => message.error(error.message))}>
              重试
            </Button>
          ) : null}
        </ActionCell>
      ),
    },
  ];

  const resultColumns: ColumnsType<KnowledgeEvalResult> = [
    {
      title: '问题',
      dataIndex: 'question',
      width: 300,
      ellipsis: true,
      // AppTable 使用 scroll.x=max-content，仅设 width 会被长文本撑开；用 maxWidth + EllipsisCell 固定可视宽度
      onCell: () => ({ style: { maxWidth: 300 } }),
      render: (value: string) => <EllipsisCell value={value} />,
    },
    { title: '耗时', dataIndex: 'latency_ms', width: 80, render: (value: number) => `${value}ms` },
    {
      title: 'Recall',
      width: 90,
      render: (_, record) => metricNumber(record.retrieval_metrics, 'recall')?.toFixed(3) ?? (record.is_unanswerable ? '无答案' : '-'),
    },
    {
      title: 'Hit',
      width: 80,
      render: (_, record) => metricNumber(record.retrieval_metrics, 'hit_rate')?.toFixed(0) ?? '-',
    },
    {
      title: '错误',
      ellipsis: true,
      onCell: () => ({ style: { maxWidth: 240 } }),
      render: (_, record) => <EllipsisCell value={record.error_message || record.judge_error || '-'} />,
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader
        title="检索评测"
        description="选择数据集、配置检索参数并异步跑批。指标由代码计算，不使用 LLM 给 Recall/nDCG 打分。生成质量评测可选，以避免额外费用。"
        extra={
          <Space>
            <Button onClick={() => navigate('/experiments/compare')}>实验对比</Button>
            <Can permission={PERMISSION_CODE.knowledgeCreate}>
              <Button type="primary" onClick={() => setCreating(true)}>
                新建实验
              </Button>
            </Can>
          </Space>
        }
      />
      <ListToolbar>
        <Select
          allowClear
          placeholder="筛选数据集"
          style={{ width: 240 }}
          value={datasetId}
          onChange={(value) => {
            setDatasetId(value);
            setPage(1);
          }}
          options={(datasetsQuery.data?.items ?? []).map((item) => ({ value: item.id, label: item.name }))}
        />
      </ListToolbar>
      <div className="grid min-h-0 flex-1 grid-rows-2 gap-3 overflow-hidden">
        <ListTableArea>
          <AppTable
            rowKey="id"
            loading={listQuery.isLoading}
            columns={experimentColumns}
            dataSource={listQuery.data?.items ?? []}
            pagination={{
              current: page,
              pageSize: DEFAULT_PAGE_SIZE,
              total: listQuery.data?.total ?? 0,
              onChange: (next) => setPage(next),
            }}
          />
        </ListTableArea>
        <ListTableArea>
          <AppTable rowKey="id" loading={runsQuery.isLoading} columns={runColumns} dataSource={runsQuery.data?.items ?? []} pagination={false} />
        </ListTableArea>
      </div>
      <Drawer title="创建实验" open={creating} onClose={() => setCreating(false)} width={480}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ strategy: 'HYBRID', top_k: 8, candidate_k: 24, rrf_k: 60, rerank: false, evaluate_generation: false }}
          onFinish={(values) =>
            createMutation.mutate({
              dataset_id: values.dataset_id,
              name: values.name.trim(),
              description: values.description,
              config: {
                strategy: values.strategy,
                top_k: values.top_k,
                candidate_k: values.candidate_k,
                vector_k: values.vector_k,
                keyword_k: values.keyword_k,
                rrf_k: values.rrf_k,
                similarity_threshold: values.similarity_threshold,
                rerank: values.rerank,
                evaluate_generation: values.evaluate_generation,
              },
            })
          }
        >
          <Form.Item name="dataset_id" label="数据集" rules={[{ required: true }]}>
            <Select options={(datasetsQuery.data?.items ?? []).map((item) => ({ value: item.id, label: `${item.name}（可评测 ${item.ready_count}）` }))} />
          </Form.Item>
          <Form.Item name="name" label="实验名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="strategy" label="检索策略">
            <Select options={Object.values(KNOWLEDGE_RETRIEVAL_STRATEGY).map((value) => ({ value, label: knowledgeRetrievalStrategyLabel(value) }))} />
          </Form.Item>
          <Form.Item name="top_k" label="最终 Top-K">
            <InputNumber min={1} max={50} className="w-full" />
          </Form.Item>
          <Form.Item name="vector_k" label="Vector Top-K">
            <InputNumber min={1} max={100} className="w-full" />
          </Form.Item>
          <Form.Item name="keyword_k" label="Keyword Top-K">
            <InputNumber min={1} max={100} className="w-full" />
          </Form.Item>
          <Form.Item name="rrf_k" label="RRF k">
            <InputNumber min={1} max={200} className="w-full" />
          </Form.Item>
          <Form.Item name="rerank" label="Rerank" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="evaluate_generation" label="生成质量评测（产生模型费用）" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
            保存参数方案
          </Button>
        </Form>
      </Drawer>
      <Drawer title={`运行 #${activeRun?.id ?? ''}`} open={activeRun != null} width={720} onClose={() => setActiveRun(null)}>
        {activeRun ? (
          <div className="space-y-4">
            <Space wrap>
              <Tag>{knowledgeRunStatusLabel(activeRun.status)}</Tag>
              <Tag>数据集版本 {activeRun.dataset_version}</Tag>
              <Tag>{knowledgeRetrievalStrategyLabel(String(activeRun.config_snapshot.strategy ?? ''))}</Tag>
              {activeRun.dataset_snapshot_meta.comparable === false ? <Tag color="warning">含失效标注，非严格可比</Tag> : null}
            </Space>
            {activeRun.error_message ? <div className="text-sm text-red-500">{activeRun.error_message}</div> : null}
            <MetricBars
              items={[
                { label: 'Hit Rate', value: metricNumber(activeRun.metrics, 'hit_rate') },
                { label: 'Recall', value: metricNumber(activeRun.metrics, 'recall') },
                { label: 'Precision', value: metricNumber(activeRun.metrics, 'precision') },
                { label: 'MRR', value: metricNumber(activeRun.metrics, 'mrr') },
                { label: 'nDCG', value: metricNumber(activeRun.metrics, 'ndcg') },
              ]}
            />
            <div className="text-xs text-slate-500">粒度：Chunk。LLM Judge 具有主观性与波动，失败时不会伪造分数。</div>
            <AppTable
              rowKey="id"
              fillHeight={false}
              columns={resultColumns}
              dataSource={resultsQuery.data ?? []}
              pagination={false}
            />
            {(resultsQuery.data ?? [])
              .filter((item) => item.generation_metrics || item.judge_error || item.human_override)
              .slice(0, 8)
              .map((item) => (
                <div key={item.id} className="rounded border border-slate-200 p-2 text-xs">
                  <div className="mb-1 font-medium">{item.question}</div>
                  {item.judge_error ? <div className="text-amber-600">Judge 失败：{item.judge_error}（未伪造分数）</div> : null}
                  {item.generation_metrics ? <div>{JSON.stringify(item.generation_metrics)}</div> : null}
                  {item.human_override ? <div>人工复核：{JSON.stringify(item.human_override)}</div> : null}
                </div>
              ))}
          </div>
        ) : null}
      </Drawer>
    </ListPageContainer>
  );
}

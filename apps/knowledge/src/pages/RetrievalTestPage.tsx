import {
  knowledgeBasesQueryKey,
  knowledgeRetrievalStrategyLabel,
  KNOWLEDGE_RETRIEVAL_STRATEGY,
  type KnowledgeSearchHit,
  type KnowledgeSearchResult,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, Descriptions, Drawer, Form, Input, InputNumber, Select, Space, Switch, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { fetchKnowledgeBases } from '@/api/knowledge-bases';
import { fetchRetrievalDefaults, testRetrieval } from '@/api/rag';
import { FormLabelHelp } from '@/components/FormLabelHelp';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import {
  candidateKHelp,
  keywordTopKHelp,
  rerankHelp,
  rrfKHelp,
  similarityThresholdHelp,
  topKHelp,
  vectorTopKHelp,
} from '@/lib/retrievalHelp';

type CompareMap = Partial<Record<string, KnowledgeSearchResult>>;

export function RetrievalTestPage() {
  const { tenantId } = usePermissions();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<KnowledgeSearchResult | null>(null);
  const [compare, setCompare] = useState<CompareMap>({});
  const [rerankPair, setRerankPair] = useState<{ off: KnowledgeSearchResult; on: KnowledgeSearchResult } | null>(null);
  const [active, setActive] = useState<KnowledgeSearchHit | null>(null);

  useEffect(() => {
    setResult(null);
    setCompare({});
    setRerankPair(null);
    setError(null);
  }, [tenantId]);

  const defaultsQuery = useQuery({
    queryKey: ['tenant', tenantId, 'knowledge-retrieval-defaults'],
    queryFn: ({ signal }) => fetchRetrievalDefaults(signal),
    enabled: tenantId != null,
  });
  const defaults = defaultsQuery.data;
  const basesQuery = useQuery({
    queryKey: knowledgeBasesQueryKey(tenantId, { page: 1, pageSize: 100, status: 'ACTIVE' }),
    queryFn: ({ signal }) => fetchKnowledgeBases({ page: 1, pageSize: 100, status: 'ACTIVE' }, signal),
    enabled: tenantId != null,
  });

  const payloadFromForm = async (overrides: Record<string, unknown> = {}) => {
    const values = await form.validateFields();
    return {
      query: values.query as string,
      strategy: (overrides.strategy as string | undefined) ?? values.strategy,
      knowledge_base_ids: values.knowledge_base_ids,
      top_k: values.top_k,
      candidate_k: values.candidate_k,
      vector_k: values.vector_k,
      keyword_k: values.keyword_k,
      rrf_k: values.rrf_k,
      similarity_threshold: values.similarity_threshold,
      rerank: (overrides.rerank as boolean | undefined) ?? values.rerank,
    };
  };

  const onRun = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await testRetrieval(await payloadFromForm());
      setResult(data);
      setCompare({});
      setRerankPair(null);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : '检索失败');
    } finally {
      setLoading(false);
    }
  };

  const onCompareStrategies = async () => {
    setLoading(true);
    setError(null);
    try {
      const next: CompareMap = {};
      for (const strategy of Object.values(KNOWLEDGE_RETRIEVAL_STRATEGY)) {
        next[strategy] = await testRetrieval(await payloadFromForm({ strategy, rerank: false }));
      }
      setCompare(next);
      setResult(null);
      setRerankPair(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '对比失败');
    } finally {
      setLoading(false);
    }
  };

  const onCompareRerank = async () => {
    setLoading(true);
    setError(null);
    try {
      const off = await testRetrieval(await payloadFromForm({ rerank: false }));
      const on = await testRetrieval(await payloadFromForm({ rerank: true }));
      setRerankPair({ off, on });
      setResult(null);
      setCompare({});
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Rerank 对比失败');
    } finally {
      setLoading(false);
    }
  };

  const stages = result?.stages ?? {};
  const columns: ColumnsType<KnowledgeSearchHit> = [
    { title: '最终排名', dataIndex: 'final_rank', width: 90 },
    { title: 'Chunk', dataIndex: 'chunk_id', width: 90 },
    { title: '文档', dataIndex: 'filename', ellipsis: true },
    { title: '向量分', dataIndex: 'vector_score', width: 100, render: (value: number | null) => value?.toFixed(3) ?? '-' },
    { title: '关键词分', dataIndex: 'keyword_score', width: 100, render: (value: number | null) => value?.toFixed(3) ?? '-' },
    { title: 'RRF', dataIndex: 'rrf_score', width: 90, render: (value: number | null) => value?.toFixed(4) ?? '-' },
    { title: 'Rerank', dataIndex: 'rerank_score', width: 90, render: (value: number | null) => value?.toFixed(3) ?? '-' },
    {
      title: '内容',
      dataIndex: 'content',
      ellipsis: true,
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => setActive(record)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PageHeader title="召回调优" description="与知识问答共用同一检索引擎。可对比 VECTOR / KEYWORD / HYBRID、Rerank 前后，并查看各阶段耗时与 Chunk 排名。" />
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-hidden lg:grid-cols-[320px_1fr]">
        <Card size="small" className="overflow-y-auto" title="参数">
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              strategy: 'HYBRID',
              top_k: defaults?.default_top_k ?? 8,
              candidate_k: defaults?.default_candidate_k ?? 24,
              rrf_k: defaults?.rrf_k ?? 60,
              rerank: true,
            }}
          >
            <Form.Item name="query" label="测试问题" rules={[{ required: true, message: '请输入问题' }]}>
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item name="knowledge_base_ids" label="知识库">
              <Select
                mode="multiple"
                allowClear
                options={(basesQuery.data?.items ?? []).map((item) => ({ value: item.id, label: item.name }))}
              />
            </Form.Item>
            <Form.Item name="strategy" label="策略">
              <Select
                options={Object.values(KNOWLEDGE_RETRIEVAL_STRATEGY).map((value) => ({
                  value,
                  label: knowledgeRetrievalStrategyLabel(value),
                }))}
              />
            </Form.Item>
            <Form.Item name="top_k" label={defaults ? <FormLabelHelp label="最终 Top-K">{topKHelp(defaults)}</FormLabelHelp> : '最终 Top-K'}>
              <InputNumber min={1} max={50} className="w-full" />
            </Form.Item>
            <Form.Item name="vector_k" label={defaults ? <FormLabelHelp label="Vector Top-K">{vectorTopKHelp(defaults)}</FormLabelHelp> : 'Vector Top-K'}>
              <InputNumber min={1} max={100} className="w-full" />
            </Form.Item>
            <Form.Item name="keyword_k" label={defaults ? <FormLabelHelp label="Keyword Top-K">{keywordTopKHelp(defaults)}</FormLabelHelp> : 'Keyword Top-K'}>
              <InputNumber min={1} max={100} className="w-full" />
            </Form.Item>
            <Form.Item name="rrf_k" label={defaults ? <FormLabelHelp label="RRF k">{rrfKHelp(defaults)}</FormLabelHelp> : 'RRF k'}>
              <InputNumber min={1} max={200} className="w-full" />
            </Form.Item>
            <Form.Item name="candidate_k" label={defaults ? <FormLabelHelp label="候选召回数">{candidateKHelp(defaults)}</FormLabelHelp> : '候选召回数'}>
              <InputNumber min={1} max={100} className="w-full" />
            </Form.Item>
            <Form.Item
              name="similarity_threshold"
              label={defaults ? <FormLabelHelp label="向量相似度阈值">{similarityThresholdHelp(defaults)}</FormLabelHelp> : '向量相似度阈值'}
            >
              <InputNumber min={0} max={1} step={0.05} className="w-full" />
            </Form.Item>
            <Form.Item name="rerank" label={defaults ? <FormLabelHelp label="启用 Rerank">{rerankHelp(defaults)}</FormLabelHelp> : '启用 Rerank'} valuePropName="checked">
              <Switch />
            </Form.Item>
            <Space wrap>
              <Button type="primary" loading={loading} onClick={() => void onRun()}>
                运行检索
              </Button>
              <Button loading={loading} onClick={() => void onCompareStrategies()}>
                对比三种策略
              </Button>
              <Button loading={loading} onClick={() => void onCompareRerank()}>
                对比 Rerank 前后
              </Button>
            </Space>
          </Form>
        </Card>
        <div className="min-h-0 overflow-y-auto">
          {error ? <div className="mb-2 text-sm text-red-500">{error}</div> : null}
          {result ? (
            <>
              <Space wrap className="mb-3">
                <Tag>{knowledgeRetrievalStrategyLabel(result.strategy)}</Tag>
                <Tag>总耗时 {result.latency_ms} ms</Tag>
                {typeof stages.vector_ms === 'number' ? <Tag>向量 {String(stages.vector_ms)} ms</Tag> : null}
                {typeof stages.keyword_ms === 'number' ? <Tag>关键词 {String(stages.keyword_ms)} ms</Tag> : null}
                {typeof stages.rerank_ms === 'number' ? <Tag>Rerank {String(stages.rerank_ms)} ms</Tag> : null}
                {result.rerank_applied ? <Tag color="success">已重排序</Tag> : null}
                {result.rerank_degraded ? <Tag color="warning">Rerank 已降级</Tag> : null}
              </Space>
              <Table rowKey={(row) => `${row.chunk_id}-${row.version}`} size="small" pagination={false} columns={columns} dataSource={result.items} />
              <Descriptions size="small" className="mt-3!" column={1} title="阶段明细">
                <Descriptions.Item label="vector_ranks">{JSON.stringify(stages.vector_ranks ?? [])}</Descriptions.Item>
                <Descriptions.Item label="keyword_ranks">{JSON.stringify(stages.keyword_ranks ?? [])}</Descriptions.Item>
                <Descriptions.Item label="rrf_ranks">{JSON.stringify(stages.rrf_ranks ?? [])}</Descriptions.Item>
              </Descriptions>
            </>
          ) : null}
          {Object.keys(compare).length ? (
            <div className="grid gap-3 lg:grid-cols-3">
              {Object.entries(compare).map(([strategy, item]) => (
                <Card key={strategy} size="small" title={`${knowledgeRetrievalStrategyLabel(strategy)} · ${item?.latency_ms ?? 0}ms`}>
                  {(item?.items ?? []).map((hit) => (
                    <div key={hit.chunk_id} className="mb-2 truncate text-xs">
                      #{hit.final_rank} chunk {hit.chunk_id} {hit.filename}
                    </div>
                  ))}
                </Card>
              ))}
            </div>
          ) : null}
          {rerankPair ? (
            <div className="grid gap-3 lg:grid-cols-2">
              <Card size="small" title={`Rerank 前 · ${rerankPair.off.latency_ms}ms`}>
                <Table size="small" pagination={false} rowKey="chunk_id" dataSource={rerankPair.off.items} columns={columns.slice(0, 4)} />
              </Card>
              <Card size="small" title={`Rerank 后 · ${rerankPair.on.latency_ms}ms${rerankPair.on.rerank_degraded ? '（已降级）' : ''}`}>
                <Table size="small" pagination={false} rowKey="chunk_id" dataSource={rerankPair.on.items} columns={columns.slice(0, 4)} />
              </Card>
            </div>
          ) : null}
          {!result && !Object.keys(compare).length && !rerankPair ? (
            <Card size="small">运行后展示候选排名、融合分数、Rerank 前后对比与耗时。</Card>
          ) : null}
        </div>
      </div>
      <Drawer title={active?.filename} open={active != null} width={560} onClose={() => setActive(null)}>
        {active ? (
          <div>
            <div className="mb-2 text-xs text-slate-500">chunk_id={active.chunk_id} version={active.version}</div>
            <div className="whitespace-pre-wrap text-sm leading-6">{active.content}</div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}

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
import { useState } from 'react';
import { fetchKnowledgeBases } from '@/api/knowledge-bases';
import { testRetrieval } from '@/api/rag';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';

export function RetrievalTestPage() {
  const { tenantId } = usePermissions();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<KnowledgeSearchResult | null>(null);
  const [active, setActive] = useState<KnowledgeSearchHit | null>(null);

  const basesQuery = useQuery({
    queryKey: knowledgeBasesQueryKey(tenantId, { page: 1, pageSize: 100, status: 'ACTIVE' }),
    queryFn: ({ signal }) => fetchKnowledgeBases({ page: 1, pageSize: 100, status: 'ACTIVE' }, signal),
    enabled: tenantId != null,
  });

  const onRun = async () => {
    const values = await form.validateFields();
    setLoading(true);
    setError(null);
    try {
      const data = await testRetrieval({
        query: values.query,
        strategy: values.strategy,
        knowledge_base_ids: values.knowledge_base_ids,
        top_k: values.top_k,
        candidate_k: values.candidate_k,
        similarity_threshold: values.similarity_threshold,
        rerank: values.rerank,
      });
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : '检索失败');
    } finally {
      setLoading(false);
    }
  };

  const stages = result?.stages ?? {};
  const columns: ColumnsType<KnowledgeSearchHit> = [
    { title: '最终排名', dataIndex: 'final_rank', width: 90 },
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
      <PageHeader title="检索测试" description="与知识问答共用同一检索引擎。可对比 VECTOR / KEYWORD / HYBRID，并查看各阶段耗时。" />
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-hidden lg:grid-cols-[320px_1fr]">
        <Card size="small" className="overflow-y-auto" title="参数">
          <Form
            form={form}
            layout="vertical"
            initialValues={{ strategy: 'HYBRID', top_k: 8, candidate_k: 24, rerank: true }}
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
            <Form.Item name="top_k" label="Top-K">
              <InputNumber min={1} max={50} className="w-full" />
            </Form.Item>
            <Form.Item name="candidate_k" label="候选召回数">
              <InputNumber min={1} max={100} className="w-full" />
            </Form.Item>
            <Form.Item name="similarity_threshold" label="向量相似度阈值">
              <InputNumber min={0} max={1} step={0.05} className="w-full" />
            </Form.Item>
            <Form.Item name="rerank" label="启用 Rerank" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Button type="primary" loading={loading} onClick={() => void onRun()}>
              运行检索
            </Button>
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
              <Table
                rowKey={(row) => `${row.chunk_id}-${row.version}`}
                size="small"
                pagination={false}
                columns={columns}
                dataSource={result.items}
              />
              <Descriptions size="small" className="mt-3" column={1} title="阶段明细">
                <Descriptions.Item label="vector_ranks">{JSON.stringify(stages.vector_ranks ?? [])}</Descriptions.Item>
                <Descriptions.Item label="keyword_ranks">{JSON.stringify(stages.keyword_ranks ?? [])}</Descriptions.Item>
                <Descriptions.Item label="rrf_ranks">{JSON.stringify(stages.rrf_ranks ?? [])}</Descriptions.Item>
              </Descriptions>
            </>
          ) : (
            <Card size="small">运行后展示候选排名、融合分数与耗时。</Card>
          )}
        </div>
      </div>
      <Drawer title={active?.filename} open={active != null} width={560} onClose={() => setActive(null)}>
        {active ? <div className="whitespace-pre-wrap text-sm leading-6">{active.content}</div> : null}
      </Drawer>
    </div>
  );
}

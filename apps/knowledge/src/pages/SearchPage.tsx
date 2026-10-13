import {
  knowledgeBasesQueryKey,
  knowledgeRetrievalStrategyLabel,
  KNOWLEDGE_RETRIEVAL_STRATEGY,
  type KnowledgeSearchHit,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, Drawer, Empty, Input, Select, Space, Tag } from 'antd';
import { useMemo, useState } from 'react';
import { fetchKnowledgeBases } from '@/api/knowledge-bases';
import { searchKnowledge } from '@/api/rag';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';

const STRATEGY_OPTIONS = Object.values(KNOWLEDGE_RETRIEVAL_STRATEGY).map((value) => ({
  value,
  label: knowledgeRetrievalStrategyLabel(value),
}));

export function SearchPage() {
  const { tenantId } = usePermissions();
  const [query, setQuery] = useState('');
  const [strategy, setStrategy] = useState('HYBRID');
  const [baseIds, setBaseIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hits, setHits] = useState<KnowledgeSearchHit[]>([]);
  const [latency, setLatency] = useState<number | null>(null);
  const [active, setActive] = useState<KnowledgeSearchHit | null>(null);

  const basesQuery = useQuery({
    queryKey: knowledgeBasesQueryKey(tenantId, { page: 1, pageSize: 100, status: 'ACTIVE' }),
    queryFn: ({ signal }) => fetchKnowledgeBases({ page: 1, pageSize: 100, status: 'ACTIVE' }, signal),
    enabled: tenantId != null,
  });

  const options = useMemo(
    () => (basesQuery.data?.items ?? []).map((item) => ({ value: item.id, label: item.name })),
    [basesQuery.data],
  );

  const onSearch = async () => {
    const text = query.trim();
    if (!text) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await searchKnowledge({
        query: text,
        strategy,
        knowledge_base_ids: baseIds.length ? baseIds : undefined,
      });
      setHits(result.items);
      setLatency(result.latency_ms);
    } catch (err) {
      setHits([]);
      setError(err instanceof Error ? err.message : '检索失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PageHeader title="智能搜索" description="在已向量化的知识库中检索切片，结果含文档名、页码与相关度。" />
      <Space wrap className="mb-3 shrink-0">
        <Input.Search
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onSearch={() => void onSearch()}
          placeholder="输入要检索的问题"
          style={{ width: 360 }}
          enterButton="搜索"
          loading={loading}
        />
        <Select value={strategy} onChange={setStrategy} options={STRATEGY_OPTIONS} style={{ width: 160 }} />
        <Select
          mode="multiple"
          allowClear
          placeholder="全部有权知识库"
          value={baseIds}
          onChange={setBaseIds}
          options={options}
          style={{ minWidth: 240 }}
        />
      </Space>
      {latency != null ? <div className="mb-2 text-xs text-slate-500">耗时 {latency} ms</div> : null}
      {error ? <div className="mb-2 text-sm text-red-500">{error}</div> : null}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {hits.length === 0 ? (
          <Empty description={loading ? '检索中' : '输入问题后查看检索结果'} />
        ) : (
          <div className="flex flex-col gap-3">
            {hits.map((hit) => (
              <Card
                key={`${hit.chunk_id}-${hit.version}`}
                size="small"
                title={
                  <Space>
                    <span>{hit.filename}</span>
                    <Tag>#{hit.final_rank}</Tag>
                  </Space>
                }
                extra={
                  <Button type="link" size="small" onClick={() => setActive(hit)}>
                    查看原文
                  </Button>
                }
              >
                <div className="mb-2 line-clamp-4 text-sm text-slate-700">{hit.content}</div>
                <Space wrap size={4} className="text-xs text-slate-500">
                  {hit.page_no != null ? <Tag>页 {hit.page_no}</Tag> : null}
                  {hit.heading ? <Tag>{hit.heading}</Tag> : null}
                  {hit.vector_score != null ? <Tag>向量 {hit.vector_score.toFixed(3)}</Tag> : null}
                  {hit.keyword_score != null ? <Tag>关键词 {hit.keyword_score.toFixed(3)}</Tag> : null}
                  {hit.rrf_score != null ? <Tag>RRF {hit.rrf_score.toFixed(4)}</Tag> : null}
                </Space>
              </Card>
            ))}
          </div>
        )}
      </div>
      <Drawer title={active?.filename} open={active != null} onClose={() => setActive(null)} width={560}>
        {active ? (
          <div className="whitespace-pre-wrap text-sm leading-6 text-slate-800">{active.content}</div>
        ) : null}
      </Drawer>
    </div>
  );
}

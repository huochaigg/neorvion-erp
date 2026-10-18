import { Collapse, Descriptions, Statistic, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { MetricBars } from '@/components/MetricBars';

export type EvalRetrievedHit = {
  chunk_id?: number;
  document_id?: number;
  filename?: string;
  content?: string;
  final_rank?: number;
  vector_score?: number | null;
  keyword_score?: number | null;
  rrf_score?: number | null;
  rerank_score?: number | null;
  relevance?: number | null;
};

export type EvalCaseResultView = {
  question: string;
  expected_answer?: string | null;
  answer?: string | null;
  is_unanswerable?: boolean;
  error_message?: string | null;
  judge_error?: string | null;
  retrieval_metrics?: Record<string, unknown> | null;
  generation_metrics?: Record<string, unknown> | null;
  retrieved?: EvalRetrievedHit[] | Record<string, unknown>[];
  latency_ms?: number | null;
  usage?: Record<string, unknown> | null;
  stages?: Record<string, unknown> | null;
  strategy?: string | null;
  raw?: unknown;
};

function metricValue(metrics: Record<string, unknown> | null | undefined, key: string): number | null {
  if (!metrics || 'skipped' in metrics) return null;
  const value = metrics[key];
  return typeof value === 'number' ? value : null;
}

function metricLabel(metrics: Record<string, unknown> | null | undefined, key: string): string {
  if (!metrics) return '无数据';
  if (metrics.skipped) return '不适用';
  if (!(key in metrics) || metrics[key] == null) return '无数据';
  const value = metrics[key];
  return typeof value === 'number' ? value.toFixed(3) : '无数据';
}

function scoreText(value: number | null | undefined): string {
  return typeof value === 'number' ? value.toFixed(4) : '无数据';
}

function statusTag(view: EvalCaseResultView) {
  if (view.error_message) return <Tag color="error">失败</Tag>;
  if (view.judge_error) return <Tag color="warning">裁判失败</Tag>;
  if (view.retrieval_metrics?.skipped) return <Tag>不适用</Tag>;
  if (!view.retrieved?.length && !view.retrieval_metrics) return <Tag>未执行</Tag>;
  if (!view.retrieved?.length) return <Tag>无检索结果</Tag>;
  return <Tag color="success">已完成</Tag>;
}

function usageNumber(usage: Record<string, unknown> | null | undefined, key: string): string {
  if (!usage || !(key in usage) || usage[key] == null) return '无数据';
  const value = usage[key];
  return typeof value === 'number' ? String(value) : String(value);
}

export function EvalCaseResultPanel({ view }: { view: EvalCaseResultView }) {
  const metrics = view.retrieval_metrics ?? null;
  const hits = (view.retrieved ?? []) as EvalRetrievedHit[];
  const generationMs =
    typeof view.stages?.generation_ms === 'number'
      ? view.stages.generation_ms
      : typeof view.usage?.generation_ms === 'number'
        ? view.usage.generation_ms
        : null;
  const retrievalMs =
    typeof view.stages?.total_ms === 'number'
      ? view.stages.total_ms
      : typeof view.latency_ms === 'number'
        ? view.latency_ms
        : null;

  const columns: ColumnsType<EvalRetrievedHit> = [
    { title: '排名', dataIndex: 'final_rank', width: 70 },
    { title: '文档', dataIndex: 'filename', ellipsis: true, render: (value?: string) => value || '无数据' },
    { title: 'Chunk', dataIndex: 'chunk_id', width: 90 },
    { title: 'Vector', width: 90, render: (_, row) => scoreText(row.vector_score) },
    { title: 'Keyword', width: 90, render: (_, row) => scoreText(row.keyword_score) },
    { title: 'RRF', width: 90, render: (_, row) => scoreText(row.rrf_score) },
    { title: 'Rerank', width: 90, render: (_, row) => scoreText(row.rerank_score) },
    {
      title: '相关性',
      width: 80,
      render: (_, row) => (row.relevance == null ? '未标注' : String(row.relevance)),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {statusTag(view)}
        {view.strategy ? <Tag>{view.strategy}</Tag> : null}
        {view.is_unanswerable ? <Tag>无答案题</Tag> : null}
      </div>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="问题">{view.question || '无数据'}</Descriptions.Item>
        <Descriptions.Item label="标准答案">{view.expected_answer || (view.is_unanswerable ? '本题无标准答案' : '无数据')}</Descriptions.Item>
        <Descriptions.Item label="实际回答">{view.answer || (view.generation_metrics ? '无数据' : '未执行生成')}</Descriptions.Item>
      </Descriptions>
      {view.error_message ? <div className="text-sm text-red-500">{view.error_message}</div> : null}
      {view.judge_error ? <div className="text-sm text-amber-600">裁判失败：{view.judge_error}（未伪造分数）</div> : null}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Statistic title="Hit Rate（0-1，非百分比）" value={metricLabel(metrics, 'hit_rate')} />
        <Statistic title="Recall（0-1）" value={metricLabel(metrics, 'recall')} />
        <Statistic title="MRR" value={metricLabel(metrics, 'mrr')} />
        <Statistic title="nDCG（0-1）" value={metricLabel(metrics, 'ndcg')} />
      </div>
      <div className="text-xs text-slate-500">下列进度条仅用于相对对比，Hit/Recall/nDCG 本身是 0–1 分数，不是百分比。</div>
      <MetricBars
        items={[
          { label: 'Hit Rate', value: metricValue(metrics, 'hit_rate') },
          { label: 'Recall', value: metricValue(metrics, 'recall') },
          { label: 'Precision', value: metricValue(metrics, 'precision') },
          { label: 'nDCG', value: metricValue(metrics, 'ndcg') },
        ]}
      />
      <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        <div>检索耗时：{retrievalMs == null ? '无数据' : `${retrievalMs} ms`}</div>
        <div>生成耗时：{generationMs == null ? '未执行' : `${generationMs} ms`}</div>
        <div>Prompt Token：{usageNumber(view.usage, 'prompt_tokens')}</div>
        <div>Completion Token：{usageNumber(view.usage, 'completion_tokens')}</div>
        <div>估算费用：{usageNumber(view.usage, 'estimated_cost_usd') === '无数据' ? '无数据' : `$${usageNumber(view.usage, 'estimated_cost_usd')}`}</div>
      </div>
      <Table<EvalRetrievedHit>
        size="small"
        rowKey={(row, index) => String(row.chunk_id ?? index)}
        columns={columns}
        dataSource={hits}
        pagination={false}
        scroll={{ x: 900 }}
        expandable={{
          expandedRowRender: (row) => (
            <div className="space-y-2 text-xs">
              <div>来源文档 ID：{row.document_id ?? '无数据'}</div>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2">{row.content || '无切片原文'}</pre>
            </div>
          ),
        }}
        locale={{ emptyText: '无检索结果' }}
      />
      {view.answer ? (
        <Collapse
          items={[{ key: 'answer', label: '模型回答全文', children: <pre className="whitespace-pre-wrap text-xs">{view.answer}</pre> }]}
        />
      ) : null}
      <Collapse
        items={[
          {
            key: 'raw',
            label: '原始数据',
            children: (
              <pre className="max-h-64 overflow-auto rounded bg-slate-50 p-2 text-xs">
                {JSON.stringify(view.raw ?? view, null, 2)}
              </pre>
            ),
          },
        ]}
      />
    </div>
  );
}

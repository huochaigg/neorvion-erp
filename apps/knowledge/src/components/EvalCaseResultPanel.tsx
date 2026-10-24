import { knowledgeEvalStageLabel } from '@neorvion/shared';
import { Collapse, Descriptions, Space, Statistic, Table, Tag } from 'antd';
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
  generation_truncated?: boolean;
  in_prompt?: boolean;
  omitted_reason?: string | null;
  partially_truncated?: boolean;
  content_chars?: number;
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

function stageStatusColor(status: string): string {
  if (status === 'SUCCESS' || status === 'SKIPPED' || status === 'DEGRADED') return 'success';
  if (status === 'FAILED') return 'error';
  return 'default';
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

type EvidenceFactRow = {
  fact_id: string;
  covered?: boolean;
  evaluable?: boolean;
  hit_role?: string | null;
  hit_chunk_ids?: number[];
  primary_chunk_ids?: number[];
  alternative_chunk_ids?: number[];
  partial_chunk_ids?: number[];
  partial_hit_chunk_ids?: number[];
};

function evidenceFacts(metrics: Record<string, unknown> | null | undefined): EvidenceFactRow[] {
  const raw = metrics?.facts;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is EvidenceFactRow => !!item && typeof item === 'object' && 'fact_id' in item);
}

function chunkList(ids: number[] | undefined): string {
  if (!ids?.length) {
    return '无';
  }
  return ids.map((id) => `#${id}`).join('、');
}

export function EvalCaseResultPanel({ view }: { view: EvalCaseResultView }) {
  const metrics = view.retrieval_metrics ?? null;
  const generation = view.generation_metrics ?? null;
  const citation = generation?.citation && typeof generation.citation === 'object' ? (generation.citation as Record<string, unknown>) : null;
  const hits = (view.retrieved ?? []) as EvalRetrievedHit[];
  const omittedHits = hits.filter((item) => item.in_prompt === false);
  const retrievedIds = hits
    .map((item) => item.chunk_id)
    .filter((id): id is number => typeof id === 'number');
  const promptIdsFromHits = hits
    .filter((item) => item.in_prompt === true)
    .map((item) => item.chunk_id)
    .filter((id): id is number => typeof id === 'number');
  const omittedIds = Array.isArray(generation?.omitted_chunk_ids)
    ? (generation.omitted_chunk_ids as number[])
    : omittedHits.map((item) => item.chunk_id).filter((id): id is number => typeof id === 'number');
  const budgetLimited =
    generation?.context_budget_limited === true ||
    generation?.prompt_truncated === true ||
    omittedHits.some((item) => item.omitted_reason === 'budget' || (item.omitted_reason == null && item.in_prompt === false));
  const truncationReason =
    typeof generation?.truncation_reason === 'string'
      ? generation.truncation_reason
      : budgetLimited
        ? 'budget'
        : omittedHits.length
          ? 'other'
          : null;
  const budgetUsed =
    typeof generation?.budget_used_chars === 'number'
      ? generation.budget_used_chars
      : typeof generation?.prompt_used_chars === 'number'
        ? generation.prompt_used_chars
        : null;
  const budgetLimit = typeof generation?.budget_limit_chars === 'number' ? generation.budget_limit_chars : null;
  const omittedCount =
    typeof generation?.omitted_chunk_count === 'number' ? generation.omitted_chunk_count : omittedIds.length;
  const partialCount =
    typeof generation?.partially_truncated_chunk_count === 'number'
      ? generation.partially_truncated_chunk_count
      : hits.filter((item) => item.partially_truncated).length;
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
    {
      title: '进 Prompt',
      width: 110,
      render: (_, row) => {
        if (row.in_prompt === true) return '是';
        if (row.in_prompt === false) {
          if (row.partially_truncated) return '部分截断';
          if (row.omitted_reason === 'empty') return '否（空切片）';
          if (row.omitted_reason === 'duplicate') return '否（重复）';
          return '否（预算）';
        }
        return '-';
      },
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {statusTag(view)}
        {view.strategy ? <Tag>{view.strategy}</Tag> : null}
        {view.is_unanswerable ? <Tag>无答案题</Tag> : null}
      </div>
      <Descriptions size="small" column={1} bordered className='mb-4!'>
        <Descriptions.Item label="问题">{view.question || '无数据'}</Descriptions.Item>
        <Descriptions.Item label="标准答案">{view.expected_answer || (view.is_unanswerable ? '本题无标准答案' : '无数据')}</Descriptions.Item>
        <Descriptions.Item label="实际回答">{view.answer || (view.generation_metrics ? '无数据' : '未执行生成')}</Descriptions.Item>
      </Descriptions>
      {view.stages && Object.keys(view.stages).some((key) => ['RETRIEVE', 'RERANK', 'GENERATE', 'JUDGE', 'METRICS'].includes(key)) ? (
        <Space wrap>
          {['RETRIEVE', 'RERANK', 'GENERATE', 'JUDGE', 'METRICS'].map((name) => {
            const entry = view.stages?.[name];
            const status =
              entry && typeof entry === 'object' && 'status' in entry ? String((entry as { status?: string }).status) : 'PENDING';
            const error =
              entry && typeof entry === 'object' && 'error' in entry ? String((entry as { error?: string }).error ?? '') : '';
            return (
              <Tag key={name} color={stageStatusColor(status)} title={error || undefined}>
                {knowledgeEvalStageLabel(name)} · {status}
              </Tag>
            );
          })}
        </Space>
      ) : null}
      {view.retrieval_metrics?.false_recall_definition === 'top_k_nonempty_not_hallucination_rate' ? (
        <div className="text-xs text-slate-500">false_recall 表示 Top-K 非空，不是幻觉率，也不是错误证据率。</div>
      ) : null}
      {Array.isArray(view.retrieved) && view.retrieved.some((item) => item && typeof item === 'object' && 'generation_truncated' in item && item.generation_truncated) ? (
        <div className="text-xs text-slate-500">
          生成上下文按与问答相同的字符预算整片跳过，不是把一篇切成半片；列表中的正文仍是 500 字展示摘要。
        </div>
      ) : null}
      {view.error_message ? <div className="text-sm text-red-500">{view.error_message}</div> : null}
      {view.judge_error ? <div className="text-sm text-amber-600">裁判失败：{view.judge_error}（未伪造分数）</div> : null}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 mt-4!">
        <Statistic title="Hit Rate（0-1，非百分比）" value={metricLabel(metrics, 'hit_rate')} />
        <Statistic title="Recall（0-1）" value={metricLabel(metrics, 'recall')} />
        <Statistic title="MRR" value={metricLabel(metrics, 'mrr')} />
        <Statistic title="nDCG（0-1）" value={metricLabel(metrics, 'ndcg')} />
        <Statistic title="Evidence Coverage@K" value={metricLabel(metrics, 'evidence_coverage_at_k')} />
        <Statistic
          title="Complete Evidence@K"
          value={
            metrics?.complete_evidence_at_k === true ? '是' : metrics?.complete_evidence_at_k === false ? '否' : '无数据'
          }
        />
        <Statistic title="Faithfulness" value={metricLabel(generation, 'faithfulness')} />
        <Statistic title="Correctness" value={metricLabel(generation, 'answer_correctness')} />
        <Statistic title="Relevancy" value={metricLabel(generation, 'answer_relevancy')} />
        <Statistic title="Citation Correctness（历史）" value={metricLabel(generation, 'citation_correctness')} />
        <Statistic
          title="引用合法性"
          value={
            metricLabel(generation, 'citation_validity') !== '无数据'
              ? metricLabel(generation, 'citation_validity')
              : metricLabel(citation, 'citation_index_precision')
          }
        />
        <Statistic
          title="Gold 命中"
          value={
            metricLabel(generation, 'gold_citation_match') !== '无数据'
              ? metricLabel(generation, 'gold_citation_match')
              : metricLabel(citation, 'citation_supported_rate')
          }
        />
        <Statistic
          title="主张支持"
          value={
            generation?.claim_support_skipped === 'not_evaluated' || (generation && generation.claim_support == null)
              ? '未评测'
              : metricLabel(generation, 'claim_support')
          }
        />
      </div>
      {generation ? (
        <div className="space-y-1 text-xs text-slate-600">
          <div>
            检索 Chunk：{chunkList(
              retrievedIds.length
                ? retrievedIds
                : Array.isArray(generation.retrieved_chunk_ids)
                  ? (generation.retrieved_chunk_ids as number[])
                  : undefined,
            )}
          </div>
          <div>
            Prompt Chunk：{chunkList(
              promptIdsFromHits.length
                ? promptIdsFromHits
                : Array.isArray(generation.prompt_chunk_ids)
                  ? (generation.prompt_chunk_ids as number[])
                  : undefined,
            )}
            {budgetLimited ? '（上下文预算不足，整片跳过）' : truncationReason === 'empty' ? '（存在空切片）' : ''}
          </div>
          <div>
            未进入 Prompt：{chunkList(omittedIds)}
            {omittedCount ? ` · omitted=${omittedCount}` : ''}
            {partialCount ? ` · 半片截断=${partialCount}` : ' · 半片截断=0'}
          </div>
          <div>
            上下文字符：{budgetUsed == null ? '无数据' : budgetUsed}
            {budgetLimit == null ? '' : ` / ${budgetLimit}`}
            {truncationReason ? ` · truncation_reason=${truncationReason}` : ''}
            {budgetLimited ? ' · context_budget_limited=true' : ''}
          </div>
          <div>
            Prompt Coverage：
            {typeof generation.prompt_evidence_coverage_at_k === 'number'
              ? Number(generation.prompt_evidence_coverage_at_k).toFixed(3)
              : generation.prompt_evidence_coverage_skipped
                ? `跳过（${String(generation.prompt_evidence_coverage_skipped)}）`
                : '无数据'}
          </div>
          <div>
            引用：{String(citation?.status ?? '无数据')}
            {Array.isArray(citation?.cited_chunk_ids) && citation.cited_chunk_ids.length
              ? ` → ${chunkList(citation.cited_chunk_ids as number[])}`
              : '（无 [n] 时引用指标为空，不是 0）'}
            。Gold 命中不是真实引用正确率；主张支持当前未评测。
          </div>
          {generation.is_unanswerable ? (
            <div>
              拒答：{generation.refused === true ? '是' : generation.refused === false ? '否' : '无 Judge 判定'}
              {generation.fabricated_status === 'likely_fabricated' && Array.isArray(generation.fabricated_terms)
                ? `；可能编造了 ${(generation.fabricated_terms as string[]).join('、')}`
                : generation.fabricated_status === 'needs_review' || generation.fabricated_status === 'unknown'
                  ? '；编造无法可靠判断，待人工复核'
                  : generation.fabricated === true && Array.isArray(generation.fabricated_terms)
                    ? `；可能编造了 ${(generation.fabricated_terms as string[]).join('、')}`
                    : '；未发现具体数值/时刻/电话编造'}
            </div>
          ) : null}
          {generation.is_false_premise ? (
            <div>
              错误前提识别：{generation.false_premise_identified === true ? '是' : generation.false_premise_identified === false ? '否' : '无数据'}
              ；纠正分：{metricLabel(generation, 'correction_correctness')}
            </div>
          ) : null}
          {typeof generation.explanation === 'string' && generation.explanation ? (
            <div>Judge 说明：{generation.explanation}</div>
          ) : null}
        </div>
      ) : null}
      {Array.isArray(metrics?.required_facts) && (metrics?.required_facts as unknown[]).length > 0 ? (
        <div className="space-y-2">
          <div className="text-sm text-slate-600">
            必要事实：{(metrics?.required_facts as unknown[]).map(String).join('、') || '无'}
          </div>
          <div className="text-sm text-slate-600">
            未覆盖：
            {Array.isArray(metrics?.uncovered_facts) && (metrics?.uncovered_facts as unknown[]).length
              ? (metrics?.uncovered_facts as unknown[]).map(String).join('、')
              : '无'}
          </div>
          <Table<EvidenceFactRow>
            size="small"
            rowKey="fact_id"
            pagination={false}
            dataSource={evidenceFacts(metrics)}
            columns={[
              { title: 'Fact', dataIndex: 'fact_id', width: 180 },
              {
                title: '状态',
                width: 90,
                render: (_, row) =>
                  row.evaluable === false ? '不可评测' : row.covered ? '已覆盖' : '未覆盖',
              },
              {
                title: '命中角色',
                width: 110,
                render: (_, row) => row.hit_role || '-',
              },
              {
                title: '命中 Chunk',
                render: (_, row) => chunkList(row.hit_chunk_ids),
              },
              {
                title: 'primary',
                render: (_, row) => chunkList(row.primary_chunk_ids),
              },
              {
                title: 'alternative',
                render: (_, row) => chunkList(row.alternative_chunk_ids),
              },
            ]}
            locale={{ emptyText: '本题没有 required_facts' }}
          />
        </div>
      ) : view.is_unanswerable ? (
        <div className="text-xs text-slate-500">无答案题不计算 Evidence Coverage，仍使用 empty_ok / false_recall。</div>
      ) : metrics?.evidence_coverage_skipped ? (
        <div className="text-xs text-slate-500">Evidence Coverage 已跳过：{String(metrics.evidence_coverage_skipped)}</div>
      ) : null}
      <div className="text-xs text-slate-500">下列进度条仅用于相对对比，Hit/Recall/nDCG 本身是 0–1 分数，不是百分比。</div>
      <MetricBars
        items={[
          { label: 'Hit Rate', value: metricValue(metrics, 'hit_rate') },
          { label: 'Recall', value: metricValue(metrics, 'recall') },
          { label: 'Precision', value: metricValue(metrics, 'precision') },
          { label: 'nDCG', value: metricValue(metrics, 'ndcg') },
          { label: 'Coverage', value: metricValue(metrics, 'evidence_coverage_at_k') },
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
          className='mt-4!'
          items={[{ key: 'answer', label: '模型回答全文', children: <pre className="whitespace-pre-wrap text-xs">{view.answer}</pre> }]}
        />
      ) : null}
      <Collapse
        className='mt-4!'
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

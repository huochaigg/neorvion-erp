import {
  knowledgeEvalLabelSuggestionStatusColor,
  knowledgeEvalLabelSuggestionStatusLabel,
  knowledgeEvalLabelSuggestionsQueryKey,
  PERMISSION_CODE,
  type KnowledgeEvalLabelSuggestion,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Drawer, Form, Input, InputNumber, Popconfirm, Select, Space, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import {
  confirmEvalLabelSuggestions,
  deleteEvalLabelSuggestion,
  fetchEvalLabelJob,
  fetchEvalLabelSuggestions,
  isLiveEvalLabelJob,
  rejectEvalLabelSuggestion,
  runEvalLabelSuggestions,
  updateEvalLabelSuggestion,
} from '@/api/evaluation';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { usePermissions } from '@/hooks/usePermissions';

const CONFIDENCE_OPTIONS = [
  { value: '', label: '全部置信度' },
  { value: 'HIGH', label: 'HIGH 优先审核' },
  { value: 'MEDIUM', label: 'MEDIUM' },
  { value: 'LOW', label: 'LOW' },
];

const VERDICT_OPTIONS = [
  { value: 'ANSWERABLE', label: 'ANSWERABLE 可回答' },
  { value: 'UNANSWERABLE', label: 'UNANSWERABLE 无答案' },
  { value: 'PARTIAL', label: 'PARTIAL 部分' },
  { value: 'CONFLICT', label: 'CONFLICT 冲突' },
  { value: 'INSUFFICIENT', label: 'INSUFFICIENT 证据不足' },
];

function hasPositiveItems(record: { items: { relevance: number }[] }): boolean {
  return record.items.some((item) => item.relevance >= 1);
}

function draftConfirmBlockReason(record: KnowledgeEvalLabelSuggestion): string | null {
  if (record.verdict === 'UNANSWERABLE' && !record.is_unanswerable && !hasPositiveItems(record)) {
    return '这是前提错误题，不是无答案题。不要改题目。请补纠正切片后确认，或驳回后点「重试无切片草稿」。';
  }
  if (record.verdict !== 'UNANSWERABLE' && !hasPositiveItems(record)) {
    return '这道草稿没有相关性≥1的切片，不能标成可评测。请先查看证据并补切片，或驳回后重试初标。';
  }
  return null;
}

type LabelSuggestionPatch = Parameters<typeof updateEvalLabelSuggestion>[1];

function coerceRebuttalValues(record: KnowledgeEvalLabelSuggestion, values: LabelSuggestionPatch): LabelSuggestionPatch {
  const items = values.items ?? record.items;
  const hasEvidence = items.some((item) => Number(item.relevance ?? 0) >= 1);
  if (values.verdict === 'UNANSWERABLE' && !record.is_unanswerable && hasEvidence) {
    return { ...values, verdict: 'ANSWERABLE' };
  }
  return values;
}

export function EvaluationLabelSuggestionsPanel({ datasetId }: { datasetId: number }) {
  const { message } = App.useApp();
  const { tenantId } = usePermissions();
  const queryClient = useQueryClient();
  const [confidence, setConfidence] = useState('');
  const [active, setActive] = useState<KnowledgeEvalLabelSuggestion | null>(null);
  const [form] = Form.useForm();

  const suggestionsQuery = useQuery({
    queryKey: knowledgeEvalLabelSuggestionsQueryKey(tenantId, datasetId, { confidence }),
    queryFn: ({ signal }) => fetchEvalLabelSuggestions(datasetId, { confidence }, signal),
    enabled: tenantId != null && Number.isFinite(datasetId),
  });
  const allSuggestionsQuery = useQuery({
    queryKey: knowledgeEvalLabelSuggestionsQueryKey(tenantId, datasetId, { confidence: '' }),
    queryFn: ({ signal }) => fetchEvalLabelSuggestions(datasetId, {}, signal),
    enabled: tenantId != null && Number.isFinite(datasetId),
  });
  const jobQuery = useQuery({
    queryKey: ['tenant', tenantId, 'knowledge-eval-label-job', datasetId],
    queryFn: ({ signal }) => fetchEvalLabelJob(datasetId, signal),
    enabled: tenantId != null && Number.isFinite(datasetId),
    refetchInterval: (query) => (isLiveEvalLabelJob(query.state.data?.status) ? 2000 : false),
  });
  const jobStatus = jobQuery.data?.status;
  const jobType = jobQuery.data?.job_type ?? 'SUGGEST';
  const jobActive = isLiveEvalLabelJob(jobStatus);
  const allSuggestions = allSuggestionsQuery.data ?? [];
  const liveDrafts = allSuggestions.filter((item) => item.status === 'DRAFT' && !item.case_deleted);
  const liveDraftCount = liveDrafts.length;
  const liveHighDraftCount = liveDrafts.filter((item) => item.confidence === 'HIGH').length;
  const liveMediumDraftCount = liveDrafts.filter((item) => item.confidence === 'MEDIUM').length;
  const liveLowDraftCount = liveDrafts.filter((item) => item.confidence === 'LOW').length;
  const liveFailedCount = allSuggestions.filter((item) => item.status === 'FAILED' && !item.case_deleted).length;
  const liveEmptyDraftCount = liveDrafts.filter((item) => draftConfirmBlockReason(item) != null).length;
  const showJobSucceeded = jobType !== 'CONFIRM' && jobStatus === 'SUCCEEDED' && liveDraftCount > 0;
  const confirmSummary = jobType === 'CONFIRM' && (jobStatus === 'SUCCEEDED' || jobStatus === 'FAILED') ? jobQuery.data : null;
  useEffect(() => {
    if (jobStatus !== 'SUCCEEDED' && jobStatus !== 'FAILED' && jobStatus !== 'CANCELLED') return;
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-label-suggestions'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-cases'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-dataset'] });
  }, [jobStatus, jobQuery.data?.id, jobQuery.data?.finished_at, queryClient, tenantId]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-label-suggestions'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-cases'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-dataset'] });
  };

  const runLabels = useMutation({
    mutationFn: (payload: {
      execute: boolean;
      rerun?: boolean;
      only_failed?: boolean;
      only_rejected?: boolean;
      only_empty?: boolean;
    }) => runEvalLabelSuggestions(datasetId, payload),
    onSuccess: (result) => {
      if (result.accepted) {
        message.success(result.already_running ? '已有初标任务在进行，继续查看进度' : '已开始初标，页面会自动刷新进度');
        void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-label-job', datasetId] });
        return;
      }
      message.info(
        `待初标 ${result.pending_cases} 题，跳过已确认 ${result.skipped_cases ?? 0} 题。预计对话 ${result.chat_calls} 次，问题向量 ${result.embedding_calls} 次，不重新向量化文档。`,
      );
    },
    onError: (error: Error) => message.error(error.message),
  });

  const confirmHigh = useMutation({
    mutationFn: () => confirmEvalLabelSuggestions(datasetId, { only_high: true }),
    onSuccess: (result) => {
      if (result.accepted) {
        message.success(result.already_running ? '已有任务在进行，继续查看进度' : '已开始批量确认，可继续使用其他页面');
        void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-label-job', datasetId] });
        return;
      }
      if (!result.confirmed && !(result.errors ?? []).length) {
        const pending = result.pending_drafts ?? liveDraftCount;
        message.info(
          pending
            ? `没有 HIGH 草稿可批量确认。剩余 ${pending} 道是 MEDIUM/LOW，需要打开「查看证据」逐条审核。`
            : '没有可确认的高置信度草稿',
        );
        return;
      }
      message.success(`已确认 ${result.confirmed} 道高置信度题`);
      if (result.errors?.length) message.warning(result.errors.map((item) => item.message).join('；'));
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeEvalLabelSuggestion> = [
    {
      title: '问题',
      dataIndex: 'question',
      width: 400,
      onHeaderCell: () => ({ style: { width: 400, minWidth: 400, maxWidth: 400 } }),
      onCell: () => ({ style: { width: 400, minWidth: 400, maxWidth: 400, whiteSpace: 'normal' } }),
      render: (value: string) => <span className="block max-w-full whitespace-normal break-words">{value}</span>,
    },
    { title: '置信度', dataIndex: 'confidence', width: 90, render: (value: string) => <Tag>{value}</Tag> },
    { title: '结论', dataIndex: 'verdict', width: 130 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 160,
      render: (value: string, record) => (
        <Space size={4} wrap>
          <Tag color={knowledgeEvalLabelSuggestionStatusColor(value)}>
            {knowledgeEvalLabelSuggestionStatusLabel(value)}
          </Tag>
          {record.case_deleted ? <Tag>题目已删除</Tag> : null}
        </Space>
      ),
    },
    {
      title: '建议切片',
      width: 90,
      render: (_, record) => record.items.filter((item) => item.relevance >= 1).length,
    },
    {
      title: '操作',
      width: 220,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setActive(record);
              form.setFieldsValue({
                confidence: record.confidence,
                verdict: record.verdict,
                rationale: record.rationale,
                risk: record.risk,
                items: record.items.map((item) => ({
                  chunk_id: item.chunk_id,
                  relevance: item.relevance,
                  reason: item.reason,
                  excerpt: item.excerpt,
                })),
              });
            }}
          >
            查看证据
          </Button>
          {record.case_deleted ? (
            <Can permission={PERMISSION_CODE.knowledgeUpdate}>
              <Popconfirm
                title="删除这条初标草稿？"
                description="工作稿里的题目已经删除，确认和驳回都没有落点。"
                onConfirm={() =>
                  deleteEvalLabelSuggestion(record.id)
                    .then(() => {
                      message.success('已删除初标草稿');
                      if (active?.id === record.id) setActive(null);
                      invalidate();
                    })
                    .catch((error: Error) => message.error(error.message))
                }
              >
                <Button type="link" size="small" danger>
                  删除
                </Button>
              </Popconfirm>
            </Can>
          ) : null}
          {record.status === 'DRAFT' && !record.case_deleted ? (
            <Can permission={PERMISSION_CODE.knowledgeUpdate}>
              {draftConfirmBlockReason(record) ? (
                <Tooltip title={draftConfirmBlockReason(record)}>
                  <Button type="link" size="small" disabled>
                    确认
                  </Button>
                </Tooltip>
              ) : (
                <Button
                  type="link"
                  size="small"
                  onClick={() =>
                    confirmEvalLabelSuggestions(datasetId, { suggestion_ids: [record.id], only_high: false })
                      .then((result) => {
                        if (result.errors?.length) {
                          message.warning(result.errors[0]?.message ?? '没有确认');
                          return;
                        }
                        message.success('已确认并标为可评测');
                        invalidate();
                      })
                      .catch((error: Error) => message.error(error.message))
                  }
                >
                  确认
                </Button>
              )}
              <Button
                type="link"
                size="small"
                danger
                onClick={() =>
                  rejectEvalLabelSuggestion(record.id, '驳回，等待重新初标')
                    .then(() => {
                      message.success('已驳回');
                      invalidate();
                    })
                    .catch((error: Error) => message.error(error.message))
                }
              >
                驳回
              </Button>
            </Can>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <>
      <Alert
        className="mb-3!"
        type="warning"
        showIcon
        title="智能初标只生成草稿。提交后马上返回，页面每 2 秒刷新进度。批量确认也是后台任务，确认后才会变成可评测。"
      />
      {jobActive ? (
        <Alert
          className="mb-3!"
          type="info"
          showIcon
          title={
            jobType === 'CONFIRM'
              ? `正在批量确认 ${jobQuery.data?.processed ?? 0}/${jobQuery.data?.total ?? 0}，成功 ${jobQuery.data?.succeeded ?? 0}，跳过 ${jobQuery.data?.skipped ?? 0}，失败 ${jobQuery.data?.failed ?? 0}。`
              : `正在初标 ${jobQuery.data?.drafted ?? 0}/${jobQuery.data?.total ?? 0}，失败 ${jobQuery.data?.failed ?? 0}。`
          }
        />
      ) : null}
      {jobType !== 'CONFIRM' && jobStatus === 'FAILED' ? (
        <Alert className="mb-3!" type="error" showIcon title={jobQuery.data?.error_message || '初标失败，可以重试失败题'} />
      ) : null}
      {showJobSucceeded ? (
        <Alert
          className="mb-3!"
          type="success"
          showIcon
          title={`初标结束：还有 ${liveDraftCount} 道草稿待确认（HIGH ${liveHighDraftCount}，MEDIUM ${liveMediumDraftCount}，LOW ${liveLowDraftCount}）${liveEmptyDraftCount ? `，其中 ${liveEmptyDraftCount} 道没有切片` : ''}${liveFailedCount ? `，失败 ${liveFailedCount} 道` : ''}。无切片草稿请点「重试无切片草稿」，不要手填 ID。批量确认只处理 HIGH。确认前还不是可评测。`}
        />
      ) : null}
      {confirmSummary ? (
        <Alert
          className="mb-3!"
          type={jobStatus === 'FAILED' ? 'error' : 'success'}
          showIcon
          title={`批量确认结束：成功 ${confirmSummary.succeeded ?? 0}，跳过 ${confirmSummary.skipped ?? 0}，失败 ${confirmSummary.failed ?? 0}。${confirmSummary.error_message ? ` ${confirmSummary.error_message}` : ''}`}
          description={
            [...(confirmSummary.details?.failures ?? []), ...(confirmSummary.details?.skips ?? [])]
              .slice(0, 8)
              .map((item) => `#${item.suggestion_id} ${item.reason}`)
              .join('；') || undefined
          }
        />
      ) : null}
      <Space className="mb-3" wrap>
        <Select value={confidence} options={CONFIDENCE_OPTIONS} style={{ width: 160 }} onChange={setConfidence} />
        <Can permission={PERMISSION_CODE.knowledgeUpdate}>
          <Space>
            <Button loading={runLabels.isPending} onClick={() => runLabels.mutate({ execute: false })}>
              查看调用估算
            </Button>
            <Popconfirm
              title="开始调用模型生成草稿？"
              description="每道待初标题会调用 1 次对话模型和 1 次问题向量。不会重新向量化文档，也不会把题目标成可评测。"
              onConfirm={() => runLabels.mutate({ execute: true })}
            >
              <Button type="primary" loading={runLabels.isPending || jobActive}>
                生成智能初标
              </Button>
            </Popconfirm>
            <Button loading={runLabels.isPending} onClick={() => runLabels.mutate({ execute: true, only_failed: true })}>
              重试失败题
            </Button>
            <Popconfirm
              title="重试没有切片的草稿？"
              description="只重跑没有相关切片的草稿。系统会按摘录对齐知识库里的真实切片，不会覆盖已确认标注。"
              onConfirm={() => runLabels.mutate({ execute: true, only_empty: true })}
            >
              <Button loading={runLabels.isPending} disabled={jobActive || liveEmptyDraftCount === 0}>
                重试无切片草稿
              </Button>
            </Popconfirm>
            <Popconfirm
              title="重新初标已驳回的题？"
              description="只重跑驳回的题目，不会覆盖已确认的正式标注。"
              onConfirm={() => runLabels.mutate({ execute: true, only_rejected: true })}
            >
              <Button loading={runLabels.isPending}>重新初标驳回题</Button>
            </Popconfirm>
            <Popconfirm
              title="确认全部高置信度草稿？"
              description="只确认 HIGH 草稿。MEDIUM/LOW 表示不确定，需要逐条查看证据后再确认。"
              onConfirm={() => confirmHigh.mutate()}
              disabled={jobActive || liveHighDraftCount === 0}
            >
              <Button loading={confirmHigh.isPending} disabled={jobActive || liveHighDraftCount === 0}>
                批量确认高置信度
              </Button>
            </Popconfirm>
          </Space>
        </Can>
      </Space>
      <AppTable
        rowKey="id"
        loading={suggestionsQuery.isLoading}
        columns={columns}
        dataSource={suggestionsQuery.data ?? []}
        pagination={false}
      />
      <Drawer title="审核建议标注" open={active != null} width={720} onClose={() => setActive(null)}>
        {active ? (
          <>
            {active.case_deleted ? (
              <Alert
                className="mb-3!"
                type="warning"
                showIcon
                title="这道题已从工作稿删除。确认和驳回都没有落点，可以查看证据后删除这条草稿。"
              />
            ) : null}
            <div className="mb-3 text-sm">
              <div className="font-medium">{active.question}</div>
              <div className="mt-2 text-slate-600">标准答案：{active.expected_answer || '（无）'}</div>
              <div className="mt-2">审核说明：{active.rationale || '无'}</div>
              <div className="mt-2 text-amber-700">风险：{active.risk || '无'}</div>
              {draftConfirmBlockReason(active) ? (
                <Alert className="mt-3!" type="warning" showIcon title={draftConfirmBlockReason(active) ?? ''} />
              ) : null}
              {active.reviewed_by ? (
                <div className="mt-2 text-slate-500">
                  审核人 #{active.reviewed_by}
                  {active.reviewed_at ? `，${active.reviewed_at}` : ''}
                  {active.review_note ? `，${active.review_note}` : ''}
                </div>
              ) : null}
            </div>
            <Form form={form} layout="vertical">
              <Form.Item name="confidence" label="置信度">
                <Select options={CONFIDENCE_OPTIONS.filter((item) => item.value)} />
              </Form.Item>
              <Form.Item name="verdict" label="结论">
                <Select options={VERDICT_OPTIONS} />
              </Form.Item>
              <Form.Item name="rationale" label="标注理由">
                <Input.TextArea rows={3} />
              </Form.Item>
              <Form.Item name="risk" label="风险说明">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.List name="items">
                {(fields, { add, remove }) => (
                  <div className="flex flex-col gap-2 mb-4">
                    {fields.map((field) => {
                      const current = form.getFieldValue(['items', field.name]) as { excerpt?: string; chunk_id?: number };
                      return (
                        <div key={field.key} className="rounded border border-slate-200 p-2">
                          <div className="mb-2 text-sm">
                            {current?.excerpt ? `Chunk #${current?.chunk_id} ${current.excerpt}` : '补充相关切片'}
                          </div>
                          <Space wrap>
                            <Form.Item {...field} name={[field.name, 'chunk_id']} label="切片 ID" rules={[{ required: true, message: '填写切片 ID' }]}>
                              <InputNumber min={1} />
                            </Form.Item>
                            <Form.Item {...field} name={[field.name, 'relevance']} label="相关性">
                              <InputNumber min={0} max={3} />
                            </Form.Item>
                            <Form.Item {...field} name={[field.name, 'reason']} label="依据">
                              <Input />
                            </Form.Item>
                            <Button type="link" danger onClick={() => remove(field.name)}>
                              删除
                            </Button>
                          </Space>
                        </div>
                      );
                    })}
                    <Button onClick={() => add({ relevance: 3, reason: '', excerpt: '' })}>添加切片</Button>
                  </div>
                )}
              </Form.List>
            </Form>
            {active.status === 'DRAFT' && !active.case_deleted ? (
              <Space>
                <Button
                  onClick={async () => {
                    const values = coerceRebuttalValues(active, await form.validateFields());
                    await updateEvalLabelSuggestion(active.id, values);
                    message.success('已保存草稿，题目仍待确认');
                    setActive(null);
                    invalidate();
                  }}
                >
                  保存修改
                </Button>
                <Button
                  type="primary"
                  onClick={async () => {
                    const values = coerceRebuttalValues(active, await form.validateFields());
                    await updateEvalLabelSuggestion(active.id, values);
                    const result = await confirmEvalLabelSuggestions(datasetId, {
                      suggestion_ids: [active.id],
                      only_high: false,
                    });
                    if (result.errors?.length) {
                      message.warning(result.errors[0]?.message ?? '没有确认');
                      invalidate();
                      return;
                    }
                    message.success('已确认并标为可评测');
                    setActive(null);
                    invalidate();
                  }}
                >
                  保存并确认
                </Button>
              </Space>
            ) : null}
          </>
        ) : null}
      </Drawer>
    </>
  );
}

import {
  knowledgeEvalLabelSuggestionStatusColor,
  knowledgeEvalLabelSuggestionStatusLabel,
  knowledgeEvalLabelSuggestionsQueryKey,
  PERMISSION_CODE,
  type KnowledgeEvalLabelSuggestion,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Drawer, Form, Input, InputNumber, Popconfirm, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import {
  confirmEvalLabelSuggestions,
  deleteEvalLabelSuggestion,
  fetchEvalLabelJob,
  fetchEvalLabelSuggestions,
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
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'QUEUED' || status === 'RUNNING' ? 2000 : false;
    },
  });
  const jobStatus = jobQuery.data?.status;
  const allSuggestions = allSuggestionsQuery.data ?? [];
  const liveDraftCount = allSuggestions.filter((item) => item.status === 'DRAFT' && !item.case_deleted).length;
  const liveFailedCount = allSuggestions.filter((item) => item.status === 'FAILED' && !item.case_deleted).length;
  const showJobSucceeded = jobStatus === 'SUCCEEDED' && liveDraftCount > 0;
  useEffect(() => {
    if (jobStatus !== 'SUCCEEDED' && jobStatus !== 'FAILED') return;
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-label-suggestions'] });
  }, [jobStatus, jobQuery.data?.id, jobQuery.data?.finished_at, queryClient, tenantId]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-label-suggestions'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-cases'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-dataset'] });
  };

  const runLabels = useMutation({
    mutationFn: (payload: { execute: boolean; rerun?: boolean; only_failed?: boolean; only_rejected?: boolean }) =>
      runEvalLabelSuggestions(datasetId, payload),
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
    mutationFn: () => {
      const liveHigh = (suggestionsQuery.data ?? [])
        .filter((item) => item.status === 'DRAFT' && item.confidence === 'HIGH' && !item.case_deleted)
        .map((item) => item.id);
      if (!liveHigh.length) {
        return Promise.resolve({ confirmed: 0, errors: [] as { suggestion_id: number; message: string }[] });
      }
      return confirmEvalLabelSuggestions(datasetId, { suggestion_ids: liveHigh, only_high: true });
    },
    onSuccess: (result) => {
      if (!result.confirmed && !result.errors.length) {
        message.info('没有可确认的高置信度草稿');
        return;
      }
      message.success(`已确认 ${result.confirmed} 道高置信度题`);
      if (result.errors.length) message.warning(result.errors.map((item) => item.message).join('；'));
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeEvalLabelSuggestion> = [
    { title: '问题', dataIndex: 'question', ellipsis: true },
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
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setActive(record);
              form.setFieldsValue({
                confidence: record.confidence,
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
              <Button
                type="link"
                size="small"
                onClick={() =>
                  confirmEvalLabelSuggestions(datasetId, { suggestion_ids: [record.id], only_high: false })
                    .then((result) => {
                      if (result.errors.length) {
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
        title="智能初标只生成草稿。提交后马上返回，页面每 2 秒刷新进度。确认后才会变成可评测。"
      />
      {jobStatus === 'QUEUED' || jobStatus === 'RUNNING' ? (
        <Alert
          className="mb-3!"
          type="info"
          showIcon
          title={`正在初标 ${jobQuery.data?.drafted ?? 0}/${jobQuery.data?.total ?? 0}，失败 ${jobQuery.data?.failed ?? 0}。`}
        />
      ) : null}
      {jobStatus === 'FAILED' ? (
        <Alert className="mb-3!" type="error" showIcon title={jobQuery.data?.error_message || '初标失败，可以重试失败题'} />
      ) : null}
      {showJobSucceeded ? (
        <Alert
          className="mb-3!"
          type="success"
          showIcon
          title={`初标结束：还有 ${liveDraftCount} 道草稿待确认${liveFailedCount ? `，失败 ${liveFailedCount} 道` : ''}。确认前还不是可评测。`}
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
              <Button type="primary" loading={runLabels.isPending || jobStatus === 'QUEUED' || jobStatus === 'RUNNING'}>
                生成智能初标
              </Button>
            </Popconfirm>
            <Button loading={runLabels.isPending} onClick={() => runLabels.mutate({ execute: true, only_failed: true })}>
              重试失败题
            </Button>
            <Popconfirm
              title="重新初标已驳回的题？"
              description="只重跑驳回的题目，不会覆盖已确认的正式标注。"
              onConfirm={() => runLabels.mutate({ execute: true, only_rejected: true })}
            >
              <Button loading={runLabels.isPending}>重新初标驳回题</Button>
            </Popconfirm>
            <Popconfirm title="确认全部高置信度草稿？" onConfirm={() => confirmHigh.mutate()}>
              <Button loading={confirmHigh.isPending}>批量确认高置信度</Button>
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
              <Form.Item name="rationale" label="标注理由">
                <Input.TextArea rows={3} />
              </Form.Item>
              <Form.Item name="risk" label="风险说明">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.List name="items">
                {(fields) => (
                  <div className="space-y-2">
                    {fields.map((field) => {
                      const current = form.getFieldValue(['items', field.name]) as { excerpt?: string; chunk_id?: number };
                      return (
                        <div key={field.key} className="rounded border border-slate-200 p-2">
                          <div className="mb-2 text-sm">Chunk #{current?.chunk_id} {current?.excerpt}</div>
                          <Space>
                            <Form.Item {...field} name={[field.name, 'chunk_id']} hidden>
                              <InputNumber />
                            </Form.Item>
                            <Form.Item {...field} name={[field.name, 'relevance']} label="相关性">
                              <InputNumber min={0} max={3} />
                            </Form.Item>
                            <Form.Item {...field} name={[field.name, 'reason']} label="依据">
                              <Input />
                            </Form.Item>
                          </Space>
                        </div>
                      );
                    })}
                  </div>
                )}
              </Form.List>
            </Form>
            {active.status === 'DRAFT' && !active.case_deleted ? (
              <Button
                type="primary"
                onClick={async () => {
                  const values = await form.validateFields();
                  await updateEvalLabelSuggestion(active.id, values);
                  message.success('已保存草稿，题目仍待确认');
                  setActive(null);
                  invalidate();
                }}
              >
                保存修改
              </Button>
            ) : null}
          </>
        ) : null}
      </Drawer>
    </>
  );
}

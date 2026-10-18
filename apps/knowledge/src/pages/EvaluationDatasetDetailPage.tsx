import {
  DEFAULT_PAGE_SIZE,
  knowledgeAnnotationStatusLabel,
  knowledgeChunksQueryKey,
  knowledgeConversationsQueryKey,
  knowledgeEvalCasesQueryKey,
  knowledgeEvalDatasetQueryKey,
  knowledgeQuestionTypeLabel,
  KNOWLEDGE_QUESTION_TYPE_LABEL,
  PERMISSION_CODE,
  type KnowledgeEvalCase,
  type KnowledgeEvalProbe,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchChunks } from '@/api/documents';
import { fetchConversations } from '@/api/rag';
import {
  createEvalCase,
  deleteEvalCase,
  fetchEvalCases,
  fetchEvalDataset,
  freezeEvalDataset,
  importEvalFromChat,
  refreshEvalStale,
  probeEvalCase,
  replaceEvalJudgments,
  updateEvalCase,
} from '@/api/evaluation';
import { ActionCell, AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';

const TYPE_OPTIONS = Object.entries(KNOWLEDGE_QUESTION_TYPE_LABEL).map(([value, label]) => ({ value, label }));

export function EvaluationDatasetDetailPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const datasetId = Number(useParams().id);
  const [status, setStatus] = useState<string | undefined>();
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [editing, setEditing] = useState<KnowledgeEvalCase | null>(null);
  const [creating, setCreating] = useState(false);
  const [probing, setProbing] = useState<KnowledgeEvalCase | null>(null);
  const [probeResult, setProbeResult] = useState<KnowledgeEvalProbe | null>(null);
  const [probeLoading, setProbeLoading] = useState(false);
  const [form] = Form.useForm();
  const [judgmentForm] = Form.useForm();

  useEffect(() => {
    setStatus(undefined);
    setKeyword('');
    setPage(1);
    setEditing(null);
  }, [tenantId, datasetId]);

  const datasetQuery = useQuery({
    queryKey: knowledgeEvalDatasetQueryKey(tenantId, datasetId),
    queryFn: ({ signal }) => fetchEvalDataset(datasetId, signal),
    enabled: tenantId != null && Number.isFinite(datasetId),
  });

  const casesQuery = useQuery({
    queryKey: knowledgeEvalCasesQueryKey(tenantId, datasetId, { status, q: keyword, page, pageSize }),
    queryFn: ({ signal }) => fetchEvalCases(datasetId, { status, q: keyword, page, pageSize }, signal),
    enabled: tenantId != null && Number.isFinite(datasetId),
  });

  const chunksQuery = useQuery({
    queryKey: knowledgeChunksQueryKey(tenantId, {
      knowledgeBaseId: datasetQuery.data?.knowledge_base_ids[0],
      enabled: true,
      page: 1,
      pageSize: 50,
    }),
    queryFn: ({ signal }) =>
      fetchChunks(
        {
          knowledgeBaseId: datasetQuery.data?.knowledge_base_ids[0],
          enabled: true,
          page: 1,
          pageSize: 50,
        },
        signal,
      ),
    enabled: tenantId != null && (datasetQuery.data?.knowledge_base_ids.length ?? 0) > 0,
  });

  const conversationsQuery = useQuery({
    queryKey: knowledgeConversationsQueryKey(tenantId, { page: 1, pageSize: 20 }),
    queryFn: ({ signal }) => fetchConversations({ page: 1, pageSize: 20 }, signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-cases'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-dataset'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-datasets'] });
  };

  const saveCase = useMutation({
    mutationFn: async (values: {
      question: string;
      expected_answer?: string;
      question_type?: string;
      difficulty?: number;
      tags?: string[];
      is_unanswerable?: boolean;
      judgments?: { chunk_id: number; relevance: number }[];
    }) => {
      const payload = {
        question: values.question.trim(),
        expected_answer: values.expected_answer,
        question_type: values.question_type,
        difficulty: values.difficulty,
        tags: values.tags,
        is_unanswerable: values.is_unanswerable,
      };
      const row = editing
        ? await updateEvalCase(editing.id, payload)
        : await createEvalCase(datasetId, payload);
      if (values.judgments) {
        return replaceEvalJudgments(row.id, values.judgments);
      }
      return row;
    },
    onSuccess: () => {
      message.success('已保存');
      setEditing(null);
      setCreating(false);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeEvalCase> = [
    { title: '问题', dataIndex: 'question', ellipsis: true },
    {
      title: '类型',
      dataIndex: 'question_type',
      width: 110,
      render: (value: string) => knowledgeQuestionTypeLabel(value),
    },
    {
      title: '状态',
      dataIndex: 'annotation_status',
      width: 100,
      render: (value: string) => <Tag>{knowledgeAnnotationStatusLabel(value)}</Tag>,
    },
    {
      title: '无答案',
      dataIndex: 'is_unanswerable',
      width: 80,
      render: (value: boolean) => (value ? <Tag color="purple">是</Tag> : '-'),
    },
    {
      title: '相关 Chunk',
      width: 120,
      render: (_, record) => {
        const stale = record.judgments.filter((item) => item.stale).length;
        return (
          <span>
            {record.judgments.length}
            {stale ? <Tag color="warning" className="ml-1">失效 {stale}</Tag> : null}
          </span>
        );
      },
    },
    {
      title: '复核',
      dataIndex: 'needs_human_review',
      width: 80,
      render: (value: boolean) => (value ? <Tag color="orange">待复核</Tag> : '-'),
    },
    {
      title: '操作',
      width: 220,
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => setProbing(record)}>
            单题评测
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setEditing(record);
              setCreating(false);
              form.setFieldsValue({
                question: record.question,
                expected_answer: record.expected_answer ?? undefined,
                question_type: record.question_type,
                difficulty: record.difficulty,
                tags: record.tags,
                is_unanswerable: record.is_unanswerable,
              });
              judgmentForm.setFieldsValue({
                judgments: record.judgments.map((item) => ({ chunk_id: item.chunk_id, relevance: item.relevance })),
              });
            }}
          >
            标注
          </Button>
          <Can permission={PERMISSION_CODE.knowledgeDelete}>
            <Popconfirm
              title="删除该问题？"
              onConfirm={() =>
                deleteEvalCase(record.id)
                  .then(() => {
                    message.success('已删除');
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
        </ActionCell>
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader
        title={datasetQuery.data?.name ?? '问题标注'}
        description="待标注 / 已标注 / 可评测必须分开。无答案题单独标记，不能当成缺少标注。Chunk 版本变化后的失效标注需重新确认。"
        extra={
          <Space>
            <Button onClick={() => navigate('/datasets')}>返回列表</Button>
            <Can permission={PERMISSION_CODE.knowledgeUpdate}>
              <Space>
                <Button onClick={() => refreshEvalStale(datasetId).then(() => { message.success('已刷新失效标注'); invalidate(); }).catch((error: Error) => message.error(error.message))}>
                  刷新失效标注
                </Button>
                <Button onClick={() => freezeEvalDataset(datasetId).then((row) => { message.success(`已冻结 v${row.version}`); invalidate(); }).catch((error: Error) => message.error(error.message))}>
                  冻结版本
                </Button>
                <Button
                  type="primary"
                  onClick={() => {
                    setCreating(true);
                    setEditing(null);
                    form.resetFields();
                    judgmentForm.resetFields();
                  }}
                >
                  新增问题
                </Button>
              </Space>
            </Can>
          </Space>
        }
      />
      <ListToolbar>
        <Space wrap>
          <Input.Search
            allowClear
            placeholder="搜索问题"
            onSearch={(value) => {
              setKeyword(value.trim());
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="标注状态"
            style={{ width: 140 }}
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={[
              { value: 'PENDING', label: '待标注' },
              { value: 'LABELED', label: '已标注' },
              { value: 'READY', label: '可评测' },
            ]}
          />
          <Can permission={PERMISSION_CODE.knowledgeUpdate}>
            <Select
              placeholder="从问答导入"
              style={{ width: 220 }}
              options={(conversationsQuery.data?.items ?? []).map((item) => ({ value: item.id, label: item.title }))}
              onSelect={(conversationId: number) => {
                void importEvalFromChat(datasetId, { conversation_id: conversationId, confirm: false })
                  .then((preview) => {
                    if (!preview.candidates.length) {
                      message.info('该会话没有可导入的用户问题');
                      return;
                    }
                    return importEvalFromChat(datasetId, { conversation_id: conversationId, confirm: true }).then((confirmed) => {
                      message.success(`已加入 ${confirmed.candidates.length} 条待标注问题`);
                      invalidate();
                    });
                  })
                  .catch((error: Error) => message.error(error.message));
              }}
            />
          </Can>
        </Space>
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="id"
          loading={casesQuery.isLoading}
          columns={columns}
          dataSource={casesQuery.data?.items ?? []}
          pagination={{
            current: page,
            pageSize,
            total: casesQuery.data?.total ?? 0,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage);
              setPageSize(nextSize);
            },
          }}
        />
      </ListTableArea>
      <Drawer
        title={editing ? '编辑问题与标注' : '新增问题'}
        open={creating || editing != null}
        width={640}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="question" label="问题" rules={[{ required: true, message: '请输入问题' }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="expected_answer" label="标准答案（无答案题可空）">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="question_type" label="类型" initialValue="FACTUAL">
            <Select options={TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="difficulty" label="难度" initialValue={2}>
            <InputNumber min={1} max={5} className="w-full" />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" />
          </Form.Item>
          <Form.Item name="is_unanswerable" label="无答案问题" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
        <Form form={judgmentForm} layout="vertical">
          <Form.List name="judgments">
            {(fields, { add, remove }) => (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm">相关 Chunk（相关性 0–3，可多个）</span>
                  <Button size="small" onClick={() => add({ relevance: 3 })}>
                    添加
                  </Button>
                </div>
                {fields.map((field) => (
                  <Space key={field.key} align="start" className="w-full">
                    <Form.Item {...field} name={[field.name, 'chunk_id']} rules={[{ required: true, message: '选择切片' }]}>
                      <Select
                        showSearch
                        optionFilterProp="label"
                        style={{ width: 360 }}
                        options={(chunksQuery.data?.items ?? []).map((item) => ({
                          value: item.id,
                          label: `#${item.id} ${item.content.slice(0, 40)}`,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'relevance']} rules={[{ required: true }]}>
                      <InputNumber min={0} max={3} />
                    </Form.Item>
                    <Button onClick={() => remove(field.name)}>删除</Button>
                  </Space>
                ))}
              </div>
            )}
          </Form.List>
        </Form>
        {editing?.judgments.some((item) => item.stale) ? (
          <div className="mb-3 text-sm text-amber-600">存在失效标注，保存前请重新确认 Chunk，不会悄悄当作有效结果。</div>
        ) : null}
        <Button
          type="primary"
          loading={saveCase.isPending}
          onClick={async () => {
            const values = await form.validateFields();
            const judgments = (judgmentForm.getFieldValue('judgments') ?? []) as { chunk_id: number; relevance: number }[];
            saveCase.mutate({ ...values, judgments });
          }}
        >
          保存
        </Button>
      </Drawer>
      <Modal
        title={probing ? `单题评测：${probing.question.slice(0, 40)}` : '单题评测'}
        open={probing != null}
        onCancel={() => {
          setProbing(null);
          setProbeResult(null);
        }}
        footer={null}
        width={720}
      >
        <Space className="mb-3" wrap>
          <Button
            type="primary"
            loading={probeLoading}
            onClick={() => {
              if (!probing) return;
              setProbeLoading(true);
              probeEvalCase(probing.id, { strategy: 'HYBRID', top_k: 8, rerank: false, generate: false })
                .then((row) => setProbeResult(row))
                .catch((error: Error) => message.error(error.message))
                .finally(() => setProbeLoading(false));
            }}
          >
            运行 HYBRID
          </Button>
          <span className="text-slate-500">只跑检索指标，默认不调用生成模型。可在实验页批量对比策略。</span>
        </Space>
        {probeResult ? (
          <pre className="max-h-96 overflow-auto rounded bg-slate-50 p-3 text-xs">
            {JSON.stringify(
              {
                strategy: probeResult.strategy,
                latency_ms: probeResult.latency_ms,
                stages: probeResult.stages,
                retrieval_metrics: probeResult.retrieval_metrics,
                retrieved: probeResult.retrieved,
                answer: probeResult.answer,
                usage: probeResult.usage,
                needs_human_review: probeResult.needs_human_review,
              },
              null,
              2,
            )}
          </pre>
        ) : null}
      </Modal>
    </ListPageContainer>
  );
}

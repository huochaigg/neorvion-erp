import {
  ApiError,
  DEFAULT_PAGE_SIZE,
  KNOWLEDGE_CHUNK_STRATEGY,
  formatFileSize,
  knowledgeChunksQueryKey,
  knowledgeDocumentQueryKey,
  knowledgeDocumentStatusLabel,
  knowledgeRevisionsQueryKey,
  knowledgeProcessingTasksQueryKey,
  knowledgeTaskStatusLabel,
  knowledgeTaskTypeLabel,
  PERMISSION_CODE,
  type KnowledgeChunk,
  type KnowledgeRevision,
  type KnowledgeTask,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Result,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
} from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  downloadDocument,
  fetchChunks,
  fetchDocument,
  fetchProcessingTasks,
  requestChunk,
  requestParse,
  retryProcessingTask,
  updateChunk,
} from '@/api/documents';
import { fetchRevisions, replaceDocument, restoreRevision } from '@/api/ops';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

export function DocumentDetailPage() {
  const { id, docId } = useParams();
  const knowledgeBaseId = Number(id);
  const documentId = Number(docId);
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [chunkOpen, setChunkOpen] = useState(false);
  const [editing, setEditing] = useState<KnowledgeChunk | null>(null);
  const [chunkPage, setChunkPage] = useState(1);
  const [chunkPageSize, setChunkPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [form] = Form.useForm<{ strategy: string; chunk_size: number; chunk_overlap: number }>();
  const [editForm] = Form.useForm<{ content: string }>();

  const detailQuery = useQuery({
    queryKey: knowledgeDocumentQueryKey(tenantId, Number.isFinite(documentId) ? documentId : null),
    queryFn: ({ signal }) => fetchDocument(documentId, signal),
    enabled: tenantId != null && Number.isFinite(documentId),
    refetchInterval: (current) => {
      const status = current.state.data?.status;
      return status === 'PENDING' || status === 'PROCESSING' ? 2500 : false;
    },
  });

  const chunkQuery = useQuery({
    queryKey: knowledgeChunksQueryKey(tenantId, { documentId, page: chunkPage, pageSize: chunkPageSize }),
    queryFn: ({ signal }) => fetchChunks({ documentId, page: chunkPage, pageSize: chunkPageSize }, signal),
    enabled: tenantId != null && Number.isFinite(documentId),
    refetchInterval: () => {
      const status = detailQuery.data?.status;
      return status === 'PENDING' || status === 'PROCESSING' ? 2500 : false;
    },
  });

  const revisionQuery = useQuery({
    queryKey: knowledgeRevisionsQueryKey(tenantId, Number.isFinite(documentId) ? documentId : null),
    queryFn: ({ signal }) => fetchRevisions(documentId, signal),
    enabled: tenantId != null && Number.isFinite(documentId),
  });

  const taskQuery = useQuery({
    queryKey: knowledgeProcessingTasksQueryKey(tenantId, { documentId, page: 1, pageSize: 10 }),
    queryFn: ({ signal }) => fetchProcessingTasks({ documentId, page: 1, pageSize: 10 }, signal),
    enabled: tenantId != null && Number.isFinite(documentId),
    refetchInterval: (current) => {
      const items = current.state.data?.items ?? [];
      return items.some((item) => item.status === 'QUEUED' || item.status === 'RUNNING') ? 2500 : false;
    },
  });

  useEffect(() => {
    setEditing(null);
    setChunkOpen(false);
    setChunkPage(1);
  }, [tenantId, documentId]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-document'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-chunks'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-processing-tasks'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-documents'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-revisions'] });
  };

  const parseMutation = useMutation({
    mutationFn: () => requestParse(documentId),
    onSuccess: () => {
      message.success('已排队重新解析');
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const chunkMutation = useMutation({
    mutationFn: requestChunk.bind(null, documentId),
    onSuccess: () => {
      message.success('已排队重新切片');
      setChunkOpen(false);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const retryMutation = useMutation({
    mutationFn: retryProcessingTask,
    onSuccess: () => {
      message.success('已重新排队');
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const saveChunkMutation = useMutation({
    mutationFn: ({ id: chunkId, content }: { id: number; content: string }) => updateChunk(chunkId, { content }),
    onSuccess: () => {
      message.success('切片已保存');
      setEditing(null);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id: chunkId, enabled }: { id: number; enabled: boolean }) => updateChunk(chunkId, { enabled }),
    onSuccess: () => invalidate(),
    onError: (error: Error) => message.error(error.message),
  });

  if (!Number.isFinite(documentId) || !Number.isFinite(knowledgeBaseId)) {
    return <Result status="404" title="文档不存在" extra={<Button onClick={() => navigate('/bases')}>返回</Button>} />;
  }
  if (detailQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (detailQuery.isError) {
    const error = detailQuery.error;
    const missing = error instanceof ApiError && error.status === 404;
    return (
      <Result
        status={missing ? '404' : 'error'}
        title={missing ? '文档不存在或不可访问' : '加载失败'}
        extra={<Button onClick={() => navigate(`/bases/${knowledgeBaseId}`)}>返回知识库</Button>}
      />
    );
  }
  const doc = detailQuery.data;
  if (!doc) {
    return <Empty />;
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <PageHeader
        title={doc.filename}
        description="解析预览、切片与任务。切片长度单位为字符，不是 Token。"
        extra={
          <Space>
            <Button onClick={() => navigate(`/bases/${knowledgeBaseId}`)}>返回知识库</Button>
            <Can permission={PERMISSION_CODE.knowledgeRead}>
              <Button onClick={() => void downloadDocument(doc.id, doc.filename)}>下载原文件</Button>
            </Can>
            <Can permission={PERMISSION_CODE.knowledgeUpdate}>
              <Button
                onClick={() => {
                  const input = document.createElement('input');
                  input.type = 'file';
                  input.onchange = () => {
                    const file = input.files?.[0];
                    if (!file) return;
                    replaceDocument(documentId, file, '页面更新')
                      .then(() => {
                        message.success('已排队解析新版本，旧索引在发布前仍可用');
                        invalidate();
                      })
                      .catch((error: Error) => message.error(error.message));
                  };
                  input.click();
                }}
              >
                更新文件
              </Button>
              <Button loading={parseMutation.isPending} onClick={() => parseMutation.mutate()}>
                重新解析
              </Button>
              <Button type="primary" onClick={() => setChunkOpen(true)}>
                重新切片
              </Button>
            </Can>
          </Space>
        }
      />
      {doc.warning_message ? <Alert className="mb-3" type="warning" showIcon message={doc.warning_message} /> : null}
      {doc.error_message ? <Alert className="mb-3" type="error" showIcon message={doc.error_message} /> : null}
      <Card className="mb-4">
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="状态">
            <Tag>{knowledgeDocumentStatusLabel(doc.status)}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="大小">{formatFileSize(doc.file_size)}</Descriptions.Item>
          <Descriptions.Item label="SHA256" span={2}>
            {doc.sha256 || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="抽取字符数">{doc.extracted_char_count}</Descriptions.Item>
          <Descriptions.Item label="切片版本">{doc.active_chunk_version}</Descriptions.Item>
          <Descriptions.Item label="切片策略">{doc.chunk_strategy || '-'}</Descriptions.Item>
          <Descriptions.Item label="长度 / 重叠">
            {doc.chunk_size ?? '-'} / {doc.chunk_overlap ?? '-'}（{doc.chunk_unit}）
          </Descriptions.Item>
          <Descriptions.Item label="上传时间">{formatDateTime(doc.created_at)}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card className="mb-4" title="版本历史">
        <Table<KnowledgeRevision>
          rowKey="id"
          size="small"
          loading={revisionQuery.isLoading}
          dataSource={revisionQuery.data?.items ?? []}
          pagination={false}
          locale={{ emptyText: '尚无历史版本。更新文件后会保留快照。' }}
          columns={[
            { title: '版本', dataIndex: 'revision', width: 70 },
            { title: '文件名', dataIndex: 'filename' },
            { title: '说明', dataIndex: 'note', ellipsis: true, render: (value: string | null) => value || '-' },
            { title: '时间', dataIndex: 'created_at', width: 180, render: (value: string) => formatDateTime(value) },
            {
              title: '',
              width: 90,
              render: (_, record) => (
                <Can permission={PERMISSION_CODE.knowledgeUpdate}>
                  <Button
                    type="link"
                    size="small"
                    onClick={() =>
                      restoreRevision(documentId, record.id)
                        .then(() => {
                          message.success('已排队恢复并重新解析');
                          invalidate();
                        })
                        .catch((error: Error) => message.error(error.message))
                    }
                  >
                    恢复
                  </Button>
                </Can>
              ),
            },
          ]}
        />
      </Card>
      <Card className="mb-4" title="解析预览">
        {doc.extracted_preview ? (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-sm text-slate-700">{doc.extracted_preview}</pre>
        ) : (
          <Empty description="暂无抽取文本" />
        )}
      </Card>
      <Card className="mb-4" title="切片">
        <Table<KnowledgeChunk>
          rowKey="id"
          size="small"
          loading={chunkQuery.isLoading}
          dataSource={chunkQuery.data?.items ?? []}
          pagination={{
            current: chunkPage,
            pageSize: chunkPageSize,
            total: chunkQuery.data?.total ?? 0,
            onChange: (nextPage, nextSize) => {
              setChunkPage(nextPage);
              setChunkPageSize(nextSize);
            },
          }}
          locale={{ emptyText: '暂无切片' }}
          columns={[
            { title: '#', dataIndex: 'chunk_index', width: 60 },
            { title: '字符', dataIndex: 'char_count', width: 70 },
            { title: '页', dataIndex: 'page_no', width: 60, render: (value: number | null) => value ?? '-' },
            { title: '内容', dataIndex: 'content', ellipsis: true },
            {
              title: '启用',
              dataIndex: 'enabled',
              width: 80,
              render: (value: boolean, record) => (
                <Can permission={PERMISSION_CODE.knowledgeUpdate} fallback="disable">
                  <Switch checked={value} onChange={(enabled) => toggleMutation.mutate({ id: record.id, enabled })} />
                </Can>
              ),
            },
            {
              title: '',
              key: 'edit',
              width: 80,
              render: (_, record) => (
                <Can permission={PERMISSION_CODE.knowledgeUpdate}>
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      setEditing(record);
                      editForm.setFieldsValue({ content: record.content });
                    }}
                  >
                    编辑
                  </Button>
                </Can>
              ),
            },
          ]}
        />
      </Card>
      <Card title="处理任务">
        <Table<KnowledgeTask>
          rowKey="id"
          size="small"
          loading={taskQuery.isLoading}
          dataSource={taskQuery.data?.items ?? []}
          pagination={false}
          locale={{ emptyText: '暂无任务' }}
          columns={[
            { title: '类型', dataIndex: 'task_type', render: (value: string) => knowledgeTaskTypeLabel(value) },
            {
              title: '状态',
              dataIndex: 'status',
              render: (value: string) => <Tag>{knowledgeTaskStatusLabel(value)}</Tag>,
            },
            { title: '进度', dataIndex: 'progress', render: (value: number) => `${value}%` },
            { title: '原因', dataIndex: 'error_message', ellipsis: true, render: (value: string | null) => value || '-' },
            {
              title: '',
              key: 'retry',
              render: (_, record) =>
                record.status === 'FAILED' ? (
                  <Can permission={PERMISSION_CODE.knowledgeUpdate}>
                    <Button type="link" size="small" onClick={() => retryMutation.mutate(record.id)}>
                      重试
                    </Button>
                  </Can>
                ) : null,
            },
          ]}
        />
      </Card>
      <Modal
        title="重新切片"
        open={chunkOpen}
        onCancel={() => setChunkOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={chunkMutation.isPending}
        okText="确认重新切片"
      >
        <p className="mb-3 text-slate-500">
          新切片写入完成后才会替换旧切片。若任务失败，旧切片会保留。长度单位是字符。
        </p>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            strategy: doc.chunk_strategy || KNOWLEDGE_CHUNK_STRATEGY.recursive,
            chunk_size: doc.chunk_size || 800,
            chunk_overlap: doc.chunk_overlap || 120,
          }}
          onFinish={(values) => chunkMutation.mutate(values)}
        >
          <Form.Item name="strategy" label="策略" rules={[{ required: true }]}>
            <Select
              options={[
                { value: KNOWLEDGE_CHUNK_STRATEGY.recursive, label: '递归切分（推荐，按段落与中文标点）' },
                { value: KNOWLEDGE_CHUNK_STRATEGY.fixed, label: '固定长度' },
              ]}
            />
          </Form.Item>
          <Form.Item name="chunk_size" label="切片长度（字符）" rules={[{ required: true }]}>
            <InputNumber min={100} max={8000} className="w-full" />
          </Form.Item>
          <Form.Item name="chunk_overlap" label="重叠（字符，须小于长度）" rules={[{ required: true }]}>
            <InputNumber min={0} max={7999} className="w-full" />
          </Form.Item>
        </Form>
      </Modal>
      <Drawer title="编辑切片" open={editing != null} onClose={() => setEditing(null)} width={480}>
        <Form form={editForm} layout="vertical" onFinish={(values) => editing && saveChunkMutation.mutate({ id: editing.id, content: values.content })}>
          <Form.Item name="content" label="正文" rules={[{ required: true, message: '请输入切片内容' }]}>
            <Input.TextArea rows={12} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saveChunkMutation.isPending}>
            保存
          </Button>
        </Form>
      </Drawer>
    </div>
  );
}

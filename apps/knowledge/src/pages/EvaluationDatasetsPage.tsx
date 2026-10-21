import {
  DEFAULT_PAGE_SIZE,
  knowledgeAnnotationStatusColor,
  knowledgeAnnotationStatusLabel,
  knowledgeBasesQueryKey,
  knowledgeEvalDatasetsQueryKey,
  PERMISSION_CODE,
  type KnowledgeEvalDataset,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Form, Input, Popconfirm, Select, Space, Tag, Upload } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchKnowledgeBases } from '@/api/knowledge-bases';
import {
  copyEvalDataset,
  createEvalDataset,
  deleteEvalDataset,
  exportEvalCases,
  fetchEvalDatasets,
  importEvalCases,
  updateEvalDataset,
} from '@/api/evaluation';
import { ActionCell, AppTable, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

type EditorState = { type: 'create' } | { type: 'edit'; dataset: KnowledgeEvalDataset };

export function EvaluationDatasetsPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [form] = Form.useForm<{ name: string; description?: string; knowledge_base_ids?: number[] }>();

  useEffect(() => {
    setEditor(null);
    setQ('');
    setKeyword('');
    setPage(1);
  }, [tenantId]);

  const listQuery = useQuery({
    queryKey: knowledgeEvalDatasetsQueryKey(tenantId, { q: keyword, page, pageSize }),
    queryFn: ({ signal }) => fetchEvalDatasets({ q: keyword, page, pageSize }, signal),
    enabled: tenantId != null,
  });

  const basesQuery = useQuery({
    queryKey: knowledgeBasesQueryKey(tenantId, { page: 1, pageSize: 100, status: 'ACTIVE' }),
    queryFn: ({ signal }) => fetchKnowledgeBases({ page: 1, pageSize: 100, status: 'ACTIVE' }, signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-datasets'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-dataset'] });
  };

  const saveMutation = useMutation({
    mutationFn: async (values: { name: string; description?: string; knowledge_base_ids?: number[] }) => {
      if (editor?.type === 'edit') {
        return updateEvalDataset(editor.dataset.id, {
          name: values.name.trim(),
          description: values.description?.trim() || null,
          knowledge_base_ids: values.knowledge_base_ids,
        });
      }
      return createEvalDataset({
        name: values.name.trim(),
        description: values.description?.trim(),
        knowledge_base_ids: values.knowledge_base_ids,
      });
    },
    onSuccess: () => {
      message.success(editor?.type === 'edit' ? '已保存' : '已创建');
      setEditor(null);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeEvalDataset> = [
    { title: '名称', dataIndex: 'name', ellipsis: true, render: (value: string) => <EllipsisCell value={value} /> },
    { title: '版本', dataIndex: 'current_version', width: 70 },
    {
      title: '标注',
      width: 220,
      render: (_, record) => (
        <Space size={4} wrap>
          <Tag color={knowledgeAnnotationStatusColor('PENDING')}>
            {knowledgeAnnotationStatusLabel('PENDING')} {record.pending_count}
          </Tag>
          <Tag color={knowledgeAnnotationStatusColor('LABELED')}>
            {knowledgeAnnotationStatusLabel('LABELED')} {record.labeled_count}
          </Tag>
          <Tag color={knowledgeAnnotationStatusColor('READY')}>
            {knowledgeAnnotationStatusLabel('READY')} {record.ready_count}
          </Tag>
        </Space>
      ),
    },
    { title: '题目', dataIndex: 'total_cases', width: 70 },
    { title: '更新时间', dataIndex: 'updated_at', width: 170, render: (value: string) => formatDateTime(value) },
    {
      title: '操作',
      width: 280,
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => navigate(`/datasets/${record.id}`)}>
            标注
          </Button>
          <Can permission={PERMISSION_CODE.knowledgeUpdate}>
            <Button
              type="link"
              size="small"
              onClick={() => {
                setEditor({ type: 'edit', dataset: record });
                form.setFieldsValue({
                  name: record.name,
                  description: record.description ?? undefined,
                  knowledge_base_ids: record.knowledge_base_ids,
                });
              }}
            >
              编辑
            </Button>
          </Can>
          <Can permission={PERMISSION_CODE.knowledgeCreate}>
            <Button type="link" size="small" onClick={() => copyEvalDataset(record.id).then(() => { message.success('已复制'); invalidate(); }).catch((error: Error) => message.error(error.message))}>
              复制
            </Button>
          </Can>
          <Can permission={PERMISSION_CODE.knowledgeUpdate}>
            <Upload
              showUploadList={false}
              accept=".csv,.jsonl,.json,.xlsx"
              beforeUpload={async (file) => {
                try {
                  const result = await importEvalCases(record.id, file as File);
                  message.success(`导入成功 ${result.succeeded}，失败 ${result.failed}`);
                  invalidate();
                } catch (error) {
                  message.error(error instanceof Error ? error.message : '导入失败');
                }
                return false;
              }}
            >
              <Button type="link" size="small">
                导入
              </Button>
            </Upload>
          </Can>
          <Button type="link" size="small" onClick={() => void exportEvalCases(record.id, `${record.name}.csv`)}>
            导出
          </Button>
          <Can permission={PERMISSION_CODE.knowledgeDelete}>
            <Popconfirm title="删除该数据集？" onConfirm={() => deleteEvalDataset(record.id).then(() => { message.success('已删除'); invalidate(); }).catch((error: Error) => message.error(error.message))}>
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
        title="评测数据集"
        description="管理标准问题、标注状态与知识库范围。未标注相关 Chunk 的问题不能进入有监督检索指标。"
        extra={
          <Can permission={PERMISSION_CODE.knowledgeCreate}>
            <Button
              type="primary"
              onClick={() => {
                setEditor({ type: 'create' });
                form.resetFields();
              }}
            >
              新建数据集
            </Button>
          </Can>
        }
      />
      <ListToolbar>
        <Space>
          <Input.Search
            allowClear
            placeholder="搜索名称"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            onSearch={(value) => {
              setKeyword(value.trim());
              setPage(1);
            }}
          />
        </Space>
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="id"
          loading={listQuery.isLoading}
          columns={columns}
          dataSource={listQuery.data?.items ?? []}
          pagination={{
            current: page,
            pageSize,
            total: listQuery.data?.total ?? 0,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage);
              setPageSize(nextSize);
            },
          }}
        />
      </ListTableArea>
      <Drawer
        title={editor?.type === 'edit' ? '编辑数据集' : '新建数据集'}
        open={editor != null}
        onClose={() => setEditor(null)}
        width={480}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(values) => saveMutation.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="knowledge_base_ids" label="关联知识库">
            <Select
              mode="multiple"
              allowClear
              options={(basesQuery.data?.items ?? []).map((item) => ({ value: item.id, label: item.name }))}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            保存
          </Button>
        </Form>
      </Drawer>
    </ListPageContainer>
  );
}

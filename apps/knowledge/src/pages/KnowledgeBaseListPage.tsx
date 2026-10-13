import {
  ApiError,
  DEFAULT_PAGE_SIZE,
  KNOWLEDGE_BASE_STATUS,
  knowledgeBasesQueryKey,
  knowledgeBaseStatusLabel,
  PERMISSION_CODE,
  type KnowledgeBase,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Form, Input, Popconfirm, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  fetchKnowledgeBases,
  updateKnowledgeBase,
} from '@/api/knowledge-bases';
import { ActionCell, AppTable, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

type EditorState =
  | { type: 'create' }
  | { type: 'edit'; knowledgeBase: KnowledgeBase };

interface KnowledgeFormValues {
  name: string;
  description?: string;
  status?: string;
}

export function KnowledgeBaseListPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [form] = Form.useForm<KnowledgeFormValues>();

  useEffect(() => {
    setEditor(null);
    setQ('');
    setKeyword('');
    setStatus(undefined);
    setPage(1);
  }, [tenantId]);

  const listQuery = useQuery({
    queryKey: knowledgeBasesQueryKey(tenantId, { q: keyword, status, page, pageSize }),
    queryFn: ({ signal }) => fetchKnowledgeBases({ q: keyword, status, page, pageSize }, signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-bases'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-base'] });
  };

  const saveMutation = useMutation({
    mutationFn: async (values: KnowledgeFormValues) => {
      if (editor?.type === 'edit') {
        return updateKnowledgeBase(editor.knowledgeBase.id, {
          name: values.name.trim(),
          description: values.description?.trim() || null,
          status: values.status,
        });
      }
      return createKnowledgeBase({
        name: values.name.trim(),
        description: values.description?.trim() || null,
      });
    },
    onSuccess: () => {
      message.success(editor?.type === 'edit' ? '知识库已保存' : '知识库已创建');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '保存失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteKnowledgeBase,
    onSuccess: () => {
      message.success('已删除');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '删除失败');
    },
  });

  const openEditor = (next: EditorState) => {
    setEditor(next);
    if (next.type === 'create') {
      form.resetFields();
      return;
    }
    form.setFieldsValue({
      name: next.knowledgeBase.name,
      description: next.knowledgeBase.description ?? '',
      status: next.knowledgeBase.status,
    });
  };

  const columns: ColumnsType<KnowledgeBase> = [
    {
      title: '名称',
      dataIndex: 'name',
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '描述',
      dataIndex: 'description',
      render: (value: string | null) => <EllipsisCell value={value} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={value === KNOWLEDGE_BASE_STATUS.active ? 'success' : 'default'}>
          {knowledgeBaseStatusLabel(value)}
        </Tag>
      ),
    },
    {
      title: '文档数',
      dataIndex: 'document_count',
      width: 88,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => navigate(`/bases/${record.id}`)}>
            详情
          </Button>
          <Can permission={PERMISSION_CODE.knowledgeUpdate}>
            <Button type="link" size="small" onClick={() => openEditor({ type: 'edit', knowledgeBase: record })}>
              编辑
            </Button>
          </Can>
          <Can permission={PERMISSION_CODE.knowledgeDelete}>
            <Popconfirm
              title="确认删除该知识库？"
              description="删除后将清理下属文档文件与切片，任务记录保留。"
              okText="删除"
              cancelText="取消"
              onConfirm={() => deleteMutation.mutate(record.id)}
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
        title="AI 知识库"
        description="按当前企业隔离管理知识库、文档上传与切片。"
        extra={
          <Can permission={PERMISSION_CODE.knowledgeCreate}>
            <Button type="primary" onClick={() => openEditor({ type: 'create' })}>
              新建知识库
            </Button>
          </Can>
        }
      />
      <ListToolbar>
        <Space wrap>
          <Input.Search
            allowClear
            placeholder="按名称搜索"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            onSearch={(value) => {
              setKeyword(value.trim());
              setPage(1);
            }}
            style={{ width: 240 }}
          />
          <Select
            allowClear
            placeholder="状态"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            style={{ width: 140 }}
            options={[
              { value: KNOWLEDGE_BASE_STATUS.active, label: '启用' },
              { value: KNOWLEDGE_BASE_STATUS.disabled, label: '禁用' },
            ]}
          />
        </Space>
      </ListToolbar>
      <ListTableArea>
        <AppTable<KnowledgeBase>
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
          locale={{ emptyText: listQuery.isError ? '加载失败，请稍后重试' : '暂无知识库' }}
        />
      </ListTableArea>
      <Drawer
        title={editor?.type === 'edit' ? '编辑知识库' : '新建知识库'}
        open={editor != null}
        onClose={() => setEditor(null)}
        destroyOnHidden
        extra={
          <Button type="primary" loading={saveMutation.isPending} onClick={() => form.submit()}>
            保存
          </Button>
        }
      >
        <Form form={form} layout="vertical" onFinish={(values) => saveMutation.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入知识库名称' }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={4} maxLength={2000} />
          </Form.Item>
          {editor?.type === 'edit' ? (
            <Form.Item name="status" label="状态" rules={[{ required: true, message: '请选择状态' }]}>
              <Select
                options={[
                  { value: KNOWLEDGE_BASE_STATUS.active, label: '启用' },
                  { value: KNOWLEDGE_BASE_STATUS.disabled, label: '禁用' },
                ]}
              />
            </Form.Item>
          ) : null}
        </Form>
      </Drawer>
    </ListPageContainer>
  );
}

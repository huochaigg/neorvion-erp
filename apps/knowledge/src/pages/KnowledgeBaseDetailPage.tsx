import {
  ApiError,
  DEFAULT_PAGE_SIZE,
  KNOWLEDGE_BASE_STATUS,
  KNOWLEDGE_DOCUMENT_STATUS,
  formatFileSize,
  knowledgeBaseQueryKey,
  knowledgeBaseStatusLabel,
  knowledgeChunksQueryKey,
  knowledgeDocumentStatusLabel,
  knowledgeDocumentsQueryKey,
  PERMISSION_CODE,
  type KnowledgeChunk,
  type KnowledgeDocument,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Descriptions, Empty, Input, Popconfirm, Result, Select, Space, Spin, Switch, Tabs, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { deleteDocument, fetchChunks, fetchDocuments, updateChunk } from '@/api/documents';
import { fetchKnowledgeBase } from '@/api/knowledge-bases';
import { ActionCell, AppTable, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { UploadDocumentsDrawer } from '@/components/UploadDocumentsDrawer';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

export function KnowledgeBaseDetailPage() {
  const { id } = useParams();
  const knowledgeBaseId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [uploadOpen, setUploadOpen] = useState(false);

  const detailQuery = useQuery({
    queryKey: knowledgeBaseQueryKey(tenantId, Number.isFinite(knowledgeBaseId) ? knowledgeBaseId : null),
    queryFn: ({ signal }) => fetchKnowledgeBase(knowledgeBaseId, signal),
    enabled: tenantId != null && Number.isFinite(knowledgeBaseId),
  });

  if (!Number.isFinite(knowledgeBaseId)) {
    return <Result status="404" title="知识库不存在" extra={<Button onClick={() => navigate('/bases')}>返回列表</Button>} />;
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
    const forbidden = error instanceof ApiError && error.status === 403;
    const missing = error instanceof ApiError && error.status === 404;
    return (
      <Result
        status={forbidden ? '403' : missing ? '404' : 'error'}
        title={forbidden ? '无权限' : missing ? '知识库不存在或不可访问' : '加载失败'}
        extra={<Button onClick={() => navigate('/bases')}>返回列表</Button>}
      />
    );
  }
  const item = detailQuery.data;
  if (!item) {
    return <Empty description="暂无数据" />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PageHeader
        title={item.name}
        description={item.description || '知识库文档、解析预览与切片管理'}
        extra={
          <Space>
            <Button onClick={() => navigate('/bases')}>返回列表</Button>
            <Can permission={PERMISSION_CODE.knowledgeCreate}>
              <Button type="primary" onClick={() => setUploadOpen(true)}>
                上传文档
              </Button>
            </Can>
          </Space>
        }
      />
      <Tabs
        className="min-h-0 flex-1 overflow-hidden [&_.ant-tabs-content-holder]:min-h-0 [&_.ant-tabs-content]:h-full [&_.ant-tabs-tabpane]:h-full"
        items={[
          {
            key: 'overview',
            label: '概览',
            children: (
              <Card>
                <Descriptions column={2} bordered size="small">
                  <Descriptions.Item label="状态">
                    <Tag color={item.status === KNOWLEDGE_BASE_STATUS.active ? 'success' : 'default'}>
                      {knowledgeBaseStatusLabel(item.status)}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="文档数量">{item.document_count}</Descriptions.Item>
                  <Descriptions.Item label="创建时间">{formatDateTime(item.created_at)}</Descriptions.Item>
                  <Descriptions.Item label="更新时间">{formatDateTime(item.updated_at)}</Descriptions.Item>
                </Descriptions>
              </Card>
            ),
          },
          {
            key: 'documents',
            label: '文档',
            children: <DocumentTable knowledgeBaseId={knowledgeBaseId} />,
          },
          {
            key: 'chunks',
            label: '切片',
            children: <ChunkTable knowledgeBaseId={knowledgeBaseId} />,
          },
        ]}
      />
      <UploadDocumentsDrawer
        knowledgeBaseId={knowledgeBaseId}
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onFinished={() => {
          void detailQuery.refetch();
          void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-documents'] });
          void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-chunks'] });
          void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-overview'] });
        }}
      />
    </div>
  );
}

function DocumentTable({ knowledgeBaseId }: { knowledgeBaseId: number }) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setQ('');
    setKeyword('');
    setStatus(undefined);
    setPage(1);
  }, [tenantId, knowledgeBaseId]);

  const listQuery = useQuery({
    queryKey: knowledgeDocumentsQueryKey(tenantId, { knowledgeBaseId, q: keyword, status, page, pageSize }),
    queryFn: ({ signal }) =>
      fetchDocuments({ knowledgeBaseId, q: keyword, status, page, pageSize }, signal),
    enabled: tenantId != null,
    refetchInterval: (current) => {
      const items = current.state.data?.items ?? [];
      return items.some((item) => item.status === 'PENDING' || item.status === 'PROCESSING') ? 2500 : false;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      message.success('已删除');
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-documents'] });
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-base'] });
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeDocument> = [
    { title: '文件名', dataIndex: 'filename', render: (value: string) => <EllipsisCell value={value} /> },
    { title: '大小', dataIndex: 'file_size', width: 100, render: (value: number) => formatFileSize(value) },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <Tag>{knowledgeDocumentStatusLabel(value)}</Tag>,
    },
    { title: '切片版本', dataIndex: 'active_chunk_version', width: 90 },
    { title: '失败原因', dataIndex: 'error_message', ellipsis: true, render: (value: string | null) => value || '-' },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => navigate(`/bases/${knowledgeBaseId}/documents/${record.id}`)}>
            详情
          </Button>
          <Can permission={PERMISSION_CODE.knowledgeDelete}>
            <Popconfirm title="删除后将清理原文件和切片，确认？" onConfirm={() => deleteMutation.mutate(record.id)}>
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
    <div className="flex h-full min-h-0 flex-col">
      <Space wrap className="mb-3">
        <Input.Search
          allowClear
          placeholder="按文件名搜索"
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
          options={Object.values(KNOWLEDGE_DOCUMENT_STATUS).map((value) => ({
            value,
            label: knowledgeDocumentStatusLabel(value),
          }))}
        />
      </Space>
      <div className="min-h-0 flex-1">
        <AppTable<KnowledgeDocument>
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
          locale={{ emptyText: '暂无文档' }}
        />
      </div>
    </div>
  );
}

function ChunkTable({ knowledgeBaseId }: { knowledgeBaseId: number }) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [tenantId, knowledgeBaseId]);

  const listQuery = useQuery({
    queryKey: knowledgeChunksQueryKey(tenantId, { knowledgeBaseId, page, pageSize }),
    queryFn: ({ signal }) => fetchChunks({ knowledgeBaseId, page, pageSize }, signal),
    enabled: tenantId != null,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => updateChunk(id, { enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-chunks'] });
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeChunk> = [
    { title: '文档', dataIndex: 'document_id', width: 80 },
    { title: '序号', dataIndex: 'chunk_index', width: 70 },
    { title: '字符数', dataIndex: 'char_count', width: 80 },
    { title: '页码', dataIndex: 'page_no', width: 70, render: (value: number | null) => value ?? '-' },
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
  ];

  return (
    <AppTable<KnowledgeChunk>
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
      locale={{ emptyText: '暂无切片' }}
    />
  );
}

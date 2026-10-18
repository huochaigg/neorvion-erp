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
  knowledgeGrantsQueryKey,
  knowledgeIndexStatusQueryKey,
  PERMISSION_CODE,
  type KnowledgeChunk,
  type KnowledgeDocument,
  type KnowledgeGrant,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Descriptions, Empty, Input, Popconfirm, Result, Select, Space, Spin, Switch, Table, Tabs, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { deleteDocument, fetchChunks, fetchDocuments, updateChunk } from '@/api/documents';
import { fetchKnowledgeBase } from '@/api/knowledge-bases';
import { deleteGrant, fetchGrants, upsertGrant } from '@/api/ops';
import { fetchIndexStatus, reindexKnowledgeBase } from '@/api/rag';
import { ActionCell, AppTable, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { UploadDocumentsDrawer } from '@/components/UploadDocumentsDrawer';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';
import { goBackOr } from '@/lib/navigation';

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

  const unavailableActions = (
    <Space>
      <Button onClick={() => goBackOr(navigate, '/bases')}>返回上一页</Button>
      <Button type="primary" onClick={() => navigate('/bases')}>
        返回知识库列表
      </Button>
    </Space>
  );

  if (!Number.isFinite(knowledgeBaseId)) {
    return <Result status="404" title="知识库不存在" extra={unavailableActions} />;
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
    const unavailable = error instanceof ApiError && (error.status === 403 || error.status === 404);
    return (
      <Result
        status={unavailable ? '404' : 'error'}
        title={unavailable ? '知识库不存在或不可访问' : '加载失败'}
        extra={unavailableActions}
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
          {
            key: 'index',
            label: '向量索引',
            children: <IndexStatusPanel knowledgeBaseId={knowledgeBaseId} />,
          },
          {
            key: 'grants',
            label: '授权',
            children: <GrantsPanel knowledgeBaseId={knowledgeBaseId} />,
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
            <Popconfirm title="移入回收站后该文档的切片将从列表和检索中隐藏，可恢复。" onConfirm={() => deleteMutation.mutate(record.id)}>
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

function IndexStatusPanel({ knowledgeBaseId }: { knowledgeBaseId: number }) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const query = useQuery({
    queryKey: knowledgeIndexStatusQueryKey(tenantId, knowledgeBaseId),
    queryFn: ({ signal }) => fetchIndexStatus(knowledgeBaseId, signal),
    enabled: tenantId != null,
    refetchInterval: (current) => {
      const data = current.state.data;
      if (!data) {
        return false;
      }
      return data.pending + data.stale + data.failed > 0 ? 3000 : false;
    },
  });

  const reindexMutation = useMutation({
    mutationFn: () => reindexKnowledgeBase(knowledgeBaseId),
    onSuccess: (data) => {
      message.success(`已排队 ${data.queued} 个索引任务`);
      void queryClient.invalidateQueries({ queryKey: knowledgeIndexStatusQueryKey(tenantId, knowledgeBaseId) });
    },
    onError: (error: Error) => message.error(error.message),
  });

  const data = query.data;
  return (
    <Card
      extra={
        <Can permission={PERMISSION_CODE.knowledgeUpdate}>
          <Button loading={reindexMutation.isPending} onClick={() => reindexMutation.mutate()}>
            重建索引
          </Button>
        </Can>
      }
    >
      {query.isLoading ? (
        <Spin />
      ) : data ? (
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="Embedding 模型">{data.model_name}</Descriptions.Item>
          <Descriptions.Item label="向量维度">{data.dimensions}</Descriptions.Item>
          <Descriptions.Item label="有效切片">{data.total_active_chunks}</Descriptions.Item>
          <Descriptions.Item label="已就绪">{data.ready}</Descriptions.Item>
          <Descriptions.Item label="排队中">{data.pending}</Descriptions.Item>
          <Descriptions.Item label="待更新">{data.stale}</Descriptions.Item>
          <Descriptions.Item label="失败">{data.failed}</Descriptions.Item>
          <Descriptions.Item label="旧模型向量">{data.incompatible ?? 0}</Descriptions.Item>
          <Descriptions.Item label="需要重建">
            {data.needs_reindex ? '是（更换 Embedding 后旧向量不会参与检索）' : '否'}
          </Descriptions.Item>
        </Descriptions>
      ) : (
        <Empty description="暂无索引状态" />
      )}
    </Card>
  );
}

function GrantsPanel({ knowledgeBaseId }: { knowledgeBaseId: number }) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [userId, setUserId] = useState<number | null>(null);
  const query = useQuery({
    queryKey: knowledgeGrantsQueryKey(tenantId, knowledgeBaseId),
    queryFn: ({ signal }) => fetchGrants(knowledgeBaseId, signal),
    enabled: tenantId != null,
  });
  return (
    <Card>
      <p className="mb-3 text-slate-500">
        无授权记录时，租户内具有 knowledge:read 的成员都可以访问。有记录后仅名单内用户可访问。
      </p>
      <Space className="mb-3">
        <Input
          placeholder="ERP 用户 ID"
          style={{ width: 160 }}
          onChange={(event) => setUserId(Number(event.target.value) || null)}
        />
        <Can permission={PERMISSION_CODE.knowledgeUpdate}>
          <Button
            type="primary"
            disabled={!userId}
            onClick={() => {
              if (!userId) return;
              upsertGrant(knowledgeBaseId, { user_id: userId, permission: 'READ' })
                .then(() => {
                  message.success('已授权');
                  void queryClient.invalidateQueries({ queryKey: knowledgeGrantsQueryKey(tenantId, knowledgeBaseId) });
                })
                .catch((error: Error) => message.error(error.message));
            }}
          >
            授予只读
          </Button>
        </Can>
      </Space>
      <Table<KnowledgeGrant>
        rowKey="id"
        size="small"
        loading={query.isLoading}
        dataSource={query.data?.items ?? []}
        pagination={false}
        columns={[
          { title: '用户 ID', dataIndex: 'user_id' },
          { title: '权限', dataIndex: 'permission' },
          {
            title: '',
            width: 80,
            render: (_, record) => (
              <Can permission={PERMISSION_CODE.knowledgeUpdate}>
                <Popconfirm
                  title="撤销该授权？"
                  onConfirm={() =>
                    deleteGrant(knowledgeBaseId, record.id)
                      .then(() => {
                        message.success('已撤销');
                        void queryClient.invalidateQueries({ queryKey: knowledgeGrantsQueryKey(tenantId, knowledgeBaseId) });
                      })
                      .catch((error: Error) => message.error(error.message))
                  }
                >
                  <Button type="link" size="small" danger>
                    撤销
                  </Button>
                </Popconfirm>
              </Can>
            ),
          },
        ]}
      />
    </Card>
  );
}

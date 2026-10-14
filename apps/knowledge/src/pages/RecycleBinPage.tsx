import { DEFAULT_PAGE_SIZE, knowledgeRecycleQueryKey, PERMISSION_CODE, type KnowledgeRecycleItem } from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Popconfirm, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { fetchRecycle, purgeDocument, purgeKnowledgeBase, restoreDocument, restoreKnowledgeBase } from '@/api/ops';
import { ActionCell, AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

export function RecycleBinPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const query = useQuery({
    queryKey: knowledgeRecycleQueryKey(tenantId, { page, pageSize }),
    queryFn: ({ signal }) => fetchRecycle({ page, pageSize }, signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-recycle'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-bases'] });
  };

  const restore = useMutation({
    mutationFn: (row: KnowledgeRecycleItem) =>
      row.resource_type === 'knowledge_base' ? restoreKnowledgeBase(row.id) : restoreDocument(row.id),
    onSuccess: () => {
      message.success('已恢复');
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const purge = useMutation({
    mutationFn: (row: KnowledgeRecycleItem) =>
      row.resource_type === 'knowledge_base' ? purgeKnowledgeBase(row.id) : purgeDocument(row.id),
    onSuccess: () => {
      message.success('已彻底删除');
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeRecycleItem> = [
    {
      title: '类型',
      dataIndex: 'resource_type',
      width: 110,
      render: (value: string) => <Tag>{value === 'knowledge_base' ? '知识库' : '文档'}</Tag>,
    },
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: '删除时间', dataIndex: 'deleted_at', width: 180, render: (value: string) => formatDateTime(value) },
    {
      title: '操作',
      width: 180,
      render: (_, record) => (
        <ActionCell>
          <Can permission={PERMISSION_CODE.knowledgeUpdate}>
            <Button type="link" size="small" onClick={() => restore.mutate(record)}>
              恢复
            </Button>
          </Can>
          <Can permission={PERMISSION_CODE.knowledgeDelete}>
            <Popconfirm title="彻底删除后无法恢复，且会清理文件与向量" onConfirm={() => purge.mutate(record)}>
              <Button type="link" size="small" danger>
                彻底删除
              </Button>
            </Popconfirm>
          </Can>
        </ActionCell>
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader title="回收站" description="软删除的知识库与文档。恢复后索引仍在，除非彻底删除。" />
      <ListTableArea>
        <AppTable
          rowKey={(row) => `${row.resource_type}-${row.id}`}
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data?.items ?? []}
          pagination={{
            current: page,
            pageSize,
            total: query.data?.total ?? 0,
            onChange: (next, size) => {
              setPage(next);
              setPageSize(size);
            },
          }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}

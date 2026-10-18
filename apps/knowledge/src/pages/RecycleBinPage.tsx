import { DEFAULT_PAGE_SIZE, knowledgeRecycleQueryKey, PERMISSION_CODE, type KnowledgeRecycleItem } from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Popconfirm, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import {
  emptyRecycle,
  fetchRecycle,
  purgeDocument,
  purgeKnowledgeBase,
  purgeRecycleBatch,
  restoreDocument,
  restoreKnowledgeBase,
  restoreRecycleBatch,
} from '@/api/ops';
import { ActionCell, AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

function batchMessage(
  succeeded: number,
  skipped: number,
  failed: number,
  verb: string,
) {
  if (failed > 0) {
    return `${verb}完成：成功 ${succeeded}，跳过 ${skipped}，失败 ${failed}`;
  }
  return `${verb}完成：成功 ${succeeded}${skipped ? `，跳过 ${skipped}` : ''}`;
}

export function RecycleBinPage() {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [selected, setSelected] = useState<KnowledgeRecycleItem[]>([]);
  const query = useQuery({
    queryKey: knowledgeRecycleQueryKey(tenantId, { page, pageSize }),
    queryFn: ({ signal }) => fetchRecycle({ page, pageSize }, signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    setSelected([]);
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-recycle'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-bases'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-documents'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-chunks'] });
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

  const restoreBatch = useMutation({
    mutationFn: () =>
      restoreRecycleBatch(selected.map((item) => ({ resource_type: item.resource_type, id: item.id }))),
    onSuccess: (result) => {
      message[result.failed ? 'warning' : 'success'](
        batchMessage(result.succeeded, result.skipped, result.failed, '批量恢复'),
      );
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const purgeBatch = useMutation({
    mutationFn: () =>
      purgeRecycleBatch(selected.map((item) => ({ resource_type: item.resource_type, id: item.id }))),
    onSuccess: (result) => {
      message[result.failed ? 'warning' : 'success'](
        batchMessage(result.succeeded, result.skipped, result.failed, '批量彻底删除'),
      );
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const emptyMutation = useMutation({
    mutationFn: (expectedCount: number) => emptyRecycle({ confirm: true, expected_count: expectedCount }),
    onSuccess: (result) => {
      message[result.failed ? 'warning' : 'success'](
        batchMessage(result.succeeded, result.skipped, result.failed, '清空回收站'),
      );
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const confirmEmpty = () => {
    const total = query.data?.total ?? 0;
    modal.confirm({
      title: '清空回收站',
      content: `将彻底删除当前回收站中的 ${total} 条记录（知识库及其级联文档、独立删除的文档）。文件、切片与向量一并清理，不可恢复。`,
      okText: '确认清空且不可恢复',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => emptyMutation.mutateAsync(total),
    });
  };

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
            <Popconfirm
              title={record.resource_type === 'knowledge_base' ? '彻底删除该知识库？' : '彻底删除该文档？'}
              description="将清理文件、切片与向量，且不可恢复。历史任务、评测与审计会保留。"
              onConfirm={() => purge.mutate(record)}
            >
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
      <PageHeader
        title="回收站"
        description="知识库删除会级联隐藏其下当时仍有效的文档；文档删除只影响该文档。恢复知识库不会恢复删除库之前就已单独删除的文档。"
        extra={
          <Space wrap>
            <Can permission={PERMISSION_CODE.knowledgeUpdate}>
              <Button disabled={!selected.length} loading={restoreBatch.isPending} onClick={() => restoreBatch.mutate()}>
                批量恢复
              </Button>
            </Can>
            <Can permission={PERMISSION_CODE.knowledgeDelete}>
              <Space>
                <Popconfirm
                  title={`彻底删除选中的 ${selected.length} 条？`}
                  description="不可恢复。部分失败不会回滚已成功项。"
                  disabled={!selected.length}
                  onConfirm={() => purgeBatch.mutate()}
                >
                  <Button danger disabled={!selected.length} loading={purgeBatch.isPending}>
                    批量彻底删除
                  </Button>
                </Popconfirm>
                <Button danger type="primary" disabled={!query.data?.total} loading={emptyMutation.isPending} onClick={confirmEmpty}>
                  清空回收站
                </Button>
              </Space>
            </Can>
          </Space>
        }
      />
      <ListTableArea>
        <AppTable
          rowKey={(row) => `${row.resource_type}-${row.id}`}
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data?.items ?? []}
          rowSelection={{
            selectedRowKeys: selected.map((item) => `${item.resource_type}-${item.id}`),
            onChange: (_keys, rows) => setSelected(rows),
          }}
          pagination={{
            current: page,
            pageSize,
            total: query.data?.total ?? 0,
            onChange: (next, size) => {
              setPage(next);
              setPageSize(size);
              setSelected([]);
            },
          }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}

import {
  DEFAULT_PAGE_SIZE,
  knowledgeProcessingTasksQueryKey,
  knowledgeTaskStatusLabel,
  knowledgeTaskTypeLabel,
  KNOWLEDGE_TASK_STATUS,
  KNOWLEDGE_TASK_TYPE,
  PERMISSION_CODE,
  type KnowledgeTask,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchProcessingTasks, retryProcessingTask } from '@/api/documents';
import { ActionCell, AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

export function TaskListPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [status, setStatus] = useState<string | undefined>();
  const [taskType, setTaskType] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setStatus(undefined);
    setTaskType(undefined);
    setPage(1);
  }, [tenantId]);

  const listQuery = useQuery({
    queryKey: knowledgeProcessingTasksQueryKey(tenantId, { status, taskType, page, pageSize }),
    queryFn: ({ signal }) =>
      fetchProcessingTasks({ status, taskType, page, pageSize }, signal),
    enabled: tenantId != null,
    refetchInterval: (current) => {
      const items = current.state.data?.items ?? [];
      return items.some((item) => item.status === 'QUEUED' || item.status === 'RUNNING') ? 2500 : false;
    },
  });

  const retryMutation = useMutation({
    mutationFn: retryProcessingTask,
    onSuccess: () => {
      message.success('已重新排队');
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-processing-tasks'] });
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeTask> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    {
      title: '类型',
      dataIndex: 'task_type',
      width: 90,
      render: (value: string) => knowledgeTaskTypeLabel(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={value === 'FAILED' ? 'error' : value === 'SUCCESS' ? 'success' : 'processing'}>
          {knowledgeTaskStatusLabel(value)}
        </Tag>
      ),
    },
    { title: '进度', dataIndex: 'progress', width: 80, render: (value: number) => `${value}%` },
    { title: '重试', dataIndex: 'attempt', width: 70 },
    { title: '失败原因', dataIndex: 'error_message', ellipsis: true, render: (value: string | null) => value || '-' },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: (value: string) => formatDateTime(value) },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_, record) => (
        <ActionCell>
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/bases/${record.knowledge_base_id}/documents/${record.document_id}`)}
          >
            文档
          </Button>
          {record.status === 'FAILED' ? (
            <Can permission={PERMISSION_CODE.knowledgeUpdate}>
              <Button type="link" size="small" onClick={() => retryMutation.mutate(record.id)}>
                重试
              </Button>
            </Can>
          ) : null}
        </ActionCell>
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader title="处理任务" description="解析与切片任务的排队、运行、成功和失败记录。数据库持久化，不依赖浏览器内存。" />
      <ListToolbar>
        <Space wrap>
          <Select
            allowClear
            placeholder="状态"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            style={{ width: 140 }}
            options={Object.values(KNOWLEDGE_TASK_STATUS).map((value) => ({
              value,
              label: knowledgeTaskStatusLabel(value),
            }))}
          />
          <Select
            allowClear
            placeholder="类型"
            value={taskType}
            onChange={(value) => {
              setTaskType(value);
              setPage(1);
            }}
            style={{ width: 140 }}
            options={Object.values(KNOWLEDGE_TASK_TYPE).map((value) => ({
              value,
              label: knowledgeTaskTypeLabel(value),
            }))}
          />
        </Space>
      </ListToolbar>
      <ListTableArea>
        <AppTable<KnowledgeTask>
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
          locale={{ emptyText: listQuery.isError ? '加载失败' : '暂无任务' }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}

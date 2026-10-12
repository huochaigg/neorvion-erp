import {
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  TASK_STATUS_LABEL,
  tasksQueryKey,
  taskStatusLabel,
  type AsyncTask,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, Progress, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { cancelTask, retryTask, fetchTasks } from '@/api/tasks';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

const STATUS_COLOR: Record<string, string> = {
  PENDING: 'default',
  QUEUED: 'blue',
  RUNNING: 'processing',
  SUCCESS: 'green',
  FAILED: 'red',
  CANCELLED: 'default',
};

export function TaskListPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<string>();
  const [keyword, setKeyword] = useState('');
  const [createdFrom, setCreatedFrom] = useState<string>();
  const [createdTo, setCreatedTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = { status, keyword, createdFrom, createdTo, page, pageSize: DEFAULT_PAGE_SIZE };
  const query = useQuery({
    queryKey: tasksQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchTasks(filters, signal),
    enabled: tenantId != null,
    refetchInterval: (current) =>
      current.state.data?.items.some((item) => item.status === 'RUNNING' || item.status === 'QUEUED')
        ? 3000
        : false,
  });
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'tasks'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'task'] });
  };

  const retryMutation = useMutation({
    mutationFn: retryTask,
    onSuccess: () => {
      message.success('已重新入队');
      invalidate();
    },
    onError: () => message.error('重试失败'),
  });
  const cancelMutation = useMutation({
    mutationFn: cancelTask,
    onSuccess: () => {
      message.success('已取消');
      invalidate();
    },
    onError: () => message.error('取消失败'),
  });

  const columns: ColumnsType<AsyncTask> = [
    { title: '任务 ID', dataIndex: 'task_id', width: 220 },
    { title: '类型', dataIndex: 'task_type', width: 140 },
    { title: '标题', dataIndex: 'title', width: 180 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag color={STATUS_COLOR[value]}>{taskStatusLabel(value)}</Tag>,
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 140,
      render: (value: number, row) => <Progress percent={value} size="small" status={row.status === 'FAILED' ? 'exception' : undefined} />,
    },
    { title: '创建人', dataIndex: 'created_by', width: 80 },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string) => formatDateTime(value),
    },
    { title: '重试', dataIndex: 'retry_count', width: 70, render: (value: number, row) => `${value}/${row.max_retries}` },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, row) => (
        <Space>
          <Button type="link" onClick={() => navigate(`/system/tasks/${row.task_id}`)}>
            详情
          </Button>
          <Can permission={PERMISSION_CODE.taskRetry}>
            {row.status === 'FAILED' || row.status === 'PENDING' ? (
              <Button type="link" onClick={() => retryMutation.mutate(row.task_id)}>
                重试
              </Button>
            ) : null}
          </Can>
          <Can permission={PERMISSION_CODE.taskCancel}>
            {row.status === 'PENDING' || row.status === 'QUEUED' ? (
              <Button type="link" danger onClick={() => cancelMutation.mutate(row.task_id)}>
                取消
              </Button>
            ) : null}
          </Can>
        </Space>
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader title={props.title ?? '任务中心'} description={props.description} />
      <ListToolbar>
        <Space wrap>
          <Input
            allowClear
            placeholder="标题 / 任务ID"
            value={keyword}
            onChange={(event) => {
              setKeyword(event.target.value);
              setPage(1);
            }}
            style={{ width: 200 }}
          />
          <Select
            allowClear
            placeholder="状态"
            value={status}
            style={{ width: 140 }}
            options={Object.entries(TASK_STATUS_LABEL).map(([value, label]) => ({ value, label }))}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
          />
          <AppRangePicker
            onChange={(dates) => {
              const range = rangeToDateTimes(dates);
              setCreatedFrom(range.from);
              setCreatedTo(range.to);
              setPage(1);
            }}
          />
        </Space>
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="task_id"
          loading={query.isPending}
          columns={columns}
          dataSource={query.data?.items ?? []}
          pagination={{
            current: page,
            total: query.data?.total ?? 0,
            pageSize: DEFAULT_PAGE_SIZE,
            onChange: setPage,
          }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}

import {
  PERMISSION_CODE,
  TASK_STATUS,
  taskLogsQueryKey,
  taskQueryKey,
  taskStatusLabel,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Descriptions, Progress, Space, Tag, Timeline } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { cancelTask, downloadTaskResult, fetchTask, fetchTaskLogs, retryTask } from '@/api/tasks';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function TaskDetailPage(_props: PageProps) {
  const { taskId = '' } = useParams();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const live =
    (status: string | undefined) =>
    status === TASK_STATUS.running || status === TASK_STATUS.queued || status === TASK_STATUS.pending;
  const query = useQuery({
    queryKey: taskQueryKey(tenantId, taskId),
    queryFn: ({ signal }) => fetchTask(taskId, signal),
    enabled: tenantId != null && Boolean(taskId),
    refetchInterval: (current) => (live(current.state.data?.status) ? 3000 : false),
  });
  const logsQuery = useQuery({
    queryKey: taskLogsQueryKey(tenantId, taskId),
    queryFn: ({ signal }) => fetchTaskLogs(taskId, signal),
    enabled: tenantId != null && Boolean(taskId),
    refetchInterval: () => (live(query.data?.status) ? 3000 : false),
  });
  const task = query.data;
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'task'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'tasks'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'task-logs'] });
  };

  const retryMutation = useMutation({
    mutationFn: () => retryTask(taskId),
    onSuccess: () => {
      message.success('已重新入队');
      invalidate();
    },
    onError: () => message.error('重试失败'),
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelTask(taskId),
    onSuccess: () => {
      message.success('已取消');
      invalidate();
    },
    onError: () => message.error('取消失败'),
  });

  return (
    <FormPageContainer>
      <PageHeader
        title={task?.title ?? '任务详情'}
        extra={
          <Space>
            <Can permission={PERMISSION_CODE.taskRetry}>
              {task && (task.status === 'FAILED' || task.status === 'PENDING') ? (
                <Button onClick={() => retryMutation.mutate()}>重试</Button>
              ) : null}
            </Can>
            <Can permission={PERMISSION_CODE.taskCancel}>
              {task && (task.status === 'PENDING' || task.status === 'QUEUED') ? (
                <Button danger onClick={() => cancelMutation.mutate()}>
                  取消
                </Button>
              ) : null}
            </Can>
            <Can permission={PERMISSION_CODE.taskDownload}>
              {task?.status === 'SUCCESS' && task.task_type === 'REPORT_EXPORT' ? (
                <Button
                  type="primary"
                  onClick={() =>
                    void downloadTaskResult(
                      task.task_id,
                      String(task.result?.file_name ?? 'export.csv'),
                    )
                  }
                >
                  下载
                </Button>
              ) : null}
            </Can>
            <Button onClick={() => navigate('/system/tasks')}>返回列表</Button>
          </Space>
        }
      />
      {task ? (
        <>
          <Progress
            percent={task.progress}
            status={task.status === 'FAILED' ? 'exception' : task.status === 'SUCCESS' ? 'success' : 'active'}
            className="mb-4"
          />
          <Descriptions bordered size="small" column={2} className="mb-4">
            <Descriptions.Item label="任务 ID">{task.task_id}</Descriptions.Item>
            <Descriptions.Item label="类型">{task.task_type}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag>{taskStatusLabel(task.status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="重试">
              {task.retry_count}/{task.max_retries}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatDateTime(task.created_at)}</Descriptions.Item>
            <Descriptions.Item label="开始时间">{formatDateTime(task.started_at)}</Descriptions.Item>
            <Descriptions.Item label="完成时间">{formatDateTime(task.finished_at)}</Descriptions.Item>
            <Descriptions.Item label="错误">{task.error_message || '-'}</Descriptions.Item>
          </Descriptions>
          <h3 className="mb-2 text-sm font-medium">Payload</h3>
          <pre className="mb-4 overflow-auto rounded bg-neutral-50 p-3 text-xs">
            {JSON.stringify(task.payload ?? {}, null, 2)}
          </pre>
          <h3 className="mb-2 text-sm font-medium">Result</h3>
          <pre className="mb-4 overflow-auto rounded bg-neutral-50 p-3 text-xs">
            {JSON.stringify(task.result ?? {}, null, 2)}
          </pre>
          <h3 className="mb-2 text-sm font-medium">任务日志</h3>
          <Timeline
            items={(logsQuery.data ?? []).map((item) => ({
              color: item.level === 'ERROR' ? 'red' : 'blue',
              children: (
                <div>
                  <div className="text-xs text-neutral-500">{formatDateTime(item.created_at)}</div>
                  <div>{item.message}</div>
                </div>
              ),
            }))}
          />
        </>
      ) : null}
    </FormPageContainer>
  );
}
